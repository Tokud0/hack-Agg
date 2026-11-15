"""Shifts for the live dashboard: surprise events and a start-of-shift feasibility check.

A generated shift must be finishable when it starts: every job has a tractor that can do it in
time, on the plan the coordinator itself makes. Surprise events then make it harder on purpose.
"""

from __future__ import annotations

import math
import random
from typing import Literal

from .coordinator import plan
from .models import JOB_TYPE_TO_IMPLEMENT
from .routing import build_network
from .scenario import DEFAULT_SPEED, MAX_JOBS, SHIFT_HOURS, EventIn, JobIn, ScenarioIn, random_live_scenario, to_world

DEADLINE_STEP_HOURS = 1.0
MAX_FIX_ROUNDS = 16
FIRST_SURPRISE_HOUR = 1.0
LAST_SURPRISE_HOUR = 5.0
# Marks an event nobody clicked: it fires on the clock, like a report from the field.
SURPRISE = "surprise"


def clock(hours: float, shift_start: float) -> str:
    total = round((shift_start + hours) * 60)
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def impossible_at_start(scenario: ScenarioIn) -> dict[str, str]:
    """Jobs the coordinator cannot place at the very start of the shift, with the reason."""
    world = to_world(scenario)
    return plan(world, build_network(world)).unassignable


def make_feasible(scenario: ScenarioIn, remove_impossible: bool = True) -> tuple[ScenarioIn, list[str]]:
    """Adjust a scenario until every job can be done from the start; say what was changed.

    A job no tractor can do in time gets a later deadline, an hour at a time, up to the end of
    the shift. A job that still does not fit (no matching implement, or too much work) is removed,
    or, with `remove_impossible` off, kept and reported: what the operator asked for is not thrown away.
    Raises ValueError if nothing doable is left.
    """
    implements = {t.implement for t in scenario.tractors}
    original = {j.id: j.deadline for j in scenario.jobs}
    removed: dict[str, str] = {}
    kept_impossible: dict[str, str] = {}
    current = scenario
    for _ in range(MAX_FIX_ROUNDS):
        stuck = {jid: why for jid, why in impossible_at_start(current).items() if jid not in kept_impossible}
        if not stuck:
            break
        jobs = []
        for job in current.jobs:
            if job.id not in stuck:
                jobs.append(job)
            elif JOB_TYPE_TO_IMPLEMENT[job.type] in implements and job.deadline < SHIFT_HOURS:
                jobs.append(job.model_copy(update={"deadline": min(SHIFT_HOURS, job.deadline + DEADLINE_STEP_HOURS)}))
            else:
                why = (f"no tractor has a {JOB_TYPE_TO_IMPLEMENT[job.type].value}" if JOB_TYPE_TO_IMPLEMENT[job.type] not in implements
                       else "it does not fit in the shift even with the latest deadline")
                if remove_impossible:
                    removed[job.id] = why
                else:
                    kept_impossible[job.id] = why
                    jobs.append(job)
        if not jobs:
            raise ValueError("no job in this scenario can be done by this fleet")
        current = current.model_copy(update={"jobs": jobs})

    start = scenario.shift_start_hour
    moved = [
        f"{j.id}: deadline moved from {clock(original[j.id], start)} to {clock(j.deadline, start)} so it can be done"
        for j in current.jobs if j.deadline != original[j.id]
    ]
    return current, [
        *moved,
        *(f"{jid} removed: {why}" for jid, why in sorted(removed.items())),
        *(f"{jid} kept, but it cannot be done: {why}" for jid, why in sorted(kept_impossible.items())),
    ]


FILLER_WORK_HOURS = 1.0
FILLER_SLACK_HOURS = 2.0


def with_work_on_every_field(scenario: ScenarioIn) -> tuple[ScenarioIn, list[str]]:
    """Give every field without a job one job, so no field the operator asked for has to be dropped."""
    implements = {t.implement.value for t in scenario.tractors}
    job_type = "spray" if "sprayer" in implements else "mow"
    jobs = list(scenario.jobs)
    added: list[str] = []
    for f in scenario.fields:
        if any(j.field_id == f.id for j in jobs) or len(jobs) >= MAX_JOBS:
            continue
        numbers = [int(j.id[1:]) for j in jobs if j.id[1:].isdigit()]
        reach = math.hypot(f.x - scenario.depot.x, f.y - scenario.depot.y) / DEFAULT_SPEED + FILLER_WORK_HOURS + FILLER_SLACK_HOURS
        job = JobIn(id=f"J{max(numbers, default=0) + 1:02d}", type=job_type, field_id=f.id, priority=2,
                    deadline=min(SHIFT_HOURS, math.ceil(reach * 2) / 2), work_hours=FILLER_WORK_HOURS)
        jobs.append(job)
        added.append(job.id)
    notes = [f"{', '.join(added)} added so every field has work"] if added else []
    return scenario.model_copy(update={"jobs": jobs}), notes


def describe_events(scenario: ScenarioIn) -> list[str]:
    """The armed events in words, so the operator can see what was understood."""
    start = scenario.shift_start_hour
    lines = []
    for e in scenario.demo_events:
        when = clock(e.at, start)
        if e.type == "breakdown":
            lines.append(f"Event at {when}: {e.tractor_id} breaks down")
        elif e.type == "block_road":
            lines.append(f"Event at {when}: road {e.a}–{e.b} closes")
        elif e.type == "change_priority":
            lines.append(f"Event at {when}: {e.job_id} becomes P{e.priority}")
        elif e.type == "weather":
            lines.append(f"Event at {when}: no {'spraying' if e.job_type == 'spray' else 'mowing'} for {e.hours:g} h")
    return lines


Trouble = Literal["none", "low", "high"]
# Chance of each kind of event on a quiet shift. A rough shift gets every kind, and a second closed road.
LOW_TROUBLE_CHANCE = {"breakdown": 0.25, "block_road": 0.45, "change_priority": 0.5, "weather": 0.35}


def random_events(scenario: ScenarioIn, seed: int, trouble: Trouble = "low") -> list[EventIn]:
    """Trouble for a shift, at random moments: breakdowns, closed roads, priority changes, weather.

    "low" rolls for each kind (a breakdown on about one shift in four) and always yields at least one
    event; "high" brings every kind. The last working tractor is never taken out.
    """
    if trouble == "none":
        return []
    rng = random.Random(seed)
    is_rough = trouble == "high"

    def happens(kind: str) -> bool:
        return rng.random() < (1.0 if is_rough else LOW_TROUBLE_CHANCE[kind])

    def moment() -> float:
        return round(rng.uniform(FIRST_SURPRISE_HOUR, LAST_SURPRISE_HOUR), 1)

    events: list[EventIn] = []
    if len(scenario.tractors) >= 2 and happens("breakdown"):
        events.append(EventIn(at=moment(), type="breakdown", tractor_id=rng.choice(scenario.tractors).id, source=SURPRISE))
    nodes = [scenario.depot.id, *(f.id for f in scenario.fields)]
    for _ in range(2 if is_rough else 1):
        if len(nodes) >= 3 and happens("block_road"):  # closing the only road would cut the farm in two
            a, b = rng.sample(nodes, 2)
            events.append(EventIn(at=moment(), type="block_road", a=a, b=b, source=SURPRISE))
    job = rng.choice(scenario.jobs)
    priority_change = EventIn(at=moment(), type="change_priority", job_id=job.id, priority=3 if job.priority == 1 else 1, source=SURPRISE)
    if happens("change_priority"):
        events.append(priority_change)
    if happens("weather"):
        held = rng.choice(sorted({j.type for j in scenario.jobs}))
        events.append(EventIn(at=moment(), type="weather", job_type=held, hours=rng.choice([1.0, 1.5, 2.0]), source=SURPRISE))
    return sorted(events or [priority_change], key=lambda e: e.at)


def with_surprises(scenario: ScenarioIn, seed: int, trouble: Trouble | None = None) -> ScenarioIn:
    """Arm generated events on a scenario. `trouble` defaults to the scenario's own setting."""
    level = trouble or scenario.trouble
    if level == "none":
        return scenario.model_copy(update={"demo_events": [], "auto_events": False})
    return scenario.model_copy(update={"demo_events": random_events(scenario, seed, level), "auto_events": True, "trouble": level})


def without_empty_fields(scenario: ScenarioIn) -> ScenarioIn:
    """Drop fields that have no job (they would sit on the map with nothing to do) and renumber the rest."""
    used = [f for f in scenario.fields if any(j.field_id == f.id for j in scenario.jobs)]
    renamed = {f.id: f"F{i + 1}" for i, f in enumerate(used)}
    fields = [f.model_copy(update={"id": renamed[f.id]}) for f in used]
    jobs = [j.model_copy(update={"field_id": renamed[j.field_id]}) for j in scenario.jobs]
    return scenario.model_copy(update={"fields": fields, "jobs": jobs, "demo_events": []})


def random_shift(
    seed: int, n_tractors: int | None = None, n_fields: int | None = None, n_jobs: int | None = None, trouble: Trouble = "low"
) -> ScenarioIn:
    """A random shift that can be finished as planned at 06:00, every field with work on it, with events armed."""
    scenario, _ = make_feasible(random_live_scenario(seed, n_tractors, n_fields, n_jobs))
    return with_surprises(without_empty_fields(scenario), seed, trouble)
