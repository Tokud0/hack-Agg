"""First-come-first-served baseline dispatcher.

Rule (also in README): whenever a healthy tractor is free, it takes the first
pending job in submission order that it can feasibly do right now (implement,
fuel, deadline). No lookahead, no priorities, no re-ordering. Work released by
a breakdown goes back to the pending pool with its finished share kept.
"""

from __future__ import annotations

from dataclasses import replace

from .feasibility import StartContext, evaluate_queue
from .models import JobStatus, TractorStatus, World
from .routing import RoadNetwork


def _drop_hopeless(world: World) -> World:
    """Pending jobs nobody can still finish in time are marked unassignable."""
    capable = {t.implement for t in world.tractors.values() if t.status != TractorStatus.BROKEN}
    jobs = dict(world.jobs)
    for jid, job in world.jobs.items():
        if job.status != JobStatus.PENDING:
            continue
        if job.implement not in capable:
            jobs[jid] = replace(job, status=JobStatus.UNASSIGNABLE, reason=f"no working {job.implement.value}")
        elif world.time + job.remaining_hours > job.deadline:
            jobs[jid] = replace(job, status=JobStatus.UNASSIGNABLE, reason="missed deadline")
    return replace(world, jobs=jobs)


def dispatch(world: World, network: RoadNetwork) -> World:
    world = _drop_hopeless(world)
    jobs = dict(world.jobs)
    tractors = dict(world.tractors)
    submission_order = sorted(jobs)

    for tid in sorted(tractors):
        t = tractors[tid]
        if t.status == TractorStatus.BROKEN or t.current_job or t.queue:
            continue
        start = StartContext(node=t.node, time=world.time, fuel=t.fuel)
        for jid in submission_order:
            if jobs[jid].status != JobStatus.PENDING:
                continue
            if evaluate_queue(t, start, (jid,), jobs, network).ok:
                tractors[tid] = replace(t, queue=(jid,))
                jobs[jid] = replace(jobs[jid], status=JobStatus.ASSIGNED, tractor_id=tid)
                break

    return replace(world, jobs=jobs, tractors=tractors)
