"""Deadline risk: how much spare time every planned job has, before anything goes wrong."""

from __future__ import annotations

from dataclasses import dataclass

from .feasibility import evaluate_queue, start_context
from .models import TractorStatus, World
from .routing import RoadNetwork

# A job that would finish with less spare time than this is flagged while it can still be saved.
AT_RISK_SLACK_HOURS = 0.5


@dataclass(frozen=True)
class JobOutlook:
    job_id: str
    tractor_id: str
    finish: float
    deadline: float

    @property
    def slack(self) -> float:
        return self.deadline - self.finish

    @property
    def is_at_risk(self) -> bool:
        return self.slack < AT_RISK_SLACK_HOURS


def outlook(world: World, network: RoadNetwork) -> dict[str, JobOutlook]:
    """Projected finish of every job that is in progress or queued, on the plan as it stands."""
    result: dict[str, JobOutlook] = {}
    for tractor in world.tractors.values():
        if tractor.status == TractorStatus.BROKEN:
            continue
        start = start_context(tractor, world, network)
        finishes = {tractor.current_job: start.time} if tractor.current_job else {}
        if tractor.queue:
            queued = evaluate_queue(tractor, start, tractor.queue, world, network)
            finishes = {**finishes, **queued.finish_times}
        for job_id, finish in finishes.items():
            result[job_id] = JobOutlook(job_id, tractor.id, finish, world.jobs[job_id].deadline)
    return result


def at_risk(world: World, network: RoadNetwork) -> list[JobOutlook]:
    return sorted((o for o in outlook(world, network).values() if o.is_at_risk), key=lambda o: o.slack)
