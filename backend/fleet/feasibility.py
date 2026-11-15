"""Hard-constraint check for a tractor's whole queue.

A queue is feasible only if every job, executed in order from the tractor's
start context, has the right implement, enough fuel left and finishes by its
deadline. Inserting a job early can break a later one, so the whole queue is
always re-simulated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .models import Job, Tractor, TractorStatus, World
from .routing import RoadNetwork

EPS = 1e-6


@dataclass(frozen=True)
class StartContext:
    """Where and when a tractor becomes free to start its (re)planned queue."""

    node: str
    time: float
    fuel: float
    # Travel already committed (current leg / pinned job), counted in totals.
    committed_travel: float = 0.0


@dataclass(frozen=True)
class QueueEval:
    ok: bool
    reason: str | None = None
    failed_job: str | None = None
    end_time: float = 0.0
    travel_hours: float = 0.0
    fuel_left: float = 0.0
    finish_times: dict[str, float] = field(default_factory=dict)


def remaining_leg_distance(tractor: Tractor, world: World, network: RoadNetwork) -> float:
    """Distance from the tractor's current position to the end of its path."""
    if not tractor.path:
        return 0.0
    nx, ny = world.node_position(tractor.path[0])
    total = math.hypot(tractor.x - nx, tractor.y - ny)
    for a, b in zip(tractor.path, tractor.path[1:]):
        total += network.distance(a, b)
    return total


def start_context(tractor: Tractor, world: World, network: RoadNetwork) -> StartContext:
    """Start context after the tractor finishes its pinned current job."""
    if tractor.current_job is None:
        return StartContext(node=tractor.node, time=world.time, fuel=tractor.fuel)

    job = world.jobs[tractor.current_job]
    travel = remaining_leg_distance(tractor, world, network) / tractor.speed
    work = job.remaining_hours
    fuel = tractor.fuel - travel * tractor.fuel_per_travel_hour - work * tractor.fuel_per_work_hour
    return StartContext(
        node=job.field_id,
        time=world.time + travel + work,
        fuel=fuel,
        committed_travel=travel,
    )


def evaluate_queue(
    tractor: Tractor,
    start: StartContext,
    job_ids: tuple[str, ...],
    jobs: dict[str, Job],
    network: RoadNetwork,
) -> QueueEval:
    node, time, fuel = start.node, start.time, start.fuel
    travel_total = start.committed_travel
    finish_times: dict[str, float] = {}

    def fail(reason: str, job_id: str) -> QueueEval:
        return QueueEval(ok=False, reason=reason, failed_job=job_id)

    if tractor.status == TractorStatus.BROKEN and job_ids:
        return fail(f"{tractor.id} is broken down", job_ids[0])

    for job_id in job_ids:
        job = jobs[job_id]
        if job.implement != tractor.implement:
            return fail(
                f"{tractor.id} carries a {tractor.implement.value}, "
                f"{job.id} needs a {job.implement.value}",
                job_id,
            )

        distance = network.distance(node, job.field_id)
        if distance == math.inf:
            return fail(f"no open road from {node} to {job.field_id}", job_id)

        travel = distance / tractor.speed
        needed = travel * tractor.fuel_per_travel_hour + job.remaining_hours * tractor.fuel_per_work_hour
        if needed > fuel + EPS:
            return fail(
                f"{tractor.id} needs {needed:.0f} fuel for {job.id}, has {max(fuel, 0):.0f} left",
                job_id,
            )

        finish = time + travel + job.remaining_hours
        if finish > job.deadline + EPS:
            return fail(
                f"{tractor.id} would finish {job.id} at {finish:.1f}h, deadline {job.deadline:.1f}h",
                job_id,
            )

        fuel -= needed
        time = finish
        travel_total += travel
        node = job.field_id
        finish_times[job_id] = finish

    return QueueEval(
        ok=True,
        end_time=time,
        travel_hours=travel_total,
        fuel_left=fuel,
        finish_times=finish_times,
    )

