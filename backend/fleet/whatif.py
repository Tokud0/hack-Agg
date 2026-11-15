"""What-if forecast: fork the live run, apply a hypothetical event, simulate to the end."""

from __future__ import annotations

from dataclasses import replace

from .engine import Run, apply_event, metrics, run_to_end
from .models import JobStatus
from .scenario import EventIn


def forecast(run: Run, event: EventIn) -> dict:
    base = replace(run, pending_events=())
    current = run_to_end(base)
    alternative = run_to_end(apply_event(base, event.model_copy(update={"at": run.world.time})))
    done_now = {j.id for j in current.world.jobs.values() if j.status == JobStatus.DONE}
    done_alt = {j.id for j in alternative.world.jobs.values() if j.status == JobStatus.DONE}
    lost = [
        {"job_id": jid, "reason": alternative.world.jobs[jid].reason or "not finished in time"}
        for jid in sorted(done_now - done_alt)
    ]
    keys = ("jobs_completed", "priority1_completed", "travel_hours", "idle_hours")
    return {
        "event": event.model_dump(exclude_none=True, exclude={"at"}),
        "at_hours": round(run.world.time, 2),
        "current": {k: metrics(current)[k] for k in keys},
        "what_if": {k: metrics(alternative)[k] for k in keys},
        "lost_jobs": lost,
        "gained_jobs": sorted(done_alt - done_now),
    }
