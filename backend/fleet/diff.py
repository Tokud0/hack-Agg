"""Structured plan diff: the only input the LLM gets to explain a re-plan."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import Plan, World


@dataclass(frozen=True)
class JobChange:
    job_id: str
    field_id: str
    job_type: str
    priority: int
    before: str  # tractor id, "unassignable" or "unplanned"
    after: str
    reason: str | None = None
    progress: float = 0.0


@dataclass(frozen=True)
class PlanDiff:
    trigger: dict
    time: float
    changes: tuple[JobChange, ...]
    queues_before: dict[str, tuple[str, ...]]
    queues_after: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict:
        return asdict(self)


def _owner_map(plan: Plan | None) -> dict[str, str]:
    if plan is None:
        return {}
    owners = {jid: tid for tid, q in plan.queues.items() for jid in q}
    owners.update({jid: "unassignable" for jid in plan.unassignable})
    return owners


def diff_plans(world: World, before: Plan | None, after: Plan, trigger: dict, released: dict[str, str]) -> PlanDiff:
    """`released` maps job ids freed by the trigger to their former tractor."""
    old = {**_owner_map(before), **released}
    new = _owner_map(after)
    changes = []
    for jid in sorted(set(old) | set(new)):
        b, a = old.get(jid, "unplanned"), new.get(jid, "unplanned")
        if b == a:
            continue
        job = world.jobs[jid]
        changes.append(
            JobChange(
                job_id=jid,
                field_id=job.field_id,
                job_type=job.type,
                priority=job.priority,
                before=b,
                after=a,
                reason=after.unassignable.get(jid),
                progress=round(job.progress, 2),
            )
        )
    return PlanDiff(
        trigger=trigger,
        time=round(world.time, 2),
        changes=tuple(changes),
        queues_before=dict(before.queues) if before else {},
        queues_after=dict(after.queues),
    )
