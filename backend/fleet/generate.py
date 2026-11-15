"""Shifts for the live dashboard: surprise events and a start-of-shift feasibility check.

A generated shift must be finishable when it starts: every job has a tractor that can do it in
time, on the plan the coordinator itself makes. Surprise events then make it harder on purpose.
"""

from __future__ import annotations

import random

from .coordinator import plan
from .models import JOB_TYPE_TO_IMPLEMENT
from .routing import build_network
from .scenario import SHIFT_HOURS, EventIn, ScenarioIn, random_live_scenario, to_world

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


def make_feasible(scenario: ScenarioIn) -> tuple[ScenarioIn, list[str]]:
    """Adjust a scenario until every job can be done from the start; say what was changed.

    A job no tractor can do in time gets a later deadline, an hour at a time, up to the end of
    the shift. A job that still does not fit (no matching implement, or too much work) is removed.
    Raises ValueError if nothing doable is left.
    """
    implements = {t.implement for t in scenario.tractors}
    original = {j.id: j.deadline for j in scenario.jobs}
    removed: dict[str, str] = {}
    current = scenario
    for _ in range(MAX_FIX_ROUNDS):
        stuck = impossible_at_start(current)
        if not stuck:
            break
        jobs = []
        for job in current.jobs:
            if job.id not in stuck:
                jobs.append(job)
            elif JOB_TYPE_TO_IMPLEMENT[job.type] not in implements:
                removed[job.id] = f"no tractor has a {JOB_TYPE_TO_IMPLEMENT[job.type].value}"
            elif job.deadline < SHIFT_HOURS:
                jobs.append(job.model_copy(update={"deadline": min(SHIFT_HOURS, job.deadline + DEADLINE_STEP_HOURS)}))
            else:
                removed[job.id] = "it does not fit in the shift even with the latest deadline"
        if not jobs:
            raise ValueError("no job in this scenario can be done by this fleet")
        current = current.model_copy(update={"jobs": jobs})

    start = scenario.shift_start_hour
    moved = [
        f"{j.id}: deadline moved from {clock(original[j.id], start)} to {clock(j.deadline, start)} so it can be done"
        for j in current.jobs if j.deadline != original[j.id]
    ]
    return current, [*moved, *(f"{jid} removed: {why}" for jid, why in sorted(removed.items()))]


def random_events(scenario: ScenarioIn, seed: int) -> list[EventIn]:
    """One of each kind of trouble the coordinator handles, at random moments of the shift."""
    rng = random.Random(seed)

    def moment() -> float:
        return round(rng.uniform(FIRST_SURPRISE_HOUR, LAST_SURPRISE_HOUR), 1)

    events: list[EventIn] = []
    if len(scenario.tractors) >= 2:  # never take the only tractor out
        events.append(EventIn(at=moment(), type="breakdown", tractor_id=rng.choice(scenario.tractors).id, source=SURPRISE))
    nodes = [scenario.depot.id, *(f.id for f in scenario.fields)]
    if len(nodes) >= 3:  # closing the only road would cut the farm in two
        a, b = rng.sample(nodes, 2)
        events.append(EventIn(at=moment(), type="block_road", a=a, b=b, source=SURPRISE))
    job = rng.choice(scenario.jobs)
    events.append(EventIn(at=moment(), type="change_priority", job_id=job.id, priority=3 if job.priority == 1 else 1, source=SURPRISE))
    return sorted(events, key=lambda e: e.at)


def with_surprises(scenario: ScenarioIn, seed: int) -> ScenarioIn:
    return scenario.model_copy(update={"demo_events": random_events(scenario, seed), "auto_events": True})


def random_shift(seed: int, n_tractors: int | None = None, n_fields: int | None = None, n_jobs: int | None = None) -> ScenarioIn:
    """A random shift that can be finished as planned at 06:00, with surprise events armed."""
    scenario, _ = make_feasible(random_live_scenario(seed, n_tractors, n_fields, n_jobs))
    return with_surprises(scenario, seed)
