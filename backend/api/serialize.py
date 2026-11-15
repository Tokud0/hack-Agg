"""World -> JSON snapshot for the dashboard (map, Gantt, table, counters)."""

from __future__ import annotations

from fleet.engine import Run, metrics
from fleet.feasibility import evaluate_queue, start_context
from fleet.models import JobStatus, TractorStatus
from fleet.risk import outlook

LOG_TAIL = 200


def _gantt(run: Run) -> list[dict]:
    """Executed segments + in-progress + planned future blocks per tractor."""
    world = run.world
    blocks: list[dict] = []
    for job in world.jobs.values():
        for tid, s, e in job.segments:
            interrupted = job.status != JobStatus.DONE or e < (job.completed_at or e)
            blocks.append({"tractor_id": tid, "job_id": job.id, "start": s, "end": e,
                           "kind": "interrupted" if interrupted else "done"})

    for t in world.tractors.values():
        blocks.extend(
            {"tractor_id": t.id, "job_id": "", "start": s, "end": e, "kind": "refuel"} for s, e in t.refuel_segments
        )
        if t.status == TractorStatus.REFUELING and t.refuel_started_at is not None:
            blocks.append({"tractor_id": t.id, "job_id": "", "start": t.refuel_started_at,
                           "end": world.time + t.refuel_left, "kind": "refuel"})
        if t.status == TractorStatus.BROKEN:
            continue
        if t.current_job:
            job = world.jobs[t.current_job]
            start = start_context(t, world, run.network)
            work_start = job.started_at if job.started_at is not None else start.time - job.remaining_hours
            blocks.append({"tractor_id": t.id, "job_id": job.id, "start": work_start, "end": start.time,
                           "kind": "active"})
        if t.queue:
            start = start_context(t, world, run.network)
            ev = evaluate_queue(t, start, t.queue, world, run.network)
            blocks.extend(
                {"tractor_id": t.id, "job_id": "", "start": s, "end": e, "kind": "refuel"}
                for s, e in ev.refuel_stops.values()
            )
            for jid, finish in ev.finish_times.items():
                blocks.append({"tractor_id": t.id, "job_id": jid, "start": finish - world.jobs[jid].remaining_hours,
                               "end": finish, "kind": "planned"})
    return [{**b, "start": round(b["start"], 3), "end": round(b["end"], 3)} for b in blocks]


def snapshot(run: Run) -> dict:
    world = run.world
    ahead = outlook(world, run.network)
    return {
        "strategy": run.strategy,
        "time": round(world.time, 3),
        "tractors": [
            {
                "id": t.id,
                "implement": t.implement.value,
                "status": t.status.value,
                "x": round(t.x, 3),
                "y": round(t.y, 3),
                "node": t.node,
                "fuel": round(max(t.fuel, 0.0), 1),
                "fuel_capacity": t.fuel_capacity,
                "current_job": t.current_job,
                "queue": list(t.queue),
                "path": list(t.path),
                "refuels": t.refuels,
                "refuel_stop": t.refuel_stop,
            }
            for t in sorted(world.tractors.values(), key=lambda t: t.id)
        ],
        "jobs": [
            {
                "id": j.id,
                "type": j.type,
                "field_id": j.field_id,
                "priority": j.priority,
                "deadline": j.deadline,
                "work_hours": j.work_hours,
                "progress": round(j.progress, 3),
                "status": j.status.value,
                "tractor_id": j.tractor_id,
                "reason": j.reason,
                "completed_at": j.completed_at,
                "not_before": j.not_before,
                # Where the plan stands for this job: when it will be finished and the spare time before its deadline.
                "projected_finish": round(ahead[j.id].finish, 3) if j.id in ahead else None,
                "slack": round(ahead[j.id].slack, 3) if j.id in ahead else None,
                "at_risk": j.id in ahead and ahead[j.id].is_at_risk,
            }
            for j in sorted(world.jobs.values(), key=lambda j: j.id)
        ],
        "blocked_roads": [sorted(r) for r in world.blocked_roads],
        "gantt": _gantt(run),
        "metrics": metrics(run),
        "log": [
            {"index": i, "time": e.time, "kind": e.kind, "message": e.message, "data": e.data}
            for i, e in list(enumerate(run.log))[-LOG_TAIL:]
        ],
    }


def static_map(world) -> dict:
    return {
        "depot": {"id": world.depot.id, "x": world.depot.x, "y": world.depot.y},
        "fields": [{"id": f.id, "x": f.x, "y": f.y} for f in sorted(world.fields.values(), key=lambda f: f.id)],
    }
