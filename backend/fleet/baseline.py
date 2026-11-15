"""Greedy baseline dispatchers (no planning ahead).

Rules (also in README): whenever a healthy tractor is free, it takes the first
pending job it can feasibly do right now (implement, fuel, deadline), where
"first" means
- fcfs: submission order (first come, first served);
- edf:  earliest deadline first, ties broken by priority.
No lookahead and no re-ordering of other tractors' work. Work released by a
breakdown goes back to the pending pool with its finished share kept.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

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


Rule = Literal["fcfs", "edf"]


def _order(world: World, rule: Rule) -> list[str]:
    if rule == "edf":
        return sorted(world.jobs, key=lambda jid: (world.jobs[jid].deadline, world.jobs[jid].priority, jid))
    return sorted(world.jobs)


def dispatch(world: World, network: RoadNetwork, rule: Rule = "fcfs") -> World:
    world = _drop_hopeless(world)
    jobs = dict(world.jobs)
    tractors = dict(world.tractors)
    submission_order = _order(world, rule)

    for tid in sorted(tractors):
        t = tractors[tid]
        if t.status == TractorStatus.BROKEN or t.current_job or t.queue:
            continue
        start = StartContext(node=t.node, time=world.time, fuel=t.fuel)
        for jid in submission_order:
            if jobs[jid].status != JobStatus.PENDING:
                continue
            if evaluate_queue(t, start, (jid,), replace(world, jobs=jobs), network).ok:
                tractors[tid] = replace(t, queue=(jid,))
                jobs[jid] = replace(jobs[jid], status=JobStatus.ASSIGNED, tractor_id=tid)
                break

    all_free = all(t.status == TractorStatus.BROKEN or not (t.current_job or t.queue) for t in tractors.values())
    if all_free:
        # Nobody is busy and nobody could take what is left: it will never be done.
        jobs = {
            jid: replace(j, status=JobStatus.UNASSIGNABLE, reason="no free tractor can finish it in time")
            if j.status == JobStatus.PENDING else j
            for jid, j in jobs.items()
        }
    return replace(world, jobs=jobs, tractors=tractors)
