"""Discrete-time simulator: moves tractors along roads and works fields."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .feasibility import plan_leg
from .models import Job, JobStatus, Tractor, TractorStatus, World
from .routing import RoadNetwork

DEFAULT_DT = 0.05  # simulated hours per tick
EPS = 1e-9


@dataclass(frozen=True)
class SimEvent:
    time: float
    kind: str
    tractor_id: str
    job_id: str | None = None


def is_finished(world: World) -> bool:
    open_jobs = any(j.status not in (JobStatus.DONE, JobStatus.UNASSIGNABLE) for j in world.jobs.values())
    busy = any(t.current_job for t in world.tractors.values() if t.status != TractorStatus.BROKEN)
    return not open_jobs and not busy


def _open_work_by_implement(world: World) -> set:
    """Implements that still have unfinished, assignable work waiting."""
    return {j.implement for j in world.jobs.values() if j.status not in (JobStatus.DONE, JobStatus.UNASSIGNABLE)}


def _towards_field(t: Tractor, world: World, network: RoadNetwork) -> Tractor:
    path = network.path(t.node, world.jobs[t.current_job].field_id)
    return replace(t, path=path, status=TractorStatus.TRAVELING if path else TractorStatus.WORKING)


def _start_refuel(t: Tractor, world: World, now: float) -> Tractor:
    return replace(t, status=TractorStatus.REFUELING, refuel_left=world.refuel_hours or 0.0, refuel_started_at=now)


def _start_next(t: Tractor, world: World, network: RoadNetwork, now: float) -> Tractor:
    if t.current_job or not t.queue:
        return t
    job_id, rest = t.queue[0], t.queue[1:]
    t = replace(t, current_job=job_id, queue=rest)
    leg = plan_leg(t, t.node, t.fuel, world.jobs[job_id], world, network)
    if not (leg.ok and leg.refuel):
        return _towards_field(t, world, network)
    t = replace(t, refuel_stop=True)
    if t.node == world.depot.id:
        return _start_refuel(t, world, now)
    return replace(t, path=network.path(t.node, world.depot.id), status=TractorStatus.TRAVELING)


def _refuel(t: Tractor, world: World, network: RoadNetwork, dt: float, now: float) -> tuple[Tractor, float]:
    """Fill up at the depot; once full, head to the job's field."""
    spent = min(dt, t.refuel_left)
    left = t.refuel_left - spent
    if left > EPS:
        return replace(t, refuel_left=left), 0.0
    started = t.refuel_started_at if t.refuel_started_at is not None else now
    full = replace(
        t,
        fuel=t.fuel_capacity,
        refuel_left=0.0,
        refuel_stop=False,
        refuels=t.refuels + 1,
        refuel_segments=t.refuel_segments + ((started, now + spent),),
        refuel_started_at=None,
    )
    return _towards_field(full, world, network), dt - spent


def _travel(t: Tractor, world: World, dt: float) -> tuple[Tractor, float]:
    """Move along the path; returns the tractor and unused time if it arrived."""
    budget = t.speed * dt
    x, y, node, path = t.x, t.y, t.node, t.path
    while path and budget > EPS:
        tx, ty = world.node_position(path[0])
        gap = math.hypot(tx - x, ty - y)
        if gap <= budget:
            x, y, node, path = tx, ty, path[0], path[1:]
            budget -= gap
        else:
            ratio = budget / gap
            x, y = x + (tx - x) * ratio, y + (ty - y) * ratio
            budget = 0.0
    used = dt - budget / t.speed
    status = TractorStatus.TRAVELING if path else TractorStatus.WORKING
    moved = replace(
        t,
        x=x,
        y=y,
        node=node,
        path=path,
        status=status,
        fuel=t.fuel - used * t.fuel_per_travel_hour,
        travel_time=t.travel_time + used,
    )
    return moved, dt - used


def _work(t: Tractor, job: Job, dt: float, now: float) -> tuple[Tractor, Job, float]:
    """Work on the job; returns tractor, job and unused time if it finished."""
    worked = min(dt, job.remaining_hours)
    remaining = job.remaining_hours - worked
    done = remaining <= EPS
    started_at = job.started_at if job.started_at is not None else now
    new_job = replace(
        job,
        remaining_hours=0.0 if done else remaining,
        status=JobStatus.DONE if done else JobStatus.IN_PROGRESS,
        tractor_id=t.id,
        completed_at=now + worked if done else None,
        started_at=None if done else started_at,
        segments=job.segments + ((t.id, started_at, now + worked),) if done else job.segments,
    )
    new_t = replace(
        t,
        fuel=t.fuel - worked * t.fuel_per_work_hour,
        work_time=t.work_time + worked,
        current_job=None if done else t.current_job,
        status=TractorStatus.IDLE if done else TractorStatus.WORKING,
    )
    return new_t, new_job, dt - worked


def _advance(
    t: Tractor, world: World, jobs: dict[str, Job], network: RoadNetwork, dt: float, open_work: bool
) -> tuple[Tractor, list[SimEvent]]:
    """Spend one tick on a tractor, chaining travel -> work -> next job."""
    events: list[SimEvent] = []
    budget = dt
    while budget > EPS:
        now = world.time + (dt - budget)
        t = _start_next(t, world, network, now)
        if t.current_job is None:
            idle = budget if open_work else 0.0
            return replace(t, status=TractorStatus.IDLE, idle_time=t.idle_time + idle), events
        if t.status == TractorStatus.REFUELING:
            t, budget = _refuel(t, world, network, budget, now)
            if not t.refuel_stop:
                events.append(SimEvent(world.time + dt - budget, "refueled", t.id, t.current_job))
            continue
        if t.status == TractorStatus.TRAVELING:
            t, budget = _travel(t, world, budget)
            if t.status == TractorStatus.WORKING and t.refuel_stop:
                t = _start_refuel(t, world, world.time + dt - budget)
                events.append(SimEvent(world.time + dt - budget, "refuel_started", t.id, t.current_job))
                continue
            if t.status == TractorStatus.WORKING and jobs[t.current_job].not_before <= world.time + dt - budget + EPS:
                jobs[t.current_job] = replace(jobs[t.current_job], status=JobStatus.IN_PROGRESS, tractor_id=t.id)
                events.append(SimEvent(world.time + dt - budget, "job_started", t.id, t.current_job))
            continue
        job_id = t.current_job
        held_for = jobs[job_id].not_before - now
        if held_for > EPS:
            # The weather does not allow this work yet: stand by at the field, burning nothing.
            if t.status != TractorStatus.WAITING:
                events.append(SimEvent(now, "weather_hold", t.id, job_id))
            t = replace(t, status=TractorStatus.WAITING)
            budget -= min(budget, held_for)
            continue
        if jobs[job_id].status != JobStatus.IN_PROGRESS:
            events.append(SimEvent(now, "job_started", t.id, job_id))
        t, jobs[job_id], budget = _work(t, jobs[job_id], budget, now)
        if t.current_job is None:
            events.append(SimEvent(world.time + dt - budget, "job_done", t.id, job_id))
    return t, events


def step(world: World, network: RoadNetwork, dt: float = DEFAULT_DT) -> tuple[World, list[SimEvent]]:
    jobs = dict(world.jobs)
    tractors: dict[str, Tractor] = {}
    events: list[SimEvent] = []
    open_work = _open_work_by_implement(world)

    for tid in sorted(world.tractors):
        t = world.tractors[tid]
        if t.status == TractorStatus.BROKEN:
            tractors[tid] = t
            continue
        tractors[tid], tractor_events = _advance(t, world, jobs, network, dt, t.implement in open_work)
        events.extend(tractor_events)

    return replace(world, time=world.time + dt, jobs=jobs, tractors=tractors), events
