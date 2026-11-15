"""Hard-constraint check for a tractor's whole queue.

A queue is feasible only if every job, executed in order from the tractor's
start context, has the right implement, enough fuel and finishes by its
deadline. Inserting a job early can break a later one, so the whole queue is
always re-simulated.

Fuel rule (shared with the simulator so execution matches the plan): a
tractor must always be able to get back to the depot. That reserve is what
lets it take over work when another tractor breaks down. If the tank cannot
cover the trip, the work and the drive from that field back to the depot, the
tractor first drives to the depot, fills up, then goes to the field. If a full tank is
not enough, the job is infeasible. With refuelling disabled, only the trip and
the work must fit in the tank.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .models import Job, Tractor, TractorStatus, World
from .models import clock_time
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
    # job id -> (refuel start, refuel end) for jobs preceded by a depot stop.
    refuel_stops: dict[str, tuple[float, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class Leg:
    """How a tractor gets from a node to a job and does it."""

    ok: bool
    refuel: bool = False
    to_depot_hours: float = 0.0
    travel_hours: float = 0.0  # total driving, including any depot detour
    fuel_after: float = 0.0
    reason: str | None = None


def plan_leg(tractor: Tractor, node: str, fuel: float, job: Job, world: World, network: RoadNetwork) -> Leg:
    rate_t, rate_w = tractor.fuel_per_travel_hour, tractor.fuel_per_work_hour
    distance = network.distance(node, job.field_id)
    if distance == math.inf:
        return Leg(ok=False, reason=f"no open road from {node} to {job.field_id}")
    travel = distance / tractor.speed
    needed = travel * rate_t + job.remaining_hours * rate_w
    if world.refuel_hours is None:
        if needed <= fuel + EPS:
            return Leg(ok=True, travel_hours=travel, fuel_after=fuel - needed)
        return Leg(ok=False, reason=f"{tractor.id} needs {needed:.0f} fuel for {job.id}, has {max(fuel, 0):.0f} left")

    depot = world.depot.id
    to_depot = network.distance(node, depot) / tractor.speed
    from_depot = network.distance(depot, job.field_id) / tractor.speed
    if math.inf in (to_depot, from_depot):
        return Leg(ok=False, reason=f"no open road via the depot to {job.field_id}")
    reserve = from_depot * rate_t  # always keep enough to drive back to the depot
    if needed + reserve <= fuel + EPS:
        return Leg(ok=True, travel_hours=travel, fuel_after=fuel - needed)

    needed_full = from_depot * rate_t + job.remaining_hours * rate_w
    if needed_full + reserve > tractor.fuel_capacity + EPS:
        return Leg(ok=False, reason=f"{job.id} needs {needed_full + reserve:.0f} fuel incl. the way back, more than {tractor.id}'s full tank")
    if to_depot * rate_t > fuel + EPS:
        return Leg(ok=False, reason=f"{tractor.id} cannot reach the depot to refuel ({max(fuel, 0):.0f} fuel left)")
    return Leg(
        ok=True,
        refuel=True,
        to_depot_hours=to_depot,
        travel_hours=to_depot + from_depot,
        fuel_after=tractor.fuel_capacity - needed_full,
    )


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
    work = job.remaining_hours
    leg_travel = remaining_leg_distance(tractor, world, network) / tractor.speed

    if tractor.refuel_stop:
        # Still heading to (or filling up at) the depot before the job.
        from_depot = network.distance(world.depot.id, job.field_id) / tractor.speed
        refuel_wait = tractor.refuel_left if tractor.status == TractorStatus.REFUELING else (world.refuel_hours or 0.0)
        fuel = (
            tractor.fuel_capacity
            - from_depot * tractor.fuel_per_travel_hour
            - work * tractor.fuel_per_work_hour
        )
        return StartContext(
            node=job.field_id,
            time=world.time + leg_travel + refuel_wait + from_depot + work,
            fuel=fuel,
            committed_travel=leg_travel + from_depot,
        )

    fuel = tractor.fuel - leg_travel * tractor.fuel_per_travel_hour - work * tractor.fuel_per_work_hour
    return StartContext(
        node=job.field_id,
        time=world.time + leg_travel + work,
        fuel=fuel,
        committed_travel=leg_travel,
    )


def evaluate_queue(
    tractor: Tractor,
    start: StartContext,
    job_ids: tuple[str, ...],
    world: World,
    network: RoadNetwork,
) -> QueueEval:
    jobs = world.jobs
    node, time, fuel = start.node, start.time, start.fuel
    travel_total = start.committed_travel
    finish_times: dict[str, float] = {}
    refuel_stops: dict[str, tuple[float, float]] = {}

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

        leg = plan_leg(tractor, node, fuel, job, world, network)
        if not leg.ok:
            return fail(leg.reason or "infeasible", job_id)

        refuel_wait = (world.refuel_hours or 0.0) if leg.refuel else 0.0
        if leg.refuel:
            refuel_start = time + leg.to_depot_hours
            refuel_stops[job_id] = (refuel_start, refuel_start + refuel_wait)
        finish = time + leg.travel_hours + refuel_wait + job.remaining_hours
        if finish > job.deadline + EPS:
            via = " (incl. refuel stop)" if leg.refuel else ""
            return fail(
                f"{tractor.id} would finish {job.id} at {clock_time(finish)}{via}, deadline {clock_time(job.deadline)}",
                job_id,
            )

        fuel = leg.fuel_after
        time = finish
        travel_total += leg.travel_hours
        node = job.field_id
        finish_times[job_id] = finish

    return QueueEval(
        ok=True,
        end_time=time,
        travel_hours=travel_total,
        fuel_left=fuel,
        finish_times=finish_times,
        refuel_stops=refuel_stops,
    )

