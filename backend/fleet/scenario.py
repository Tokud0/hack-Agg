"""Scenario loading (validated at the boundary) and seeded random generation."""

from __future__ import annotations

import json
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
    type: Literal["breakdown", "block_road", "change_priority"]
    tractor_id: str | None = None
    a: str | None = None
    b: str | None = None
    job_id: str | None = None
    priority: int | None = None


class ScenarioIn(BaseModel):
    name: str = "scenario"
    shift_start_hour: float = 6
    depot: DepotIn
    tractors: list[TractorIn] = PField(min_length=1)
    fields: list[FieldIn] = PField(min_length=1)
    jobs: list[JobIn] = PField(min_length=1)
    demo_events: list[EventIn] = []

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
    return World(time=0.0, fields=fields, jobs=jobs, tractors=tractors, depot=depot)


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
