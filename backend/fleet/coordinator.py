"""Deterministic coordinator: filter -> multi-start construction -> local search.

Several starting plans (different job orders, plus an earliest-deadline
schedule) are each improved by local search; the best feasible plan wins.
Shuffled starts use fixed seeds, so the same input always yields the same plan.
Priority 1 is the most urgent.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

from .feasibility import QueueEval, StartContext, evaluate_queue, start_context
from .models import Job, JobStatus, Plan, Tractor, TractorStatus, World
from .routing import RoadNetwork

PRIORITY_WEIGHT = {1: 4.0, 2: 2.0, 3: 1.0}
ASSIGN_WEIGHT = 1000.0  # completing work dominates everything else
TRAVEL_WEIGHT = 10.0
COMPLETION_WEIGHT = 1.0  # finish earlier -> less idle risk, more slack
DEFAULT_ITERATIONS = 50
SHUFFLED_STARTS = 4


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
    return evaluate_queue(tractor, inp.starts[tractor.id], queue, inp.world, inp.network)


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


Queues = dict[str, tuple[str, ...]]
# Award rule of a construction round: cheapest insertion, or soonest finish when appended.
AwardRule = Literal["cheapest", "soonest"]
# Observers let the agent transcript watch the search without changing it.
AwardObserver = Callable[[str, Queues, "str | None", AwardRule], None]  # job, queues before, winner, rule
TradeObserver = Callable[[Queues, Queues, float], None]  # queues before, queues after, score gain
Build = Callable[["AwardObserver | None"], Queues]


def greedy(inp: PlanningInput, order: tuple[str, ...] | None = None, observe: AwardObserver | None = None) -> Queues:
    """Cheapest feasible insertion of each job, in the given order."""
    queues: Queues = {t.id: () for t in inp.tractors}
    for job_id in order or inp.pool:
        best = best_insertion(inp, queues, job_id)
        if observe:
            observe(job_id, queues, best[0] if best else None, "cheapest")
        if best is not None:
            queues = {**queues, best[0]: best[1]}
    return queues


def earliest_deadline_schedule(inp: PlanningInput, observe: AwardObserver | None = None) -> Queues:
    """Jobs by deadline, each appended to the tractor that can finish it soonest."""
    jobs = inp.world.jobs
    queues: Queues = {t.id: () for t in inp.tractors}
    for job_id in sorted(inp.pool, key=lambda j: (jobs[j].deadline, jobs[j].priority, j)):
        options = []
        for t in inp.tractors:
            ev = _eval(inp, t, queues[t.id] + (job_id,))
            if ev.ok:
                options.append((ev.finish_times[job_id], t.id))
        if observe:
            observe(job_id, queues, min(options)[1] if options else None, "soonest")
        if options:
            _, tid = min(options)
            queues = {**queues, tid: queues[tid] + (job_id,)}
    return queues


@dataclass(frozen=True)
class Candidate:
    """One starting plan of the multi-start search and where local search took it."""

    name: str
    start_score: float | None
    score: float | None
    jobs_assigned: int
    is_winner: bool = False


def _starting_plans(inp: PlanningInput) -> list[tuple[str, Build]]:
    jobs = inp.world.jobs
    by_deadline = tuple(sorted(inp.pool, key=lambda j: (jobs[j].deadline, jobs[j].priority, j)))
    by_slack = tuple(sorted(inp.pool, key=lambda j: (jobs[j].deadline - jobs[j].remaining_hours, j)))
    starts: list[tuple[str, Build]] = [
        ("priority order", lambda observe=None: greedy(inp, observe=observe)),
        ("deadline order", lambda observe=None: greedy(inp, by_deadline, observe)),
        ("least slack first", lambda observe=None: greedy(inp, by_slack, observe)),
        ("earliest-deadline schedule", lambda observe=None: earliest_deadline_schedule(inp, observe)),
    ]
    for seed in range(SHUFFLED_STARTS):
        shuffled = list(inp.pool)
        random.Random(seed).shuffle(shuffled)
        starts.append((f"shuffled order #{seed + 1}", lambda observe=None, order=tuple(shuffled): greedy(inp, order, observe)))
    return starts


def search(inp: PlanningInput, iterations: int) -> tuple[Queues, tuple[Candidate, ...]]:
    """Improve every starting plan; return the best one plus the record of all candidates."""
    best_queues: Queues = {t.id: () for t in inp.tractors}
    best_score = score_plan(inp, best_queues) or 0.0
    winner: int | None = None
    candidates: list[Candidate] = []
    for name, build in _starting_plans(inp):
        start = build(None)
        queues = local_search(inp, start, iterations)
        score = score_plan(inp, queues)
        candidates.append(Candidate(name, score_plan(inp, start), score, sum(len(q) for q in queues.values())))
        if score is not None and score > best_score + 1e-6:
            best_queues, best_score, winner = queues, score, len(candidates) - 1
    return best_queues, tuple(replace(c, is_winner=i == winner) for i, c in enumerate(candidates))


def best_plan(inp: PlanningInput, iterations: int) -> Queues:
    return search(inp, iterations)[0]


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
    inp: PlanningInput, queues: dict[str, tuple[str, ...]], iterations: int, observe: TradeObserver | None = None
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
                if observe:
                    observe(current, candidate, s - current_score)
                current, current_score, improved = candidate, s, True
                break
        if not improved:
            break
    return current


def replay_winner(
    inp: PlanningInput,
    candidates: tuple[Candidate, ...],
    on_award: AwardObserver,
    on_trade: TradeObserver,
    iterations: int = DEFAULT_ITERATIONS,
) -> None:
    """Re-run only the winning candidate with observers attached.

    The search is deterministic, so the replay takes exactly the steps of the first run.
    """
    for candidate, (_, build) in zip(candidates, _starting_plans(inp)):
        if candidate.is_winner:
            local_search(inp, build(on_award), iterations, on_trade)


def plan(world: World, network: RoadNetwork, iterations: int = DEFAULT_ITERATIONS) -> Plan:
    return plan_with_trace(world, network, iterations)[0]


def plan_with_trace(
    world: World, network: RoadNetwork, iterations: int = DEFAULT_ITERATIONS
) -> tuple[Plan, tuple[Candidate, ...]]:
    """The plan plus every candidate the search considered (for the orchestration trace)."""
    inp = build_input(world, network)
    queues, candidates = search(inp, iterations)
    assigned = {jid for q in queues.values() for jid in q}
    unassignable = {jid: unassignable_reason(inp, queues, jid) for jid in inp.pool if jid not in assigned}
    broken = {tid: () for tid, t in world.tractors.items() if t.status == TractorStatus.BROKEN}
    result = Plan(
        queues={**broken, **queues},
        unassignable=unassignable,
        score=score_plan(inp, queues) or 0.0,
    )
    return result, candidates
