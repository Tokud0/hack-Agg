"""One re-plan entry point for every event: state in, verified plan out."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

from .coordinator import plan as coordinate
from .invariants import InvariantReport, check_plan
from .models import Job, JobStatus, Plan, TractorStatus, World
from .routing import RoadNetwork, build_network


@dataclass(frozen=True)
class ReplanResult:
    world: World
    plan: Plan
    previous_plan: Plan | None
    report: InvariantReport
    accepted: bool
    duration_ms: float


def current_plan(world: World) -> Plan:
    """Reconstruct the plan currently applied to the world."""
    queues = {tid: t.queue for tid, t in world.tractors.items()}
    unassignable = {j.id: j.reason or "" for j in world.jobs.values() if j.status == JobStatus.UNASSIGNABLE}
    return Plan(queues=queues, unassignable=unassignable)


def apply_plan(world: World, plan: Plan) -> World:
    tractors = {tid: replace(t, queue=plan.queues.get(tid, ())) for tid, t in world.tractors.items()}
    owner = {jid: tid for tid, q in plan.queues.items() for jid in q}
    pinned = {t.current_job for t in world.tractors.values() if t.current_job}

    jobs = {}
    for jid, job in world.jobs.items():
        if job.status == JobStatus.DONE or jid in pinned:
            jobs[jid] = job
        elif jid in owner:
            jobs[jid] = replace(job, status=JobStatus.ASSIGNED, tractor_id=owner[jid], reason=None)
        else:
            reason = plan.unassignable.get(jid, "not planned")
            jobs[jid] = replace(job, status=JobStatus.UNASSIGNABLE, tractor_id=None, reason=reason)
    return replace(world, tractors=tractors, jobs=jobs)


def replan(world: World, network: RoadNetwork | None = None) -> ReplanResult:
    """Run the coordinator; keep the previous plan if invariants fail."""
    network = network or build_network(world)
    previous = current_plan(world)
    started = time.perf_counter()
    new_plan = coordinate(world, network)
    duration_ms = (time.perf_counter() - started) * 1000
    report = check_plan(world, new_plan, network)
    if not report.ok:
        return ReplanResult(world, previous, previous, report, False, duration_ms)
    return ReplanResult(apply_plan(world, new_plan), new_plan, previous, report, True, duration_ms)


def _release(job: Job, tractor_id: str, now: float) -> Job:
    """Back to the pool; an interrupted work segment is closed, progress kept."""
    segments = job.segments
    if job.started_at is not None:
        segments = segments + ((tractor_id, job.started_at, now),)
    return replace(job, status=JobStatus.PENDING, tractor_id=None, started_at=None, segments=segments)


def break_tractor(world: World, tractor_id: str) -> World:
    """Stop a tractor: keep finished share of its job, release all unfinished work."""
    tractor = world.tractors[tractor_id]
    released = set(tractor.queue)
    if tractor.current_job:
        released.add(tractor.current_job)
    jobs = {jid: (_release(j, tractor_id, world.time) if jid in released else j) for jid, j in world.jobs.items()}
    broken = replace(tractor, status=TractorStatus.BROKEN, current_job=None, queue=(), path=())
    return replace(world, jobs=jobs, tractors={**world.tractors, tractor_id: broken})


def block_road(world: World, a: str, b: str) -> World:
    return replace(world, blocked_roads=world.blocked_roads | {frozenset((a, b))})


def change_priority(world: World, job_id: str, priority: int) -> World:
    job = world.jobs[job_id]
    return replace(world, jobs={**world.jobs, job_id: replace(job, priority=priority)})
