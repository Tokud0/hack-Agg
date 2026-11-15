"""Facts behind one assignment: score breakdown and rejected alternatives.

These numbers are what the LLM is allowed to talk about when asked "why?".
"""

from __future__ import annotations

from .coordinator import best_insertion, build_input, priority_weight
from .feasibility import evaluate_queue, start_context
from .models import JobStatus, World
from .routing import RoadNetwork


def _alternatives(world: World, network: RoadNetwork, job_id: str, owner: str | None) -> list[dict]:
    inp = build_input(world, network)
    job = world.jobs[job_id]
    queues = {t.id: tuple(j for j in world.tractors[t.id].queue if j != job_id) for t in inp.tractors}
    result = []
    for tid in sorted(world.tractors):
        if tid == owner:
            continue
        tractor = world.tractors[tid]
        if tractor.status.value == "broken":
            result.append({"tractor_id": tid, "feasible": False, "reason": f"{tid} is broken down"})
            continue
        if tractor.implement != job.implement:
            result.append(
                {"tractor_id": tid, "feasible": False, "reason": f"carries a {tractor.implement.value}, job needs a {job.implement.value}"}
            )
            continue
        only_this = {**{k: () for k in queues}, tid: queues[tid]}
        best = best_insertion(inp, only_this, job_id)
        if best is None:
            ev = evaluate_queue(tractor, inp.starts[tid], queues[tid] + (job_id,), world.jobs, network)
            result.append({"tractor_id": tid, "feasible": False, "reason": ev.reason or "no feasible slot"})
        else:
            result.append(
                {"tractor_id": tid, "feasible": True, "added_cost": round(best[2], 1),
                 "reason": "feasible but costs more travel/time than the chosen tractor or would push out other work"}
            )
    return result


def explain_assignment(world: World, network: RoadNetwork, job_id: str) -> dict:
    job = world.jobs[job_id]
    base = {
        "job_id": job_id,
        "field_id": job.field_id,
        "type": job.type,
        "priority": job.priority,
        "priority_weight": priority_weight(job),
        "deadline": job.deadline,
        "status": job.status.value,
        "progress": round(job.progress, 2),
    }
    if job.status == JobStatus.UNASSIGNABLE:
        return {**base, "tractor_id": None, "reason": job.reason, "alternatives": _alternatives(world, network, job_id, None)}
    if job.status == JobStatus.DONE or job.tractor_id is None:
        return {**base, "tractor_id": job.tractor_id, "alternatives": []}

    tractor = world.tractors[job.tractor_id]
    start = start_context(tractor, world, network)
    queue = tractor.queue
    if job_id in queue:
        idx = queue.index(job_id)
        before = evaluate_queue(tractor, start, queue[:idx], world.jobs, network)
        through = evaluate_queue(tractor, start, queue[: idx + 1], world.jobs, network)
        prev_node = world.jobs[queue[idx - 1]].field_id if idx else start.node
        finish = through.finish_times.get(job_id, 0.0)
        fuel_before, fuel_after = before.fuel_left, through.fuel_left
        position = idx + 1
    else:  # pinned current job
        prev_node = tractor.node
        finish = start.time
        fuel_before, fuel_after = tractor.fuel, start.fuel
        position = 0

    travel = network.distance(prev_node, job.field_id) / tractor.speed
    return {
        **base,
        "tractor_id": tractor.id,
        "queue_position": position,
        "travel_hours_to_field": round(travel, 2),
        "planned_finish": round(finish, 2),
        "deadline_slack_hours": round(job.deadline - finish, 2),
        "fuel_before": round(fuel_before, 1),
        "fuel_after": round(fuel_after, 1),
        "fuel_capacity": tractor.fuel_capacity,
        "alternatives": _alternatives(world, network, job_id, tractor.id),
    }
