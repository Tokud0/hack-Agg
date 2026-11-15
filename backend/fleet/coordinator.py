"""Deterministic coordinator: filter -> greedy insertion -> local search.

Pure function of the world: same input always yields the same plan.
Priority 1 is the most urgent.
"""

from __future__ import annotations

from dataclasses import dataclass

from .feasibility import QueueEval, StartContext, evaluate_queue, start_context
from .models import Job, JobStatus, Plan, Tractor, TractorStatus, World
from .routing import RoadNetwork

PRIORITY_WEIGHT = {1: 4.0, 2: 2.0, 3: 1.0}
ASSIGN_WEIGHT = 1000.0  # completing work dominates everything else
TRAVEL_WEIGHT = 10.0
COMPLETION_WEIGHT = 1.0  # finish earlier -> less idle risk, more slack
DEFAULT_ITERATIONS = 50


@dataclass(frozen=True)
class PlanningInput:
    world: World
    network: RoadNetwork
    tractors: tuple[Tractor, ...]
    starts: dict[str, StartContext]
    pool: tuple[str, ...]


def priority_weight(job: Job) -> float:
    return PRIORITY_WEIGHT.get(job.priority, 1.0)


def pinned_jobs(world: World) -> set[str]:
    return {t.current_job for t in world.tractors.values() if t.current_job and t.status != TractorStatus.BROKEN}


def build_input(world: World, network: RoadNetwork) -> PlanningInput:
    tractors = tuple(
        world.tractors[tid] for tid in sorted(world.tractors) if world.tractors[tid].status != TractorStatus.BROKEN
    )
    starts = {t.id: start_context(t, world, network) for t in tractors}
    pinned = pinned_jobs(world)
    pool = tuple(
        sorted(
            (j.id for j in world.jobs.values() if j.status != JobStatus.DONE and j.id not in pinned),
            key=lambda jid: (world.jobs[jid].priority, world.jobs[jid].deadline, jid),
        )
    )
    return PlanningInput(world=world, network=network, tractors=tractors, starts=starts, pool=pool)


def _eval(inp: PlanningInput, tractor: Tractor, queue: tuple[str, ...]) -> QueueEval:
    return evaluate_queue(tractor, inp.starts[tractor.id], queue, inp.world.jobs, inp.network)


def _queue_cost(inp: PlanningInput, ev: QueueEval) -> float:
    completion = sum(t - inp.world.time for t in ev.finish_times.values())
    return TRAVEL_WEIGHT * ev.travel_hours + COMPLETION_WEIGHT * completion


def score_plan(inp: PlanningInput, queues: dict[str, tuple[str, ...]]) -> float | None:
    """Total objective (higher is better); None if any queue is infeasible."""
    total = 0.0
    for tractor in inp.tractors:
        queue = queues.get(tractor.id, ())
        ev = _eval(inp, tractor, queue)
        if not ev.ok:
            return None
        total += sum(ASSIGN_WEIGHT * priority_weight(inp.world.jobs[j]) for j in queue)
        total -= _queue_cost(inp, ev)
    return total


def best_insertion(
    inp: PlanningInput, queues: dict[str, tuple[str, ...]], job_id: str
) -> tuple[str, tuple[str, ...], float] | None:
    """Cheapest feasible (tractor, new_queue, added_cost) for one job."""
    best: tuple[str, tuple[str, ...], float] | None = None
    job = inp.world.jobs[job_id]
    for tractor in inp.tractors:
        if tractor.implement != job.implement:
            continue
        queue = queues[tractor.id]
        base_ev = _eval(inp, tractor, queue)
        base_cost = _queue_cost(inp, base_ev) if base_ev.ok else 0.0
        for pos in range(len(queue) + 1):
            candidate = queue[:pos] + (job_id,) + queue[pos:]
            ev = _eval(inp, tractor, candidate)
            if not ev.ok:
                continue
            added = _queue_cost(inp, ev) - base_cost
            if best is None or added < best[2] - 1e-9:
                best = (tractor.id, candidate, added)
    return best


def unassignable_reason(inp: PlanningInput, queues: dict[str, tuple[str, ...]], job_id: str) -> str:
    job = inp.world.jobs[job_id]
    capable = [t for t in inp.tractors if t.implement == job.implement]
    if not capable:
        return f"no working {job.implement.value} left in the fleet"
    reasons = []
    for tractor in capable:
        ev = _eval(inp, tractor, queues[tractor.id] + (job_id,))
        alone = _eval(inp, tractor, (job_id,))
        if not alone.ok:
            reasons.append(alone.reason or "infeasible")
        elif not ev.ok:
            reasons.append(f"{tractor.id} is fully booked with higher-value work ({ev.reason})")
    return "; ".join(reasons) if reasons else "no feasible slot"


def greedy(inp: PlanningInput) -> dict[str, tuple[str, ...]]:
    queues: dict[str, tuple[str, ...]] = {t.id: () for t in inp.tractors}
    for job_id in inp.pool:
        best = best_insertion(inp, queues, job_id)
        if best is not None:
            queues = {**queues, best[0]: best[1]}
    return queues


def _neighbours(inp: PlanningInput, queues: dict[str, tuple[str, ...]]):
    """Yield candidate plans: relocate, swap, insert unassigned, eject-and-insert."""
    assigned = [(tid, pos, jid) for tid, q in queues.items() for pos, jid in enumerate(q)]
    assigned_ids = {jid for _, _, jid in assigned}
    unassigned = [j for j in inp.pool if j not in assigned_ids]

    for tid, pos, jid in assigned:
        removed = {**queues, tid: queues[tid][:pos] + queues[tid][pos + 1 :]}
        for target in inp.tractors:
            q = removed[target.id]
            for p in range(len(q) + 1):
                yield {**removed, target.id: q[:p] + (jid,) + q[p:]}

    for i, (ta, pa, ja) in enumerate(assigned):
        for tb, pb, jb in assigned[i + 1 :]:
            if ta == tb:
                continue
            qa = queues[ta][:pa] + (jb,) + queues[ta][pa + 1 :]
            qb = queues[tb][:pb] + (ja,) + queues[tb][pb + 1 :]
            yield {**queues, ta: qa, tb: qb}

    for uid in unassigned:
        for target in inp.tractors:
            q = queues[target.id]
            for p in range(len(q) + 1):
                yield {**queues, target.id: q[:p] + (uid,) + q[p:]}
        for tid, pos, jid in assigned:
            q = queues[tid][:pos] + queues[tid][pos + 1 :]
            for p in range(len(q) + 1):
                yield {**queues, tid: q[:p] + (uid,) + q[p:]}


def local_search(
    inp: PlanningInput, queues: dict[str, tuple[str, ...]], iterations: int
) -> dict[str, tuple[str, ...]]:
    """First-improvement hill climbing with a fixed iteration cap (deterministic)."""
    current = queues
    current_score = score_plan(inp, current)
    if current_score is None:
        return current
    for _ in range(iterations):
        improved = False
        for candidate in _neighbours(inp, current):
            s = score_plan(inp, candidate)
            if s is not None and s > current_score + 1e-6:
                current, current_score, improved = candidate, s, True
                break
        if not improved:
            break
    return current


def plan(world: World, network: RoadNetwork, iterations: int = DEFAULT_ITERATIONS) -> Plan:
    inp = build_input(world, network)
    queues = local_search(inp, greedy(inp), iterations)
    assigned = {jid for q in queues.values() for jid in q}
    unassignable = {jid: unassignable_reason(inp, queues, jid) for jid in inp.pool if jid not in assigned}
    broken = {tid: () for tid, t in world.tractors.items() if t.status == TractorStatus.BROKEN}
    return Plan(
        queues={**broken, **queues},
        unassignable=unassignable,
        score=score_plan(inp, queues) or 0.0,
    )
