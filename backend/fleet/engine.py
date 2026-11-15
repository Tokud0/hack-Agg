"""Runs a scenario under one strategy: live (tick by tick) or to completion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from . import baseline
from .diff import diff_plans
from .models import Job, JobStatus, World
from .replan import block_road, break_tractor, change_priority, replan
from .routing import RoadNetwork, build_network
from .scenario import EventIn, ScenarioIn, to_world
from .simulator import DEFAULT_DT, is_finished, step

Strategy = Literal["coordinator", "baseline"]
MAX_HORIZON_HOURS = 24.0


@dataclass(frozen=True)
class LogEntry:
    time: float
    kind: str
    message: str
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Run:
    strategy: Strategy
    world: World
    network: RoadNetwork
    log: tuple[LogEntry, ...] = ()
    pending_events: tuple[EventIn, ...] = ()
    violations_total: int = 0
    replans: int = 0


def _with_log(run: Run, *entries: LogEntry) -> Run:
    return replace(run, log=run.log + entries)


def _replan_entry(run: Run, trigger: dict, released: dict[str, str]) -> Run:
    result = replan(run.world, run.network)
    diff = diff_plans(result.world, result.previous_plan, result.plan, trigger, released)
    entry = LogEntry(
        time=round(run.world.time, 2),
        kind="replan",
        message=f"Re-planned in {result.duration_ms:.1f} ms after {trigger['type']}"
        + ("" if result.accepted else " — REJECTED, kept last valid plan"),
        data={
            "duration_ms": round(result.duration_ms, 2),
            "accepted": result.accepted,
            "invariants": {"checked": list(result.report.checked), "violations": list(result.report.violations)},
            "diff": diff.to_dict(),
        },
    )
    return replace(
        _with_log(run, entry),
        world=result.world,
        violations_total=run.violations_total + len(result.report.violations),
        replans=run.replans + 1,
    )


def start(scenario: ScenarioIn, strategy: Strategy, with_demo_events: bool = True) -> Run:
    world = to_world(scenario)
    run = Run(
        strategy=strategy,
        world=world,
        network=build_network(world),
        pending_events=tuple(sorted(scenario.demo_events, key=lambda e: e.at)) if with_demo_events else (),
    )
    run = _with_log(run, LogEntry(0.0, "start", f"Shift started ({strategy})"))
    if strategy == "coordinator":
        run = _replan_entry(run, {"type": "initial_plan"}, {})
    return run


def apply_event(run: Run, event: EventIn) -> Run:
    world = run.world
    trigger = event.model_dump(exclude_none=True)
    released: dict[str, str] = {}
    if event.type == "breakdown" and event.tractor_id:
        if world.tractors[event.tractor_id].status.value == "broken":
            return run
        tractor = world.tractors[event.tractor_id]
        held = (*([tractor.current_job] if tractor.current_job else []), *tractor.queue)
        released = {jid: tractor.id for jid in held}
        world = break_tractor(world, event.tractor_id)
        message = f"{event.tractor_id} broke down" + (f", released {', '.join(held)}" if held else "")
    elif event.type == "block_road" and event.a and event.b:
        world = block_road(world, event.a, event.b)
        message = f"Road {event.a}–{event.b} closed"
    elif event.type == "change_priority" and event.job_id and event.priority:
        world = change_priority(world, event.job_id, event.priority)
        message = f"{event.job_id} priority set to P{event.priority}"
    else:
        raise ValueError(f"invalid event: {trigger}")

    network = build_network(world) if event.type == "block_road" else run.network
    run = _with_log(replace(run, world=world, network=network), LogEntry(round(world.time, 2), "event", message, trigger))
    if run.strategy == "coordinator":
        run = _replan_entry(run, trigger, released)
    return run


def tick(run: Run, dt: float = DEFAULT_DT) -> Run:
    while run.pending_events and run.pending_events[0].at <= run.world.time + 1e-9:
        event, rest = run.pending_events[0], run.pending_events[1:]
        run = apply_event(replace(run, pending_events=rest), event)

    world = baseline.dispatch(run.world, run.network) if run.strategy == "baseline" else run.world
    world, events = step(world, run.network, dt)
    entries = tuple(
        LogEntry(round(e.time, 2), e.kind, f"{e.tractor_id} {'started' if e.kind == 'job_started' else 'finished'} {e.job_id}")
        for e in events
    )
    return _with_log(replace(run, world=world), *entries)


def finished(run: Run) -> bool:
    if run.pending_events:
        return False
    if run.strategy == "baseline":
        dispatched = baseline.dispatch(run.world, run.network)
        return is_finished(dispatched) and not any(t.queue for t in dispatched.tractors.values())
    return is_finished(run.world)


def run_to_end(run: Run, dt: float = DEFAULT_DT) -> Run:
    while not finished(run) and run.world.time < MAX_HORIZON_HOURS:
        run = tick(run, dt)
    return run


def metrics(run: Run) -> dict:
    jobs = run.world.jobs.values()
    on_time = [j for j in jobs if j.status == JobStatus.DONE and j.completed_at is not None and j.completed_at <= j.deadline + 1e-6]
    return {
        "jobs_total": len(run.world.jobs),
        "jobs_completed": len(on_time),
        "priority1_completed": sum(1 for j in on_time if j.priority == 1),
        "travel_hours": round(sum(t.travel_time for t in run.world.tractors.values()), 2),
        "idle_hours": round(sum(t.idle_time for t in run.world.tractors.values()), 2),
        "unassignable": sum(1 for j in jobs if j.status == JobStatus.UNASSIGNABLE),
        "invariant_violations": run.violations_total,
        "replans": run.replans,
        "makespan_hours": round(run.world.time, 2),
    }


def log_as_dicts(run: Run) -> list[dict]:
    return [asdict(e) for e in run.log]


def add_job(run: Run, job: Job) -> Run:
    """Operator adds work mid-shift; the coordinator re-plans, the baseline queues it."""
    if job.id in run.world.jobs:
        raise ValueError(f"job {job.id} already exists")
    if job.field_id not in run.world.fields:
        raise ValueError(f"unknown field {job.field_id}")
    world = replace(run.world, jobs={**run.world.jobs, job.id: job})
    trigger = {"type": "add_job", "job_id": job.id, "field_id": job.field_id, "priority": job.priority}
    entry = LogEntry(round(world.time, 2), "event", f"New job {job.id}: {job.type} {job.field_id}, P{job.priority}", trigger)
    run = _with_log(replace(run, world=world), entry)
    if run.strategy == "coordinator":
        run = _replan_entry(run, trigger, {})
    return run
