"""Safety invariants checked after every re-plan."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .feasibility import evaluate_queue, start_context
from .models import JobStatus, Plan, TractorStatus, World
from .routing import RoadNetwork

INVARIANT_NAMES = (
    "one_tractor_per_job",
    "done_never_reassigned",
    "hard_constraints",
    "every_open_job_accounted",
)


@dataclass(frozen=True)
class InvariantReport:
    violations: tuple[str, ...]
    checked: tuple[str, ...] = INVARIANT_NAMES

    @property
    def ok(self) -> bool:
        return not self.violations


def check_plan(world: World, plan: Plan, network: RoadNetwork) -> InvariantReport:
    violations: list[str] = []
    pinned = {t.current_job: t.id for t in world.tractors.values() if t.current_job and t.status != TractorStatus.BROKEN}

    # 1. Each job has at most one tractor (queues + pinned current jobs).
    holders = Counter(jid for q in plan.queues.values() for jid in q)
    holders.update(pinned.keys())
    for jid, count in holders.items():
        if count > 1:
            violations.append(f"one_tractor_per_job: {jid} held by {count} tractors")

    # 2. A completed job is never reassigned.
    for jid in holders:
        if world.jobs[jid].status == JobStatus.DONE:
            violations.append(f"done_never_reassigned: {jid} is done but still planned")

    # 3. Every assignment satisfies implement, fuel and deadline.
    for tid, queue in plan.queues.items():
        tractor = world.tractors[tid]
        if tractor.status == TractorStatus.BROKEN:
            if queue:
                violations.append(f"hard_constraints: broken {tid} still has jobs {list(queue)}")
            continue
        ev = evaluate_queue(tractor, start_context(tractor, world, network), queue, world.jobs, network)
        if not ev.ok:
            violations.append(f"hard_constraints: {tid}: {ev.reason}")

    # 4. Every unfinished job is either planned or unassignable with a reason.
    for job in world.jobs.values():
        if job.status == JobStatus.DONE or job.id in holders:
            continue
        if not plan.unassignable.get(job.id):
            violations.append(f"every_open_job_accounted: {job.id} lost (no tractor, no reason)")

    return InvariantReport(violations=tuple(violations))
