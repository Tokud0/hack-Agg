"""Runs a scenario under one strategy: live (tick by tick) or to completion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Literal

from . import agents, baseline
from .coordinator import PRIORITY_WEIGHT
from .diff import diff_plans
from .models import Job, JobStatus, TractorStatus, World, clock_time
from .replan import (
    WORK_NAME,
    block_road,
    break_tractor,
    change_priority,
    hold_for_weather,
    on_closed_stretch,
    replan,
    reroute_in_transit,
    weather_holds,
)
from .routing import RoadNetwork, build_network
from .scenario import EventIn, ScenarioIn, to_world
from .simulator import DEFAULT_DT, is_finished, step

Strategy = Literal["coordinator", "baseline", "edf"]
BASELINE_RULES: dict[str, baseline.Rule] = {"baseline": "fcfs", "edf": "edf"}
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
    # Record the agents' conversation of every re-plan (costs one extra planner round).
    record_messages: bool = False


def _with_log(run: Run, *entries: LogEntry) -> Run:
    return replace(run, log=run.log + entries)


def _replan_entry(run: Run, trigger: dict, released: dict[str, str]) -> Run:
    open_jobs = sorted(j.id for j in run.world.jobs.values() if j.status != JobStatus.DONE)
    available = sorted(t.id for t in run.world.tractors.values() if t.status != TractorStatus.BROKEN)
    result = replan(run.world, run.network, agents.Recorder if run.record_messages else None)
    diff = diff_plans(result.world, result.previous_plan, result.plan, trigger, released)
    messages = agents.transcript(run.world, run.network, trigger, released, result) if run.record_messages else ()
    entry = LogEntry(
        time=round(run.world.time, 2),
        kind="replan",
        message=f"Re-planned in {result.duration_ms:.1f} ms after {trigger['type']}"
        + ("" if result.accepted else " — REJECTED, kept last valid plan"),
        data={
            "duration_ms": round(result.duration_ms, 2),
            "accepted": result.accepted,
            "invariants": {
                "checked": list(result.report.checked),
                "violations": list(result.report.violations),
                "warnings": list(result.report.warnings),
            },
            "diff": diff.to_dict(),
            "messages": [asdict(m) for m in messages],
            "trace": {
                "sense": {
                    "open_jobs": open_jobs,
                    "tractors_available": available,
                    "released": sorted(released),
                    "blocked_roads": len(run.world.blocked_roads),
                },
                "agronomy": {"holds": weather_holds(run.world)},
                "navigate": {
                    "locations": len(run.world.node_ids()),
                    "roads_closed": sorted(sorted(road) for road in run.world.blocked_roads),
                },
                "plan": {
                    "duration_ms": round(result.duration_ms, 2),
                    "score": round(result.plan.score, 1),
                    "candidates": [asdict(c) for c in result.candidates],
                },
                "verify": {"duration_ms": round(result.verify_ms, 2), "accepted": result.accepted},
                "dispatch": {
                    "jobs_changed": len(diff.changes),
                    "unassignable": sorted(result.plan.unassignable),
                },
            },
        },
    )
    return replace(
        _with_log(run, entry),
        world=result.world,
        violations_total=run.violations_total + len(result.report.violations),
        replans=run.replans + 1,
    )


def start(
    scenario: ScenarioIn, strategy: Strategy, with_demo_events: bool = True, record_messages: bool = False
) -> Run:
    world = to_world(scenario)
    run = Run(
        strategy=strategy,
        world=world,
        network=build_network(world),
        record_messages=record_messages,
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
        caught = [tid for tid in sorted(world.tractors) if on_closed_stretch(world, tid, event.a, event.b)]
        blocked = block_road(world, event.a, event.b)
        world = reroute_in_transit(blocked, build_network(blocked))
        message = f"Road {event.a}–{event.b} closed" + (
            f"; {', '.join(caught)} already on it, finishing that stretch" if caught else ""
        )
        trigger = {**trigger, "caught_on_road": caught}
    elif event.type == "change_priority" and event.job_id and event.priority:
        if world.jobs[event.job_id].status == JobStatus.DONE:  # too late to matter; finished work is never touched
            return run
        world = change_priority(world, event.job_id, event.priority)
        message = f"{event.job_id} priority set to P{event.priority}"
    elif event.type == "weather" and event.job_type:
        until = event.until if event.until is not None else world.time + (event.hours or 0.0)
        world = hold_for_weather(world, event.job_type, until, run.network)
        trigger = {**trigger, "until": round(until, 2)}
        message = f"Weather: no {WORK_NAME[event.job_type]} until {clock_time(until)}"
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

    rule = BASELINE_RULES.get(run.strategy)
    world = baseline.dispatch(run.world, run.network, rule) if rule else run.world
    world, events = step(world, run.network, dt)
    entries = tuple(
        LogEntry(round(e.time, 2), e.kind, _sim_message(e.kind, e.tractor_id, e.job_id), {"tractor_id": e.tractor_id, "job_id": e.job_id})
        for e in events
    )
    return _with_log(replace(run, world=world), *entries)


SIM_MESSAGES = {
    "job_started": "{t} started {j}",
    "job_done": "{t} finished {j}",
    "refuel_started": "{t} refuelling at the depot before {j}",
    "refueled": "{t} refuelled, heading to {j}",
    "weather_hold": "{t} standing by at the field: the weather does not allow {j} yet",
}


def _sim_message(kind: str, tractor_id: str, job_id: str | None) -> str:
    return SIM_MESSAGES.get(kind, "{t} {j}").format(t=tractor_id, j=job_id)


def finished(run: Run) -> bool:
    if run.pending_events:
        return False
    rule = BASELINE_RULES.get(run.strategy)
    if rule:
        dispatched = baseline.dispatch(run.world, run.network, rule)
        return is_finished(dispatched) and not any(t.queue for t in dispatched.tractors.values())
    return is_finished(run.world)


def finalize(run: Run) -> Run:
    """Persist the baselines' last dispatch, so leftover jobs get their final status."""
    rule = BASELINE_RULES.get(run.strategy)
    return replace(run, world=baseline.dispatch(run.world, run.network, rule)) if rule else run


def run_to_end(run: Run, dt: float = DEFAULT_DT) -> Run:
    while not finished(run) and run.world.time < MAX_HORIZON_HOURS:
        run = tick(run, dt)
    return finalize(run)


def metrics(run: Run) -> dict:
    jobs = run.world.jobs.values()
    on_time = [j for j in jobs if j.status == JobStatus.DONE and j.completed_at is not None and j.completed_at <= j.deadline + 1e-6]
    travel = sum(t.travel_time for t in run.world.tractors.values())
    return {
        "jobs_total": len(run.world.jobs),
        "jobs_completed": len(on_time),
        "priority1_completed": sum(1 for j in on_time if j.priority == 1),
        "priority_score": sum(PRIORITY_WEIGHT[j.priority] for j in on_time),
        "refuel_stops": sum(t.refuels for t in run.world.tractors.values()),
        "travel_hours": round(travel, 2),
        # Driving spent per job finished on time; 0 until the first job is done.
        "travel_per_job": round(travel / len(on_time), 2) if on_time else 0.0,
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
