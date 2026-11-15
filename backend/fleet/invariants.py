"""Safety invariants checked after every re-plan."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .feasibility import evaluate_queue, start_context
from .models import JobStatus, Plan, TractorStatus, World, clock_time
from .routing import RoadNetwork

FUEL_TOLERANCE = 1e-6

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
    # Problems the plan did not cause and cannot fix (work in progress that will finish late).
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violations


def check_plan(world: World, plan: Plan, network: RoadNetwork) -> InvariantReport:
    violations: list[str] = []
    warnings: list[str] = []
    # Work in progress, one entry per tractor: two tractors on the same job must both be counted.
    active = [(t.current_job, t) for t in world.tractors.values() if t.current_job and t.status != TractorStatus.BROKEN]

    # 1. Each job has at most one tractor (queues + current jobs), and the job agrees who that is.
    holders = Counter(jid for q in plan.queues.values() for jid in q)
    holders.update(jid for jid, _ in active)
    for jid, count in holders.items():
        if count > 1:
            violations.append(f"one_tractor_per_job: {jid} held by {count} tractors")
    for jid, tractor in active:
        owner = world.jobs[jid].tractor_id
        if owner != tractor.id:
            violations.append(f"one_tractor_per_job: {jid} is worked by {tractor.id} but recorded on {owner or 'no tractor'}")

    # 2. A completed job is never reassigned.
    for jid in holders:
        if world.jobs[jid].status == JobStatus.DONE:
            violations.append(f"done_never_reassigned: {jid} is done but still planned")

    # 3. Every assignment satisfies implement, fuel and deadline, starting with the work in progress.
    for jid, tractor in active:
        job = world.jobs[jid]
        after_job = start_context(tractor, world, network)
        if job.implement != tractor.implement:
            violations.append(f"hard_constraints: {tractor.id} carries a {tractor.implement.value}, its current job {jid} needs a {job.implement.value}")
        if after_job.fuel < -FUEL_TOLERANCE:
            violations.append(f"hard_constraints: {tractor.id} runs out of fuel before finishing its current job {jid}")
        if job.status != JobStatus.DONE and after_job.time > job.deadline + 1e-6:
            warnings.append(f"{jid} is in progress on {tractor.id} and will finish at {clock_time(after_job.time)}, after its {clock_time(job.deadline)} deadline")
    for tid, queue in plan.queues.items():
        tractor = world.tractors[tid]
        if tractor.status == TractorStatus.BROKEN:
            if queue:
                violations.append(f"hard_constraints: broken {tid} still has jobs {list(queue)}")
            continue
        ev = evaluate_queue(tractor, start_context(tractor, world, network), queue, world, network)
        if not ev.ok:
            violations.append(f"hard_constraints: {tid}: {ev.reason}")

    # 4. Every unfinished job is either planned or unassignable with a reason.
    for job in world.jobs.values():
        if job.status == JobStatus.DONE or job.id in holders:
            continue
        if not plan.unassignable.get(job.id):
            violations.append(f"every_open_job_accounted: {job.id} lost (no tractor, no reason)")

    return InvariantReport(violations=tuple(violations), warnings=tuple(warnings))
