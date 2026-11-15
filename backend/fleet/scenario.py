"""Scenario loading (validated at the boundary) and seeded random generation."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field as PField, model_validator

from .models import Field, Implement, Job, Tractor, World


class DepotIn(BaseModel):
    id: str = "D"
    x: float
    y: float


class TractorIn(BaseModel):
    id: str
    implement: Implement
    fuel_capacity: float = PField(gt=0)
    speed: float = PField(gt=0)
    fuel_per_travel_hour: float = PField(ge=0)
    fuel_per_work_hour: float = PField(ge=0)


class FieldIn(BaseModel):
    id: str
    x: float
    y: float


class JobIn(BaseModel):
    id: str
    type: Literal["spray", "mow"]
    field_id: str
    priority: int = PField(ge=1, le=3)
    deadline: float = PField(gt=0)
    work_hours: float = PField(gt=0)


class EventIn(BaseModel):
    at: float = PField(ge=0)
    type: Literal["breakdown", "block_road", "change_priority", "weather"]
    tractor_id: str | None = None
    a: str | None = None
    b: str | None = None
    job_id: str | None = None
    priority: int | None = None
    # Weather: the kind of work it rules out, for `hours` from the moment it arrives (or until `until`).
    job_type: Literal["spray", "mow"] | None = None
    hours: float | None = PField(default=None, gt=0, le=12)
    until: float | None = None
    # Who raised it: "operator" (button), "copilot" (LLM proposal the operator confirmed)
    # "telemetry" (a scheduled fault the tractor reports itself) or "surprise" (a generated
    # event of a random shift). Nobody clicks for the last two.
    source: str | None = None


class ScenarioIn(BaseModel):
    name: str = "scenario"
    shift_start_hour: float = 6
    # Hours to refill at the depot; null disables refuelling.
    refuel_hours: float | None = PField(default=0.25, ge=0)
    depot: DepotIn
    tractors: list[TractorIn] = PField(min_length=1)
    fields: list[FieldIn] = PField(min_length=1)
    jobs: list[JobIn] = PField(min_length=1)
    demo_events: list[EventIn] = []
    # Live dashboard only: fire `demo_events` by themselves on the clock (generated ones if none are given).
    auto_events: bool = False
    # How much goes wrong when events are generated: "low" is a mostly quiet shift, "high" a rough one.
    trouble: Literal["low", "high"] = "low"

    @model_validator(mode="after")
    def _check_refs(self) -> "ScenarioIn":
        field_ids = {f.id for f in self.fields}
        for job in self.jobs:
            if job.field_id not in field_ids:
                raise ValueError(f"job {job.id} references unknown field {job.field_id}")
        for ids, kind in ((self.tractors, "tractor"), (self.fields, "field"), (self.jobs, "job")):
            names = [x.id for x in ids]
            if len(names) != len(set(names)):
                raise ValueError(f"duplicate {kind} ids")
        tractor_ids = {t.id for t in self.tractors}
        job_ids = {j.id for j in self.jobs}
        nodes = field_ids | {self.depot.id}
        for event in self.demo_events:  # an event fires long after loading; a bad reference must fail here
            if event.type == "breakdown" and event.tractor_id not in tractor_ids:
                raise ValueError(f"event references unknown tractor {event.tractor_id}")
            if event.type == "block_road" and (event.a not in nodes or event.b not in nodes or event.a == event.b):
                raise ValueError(f"event references unknown road {event.a}–{event.b}")
            if event.type == "change_priority" and (event.job_id not in job_ids or event.priority not in (1, 2, 3)):
                raise ValueError(f"event references unknown job {event.job_id} or a bad priority")
            if event.type == "weather" and (event.job_type is None or (event.hours is None and event.until is None)):
                raise ValueError("a weather event needs the kind of work it holds and for how long")
        return self


def to_world(scenario: ScenarioIn) -> World:
    depot = Field(scenario.depot.id, scenario.depot.x, scenario.depot.y)
    tractors = {
        t.id: Tractor(
            id=t.id,
            implement=t.implement,
            fuel_capacity=t.fuel_capacity,
            fuel=t.fuel_capacity,
            speed=t.speed,
            fuel_per_travel_hour=t.fuel_per_travel_hour,
            fuel_per_work_hour=t.fuel_per_work_hour,
            x=depot.x,
            y=depot.y,
            node=depot.id,
        )
        for t in scenario.tractors
    }
    fields = {f.id: Field(f.id, f.x, f.y) for f in scenario.fields}
    jobs = {
        j.id: Job(
            id=j.id,
            type=j.type,
            field_id=j.field_id,
            priority=j.priority,
            deadline=j.deadline,
            work_hours=j.work_hours,
            remaining_hours=j.work_hours,
        )
        for j in scenario.jobs
    }
    return World(
        time=0.0, fields=fields, jobs=jobs, tractors=tractors, depot=depot, refuel_hours=scenario.refuel_hours
    )


def load_scenario(path: str | Path) -> ScenarioIn:
    return ScenarioIn.model_validate(json.loads(Path(path).read_text()))


def random_scenario(seed: int, n_fields: int = 8, n_jobs: int = 10) -> ScenarioIn:
    """Same shape as the demo: 2 sprayers (one low on fuel) + 1 mower, one breakdown."""
    rng = random.Random(seed)
    fields = [FieldIn(id=f"F{i + 1}", x=rng.randint(0, 10), y=rng.randint(1, 10)) for i in range(n_fields)]
    tractors = [
        TractorIn(id="T1", implement=Implement.SPRAYER, fuel_capacity=100, speed=4,
                  fuel_per_travel_hour=5, fuel_per_work_hour=8),
        TractorIn(id="T2", implement=Implement.MOWER, fuel_capacity=100, speed=4,
                  fuel_per_travel_hour=5, fuel_per_work_hour=8),
        TractorIn(id="T3", implement=Implement.SPRAYER, fuel_capacity=rng.choice([60, 70, 80]), speed=4,
                  fuel_per_travel_hour=5, fuel_per_work_hour=8),
    ]
    jobs = [
        JobIn(
            id=f"J{i + 1:02d}",
            type="spray" if rng.random() < 0.7 else "mow",
            field_id=rng.choice(fields).id,
            priority=rng.randint(1, 3),
            deadline=round(rng.uniform(2.5, 10.0), 1),
            work_hours=round(rng.uniform(0.5, 2.0), 1),
        )
        for i in range(n_jobs)
    ]
    breakdown = EventIn(at=round(rng.uniform(1.0, 3.0), 1), type="breakdown", tractor_id=rng.choice(["T1", "T3"]))
    return ScenarioIn(
        name=f"random-{seed}",
        depot=DepotIn(x=5, y=0),
        tractors=tractors,
        fields=fields,
        jobs=jobs,
        demo_events=[breakdown],
    )


# --- scenarios for the live dashboard: random and operator-built --------------

GRID_MAX = 10
MAX_TRACTORS = 4
MAX_FIELDS = 10
MAX_JOBS = 14
SHIFT_HOURS = 12.0
DEFAULT_SPEED = 4.0
DEFAULT_TRAVEL_BURN = 5.0
DEFAULT_WORK_BURN = 8.0
DEPOT = DepotIn(x=5, y=0)
# Field tiles are 1.5 wide on the map, so fields sit on a coarse lattice to stay apart.
FIELD_SLOTS = tuple((x, y) for x in (1, 3, 5, 7, 9) for y in (2, 4, 6, 8, 10))


class TractorDraft(BaseModel):
    implement: Literal["sprayer", "mower"]
    fuel_capacity: float = 100


class FieldDraft(BaseModel):
    x: float
    y: float


class JobDraftIn(BaseModel):
    type: Literal["spray", "mow"]
    field_number: int  # 1-based position in `fields`
    priority: int
    deadline_hours: float  # hours after shift start
    work_hours: float


class EventDraft(BaseModel):
    """Something the description says will go wrong during the shift. Numbers are 1-based positions in the draft's lists."""

    type: Literal["breakdown", "block_road", "change_priority", "weather"]
    at_hours: float  # hours after shift start
    tractor_number: int | None = None  # breakdown
    from_field_number: int | None = None  # block_road; 0 is the depot
    to_field_number: int | None = None
    job_number: int | None = None  # change_priority
    priority: int | None = None
    work_type: Literal["spray", "mow"] | None = None  # weather: the work it stops
    hours: float | None = None  # weather: for how long


class ScenarioDraft(BaseModel):
    """A scenario as a person (or the LLM reading a person) would give it: no ids, no fuel rates."""

    name: str
    tractors: list[TractorDraft]
    fields: list[FieldDraft]
    jobs: list[JobDraftIn]
    events: list[EventDraft] = []


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _free_slot(wanted: tuple[int, int], taken: set[tuple[int, int]]) -> tuple[int, int]:
    """The wanted cell, or the nearest free cell, so two fields never share a spot."""
    cells = [(x, y) for x in range(GRID_MAX + 1) for y in range(1, GRID_MAX + 1) if (x, y) not in taken]
    return min(cells, key=lambda c: (c[0] - wanted[0]) ** 2 + (c[1] - wanted[1]) ** 2)


def scenario_from_draft(draft: ScenarioDraft) -> ScenarioIn:
    """Turn a loose draft into a valid scenario: ids assigned, values clamped, defaults filled in.

    Raises ValueError when there is nothing usable (no tractor, field or job).
    """
    tractors = [
        TractorIn(id=f"T{i + 1}", implement=Implement(t.implement), fuel_capacity=_clamp(t.fuel_capacity, 30, 200),
                  speed=DEFAULT_SPEED, fuel_per_travel_hour=DEFAULT_TRAVEL_BURN, fuel_per_work_hour=DEFAULT_WORK_BURN)
        for i, t in enumerate(draft.tractors[:MAX_TRACTORS])
    ]
    taken: set[tuple[int, int]] = {(int(DEPOT.x), int(DEPOT.y))}
    fields = []
    for i, f in enumerate(draft.fields[:MAX_FIELDS]):
        cell = _free_slot((round(_clamp(f.x, 0, GRID_MAX)), round(_clamp(f.y, 1, GRID_MAX))), taken)
        taken.add(cell)
        fields.append(FieldIn(id=f"F{i + 1}", x=cell[0], y=cell[1]))
    jobs = []
    job_id_of: dict[int, str] = {}  # the draft's job number -> the id it got (jobs on a missing field are dropped)
    for number, j in enumerate(draft.jobs[:MAX_JOBS], start=1):
        if not 1 <= j.field_number <= len(fields):
            continue
        work = round(_clamp(j.work_hours, 0.25, 6), 2)
        job_id_of[number] = f"J{len(jobs) + 1:02d}"
        jobs.append(JobIn(id=job_id_of[number], type=j.type, field_id=fields[j.field_number - 1].id,
                          priority=int(_clamp(j.priority, 1, 3)),
                          deadline=round(_clamp(j.deadline_hours, work + 0.5, SHIFT_HOURS), 2), work_hours=work))
    if not tractors or not fields or not jobs:
        raise ValueError("a scenario needs at least one tractor, one field and one job on an existing field")
    events = _events_from_draft(draft.events, tractors, fields, job_id_of)
    return ScenarioIn(name=draft.name.strip()[:60] or "Custom shift", depot=DEPOT, tractors=tractors, fields=fields, jobs=jobs,
                      demo_events=events, auto_events=bool(events))


MAX_DRAFT_EVENTS = 6


def _events_from_draft(drafts: list[EventDraft], tractors: list[TractorIn], fields: list[FieldIn], job_id_of: dict[int, str]) -> list[EventIn]:
    """The described events as events that fire by themselves. One that points at something that is not there is left out."""
    def node(number: int | None) -> str | None:
        if number == 0:
            return DEPOT.id
        return fields[number - 1].id if number is not None and 1 <= number <= len(fields) else None

    events: list[EventIn] = []
    for e in drafts[:MAX_DRAFT_EVENTS]:
        at = round(_clamp(e.at_hours, 0.25, SHIFT_HOURS - 1), 2)
        if e.type == "breakdown" and e.tractor_number is not None and 1 <= e.tractor_number <= len(tractors):
            events.append(EventIn(at=at, type="breakdown", tractor_id=tractors[e.tractor_number - 1].id, source="surprise"))
        elif e.type == "block_road" and node(e.from_field_number) and node(e.to_field_number) and node(e.from_field_number) != node(e.to_field_number):
            events.append(EventIn(at=at, type="block_road", a=node(e.from_field_number), b=node(e.to_field_number), source="surprise"))
        elif e.type == "change_priority" and e.job_number in job_id_of and e.priority in (1, 2, 3):
            events.append(EventIn(at=at, type="change_priority", job_id=job_id_of[e.job_number], priority=e.priority, source="surprise"))
        elif e.type == "weather" and e.work_type is not None:
            events.append(EventIn(at=at, type="weather", job_type=e.work_type, hours=_clamp(e.hours or 1.0, 0.5, 6), source="surprise"))
    return sorted(events, key=lambda e: e.at)


def random_live_scenario(seed: int, n_tractors: int | None = None, n_fields: int | None = None, n_jobs: int | None = None) -> ScenarioIn:
    """A fresh shift for the dashboard: fields spread over the map, 2-4 tractors, every job doable by some tractor.

    Separate from `random_scenario`, whose exact output the benchmark depends on.
    """
    rng = random.Random(seed)
    n_tractors = int(_clamp(n_tractors or rng.randint(2, 4), 1, MAX_TRACTORS))
    n_fields = int(_clamp(n_fields or rng.randint(5, 9), 1, MAX_FIELDS))
    n_jobs = int(_clamp(n_jobs or rng.randint(n_fields, n_fields + 4), 1, MAX_JOBS))
    implements = ["sprayer", "mower"] + [rng.choice(["sprayer", "sprayer", "mower"]) for _ in range(MAX_TRACTORS)]
    tractors = [TractorDraft(implement=implements[i], fuel_capacity=rng.choice([60, 80, 100])) for i in range(n_tractors)]
    available = {t.implement for t in tractors}
    job_types = [t for t in ("spray", "mow") if {"spray": "sprayer", "mow": "mower"}[t] in available]
    fields = [FieldDraft(x=x, y=y) for x, y in rng.sample(FIELD_SLOTS, n_fields)]
    jobs = []
    for i in range(n_jobs):
        spot = fields[i % n_fields]
        work = rng.choice([0.5, 1.0, 1.5, 2.0])
        # Never earlier than a tractor leaving the depot at once could finish, plus some slack.
        reachable = math.hypot(spot.x - DEPOT.x, spot.y - DEPOT.y) / DEFAULT_SPEED + work + rng.choice([0.5, 1.0, 2.0])
        deadline = math.ceil(max(rng.uniform(3.0, 11.0), reachable) * 2) / 2
        jobs.append(JobDraftIn(type=rng.choice(job_types), field_number=(i % n_fields) + 1, priority=rng.choice([1, 2, 2, 3]),
                               deadline_hours=deadline, work_hours=work))
    return scenario_from_draft(ScenarioDraft(name=f"Random shift #{seed}", tractors=tractors, fields=fields, jobs=jobs))
