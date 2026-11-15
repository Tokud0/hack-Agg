"""Live demo session: baseline and coordinator run side by side on one clock."""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import uuid4
from dataclasses import dataclass, field, replace
from pathlib import Path

from fleet import engine
from fleet.engine import Run
from fleet.scenario import EventIn, ScenarioIn, load_scenario
from fleet.generate import SURPRISE, clock
from fleet.models import Job
from fleet.replan import fault_test, weather_holds
from fleet.risk import at_risk
from fleet.whatif import forecast
from llm.assistant import explain_replan

from .serialize import snapshot, static_map

logger = logging.getLogger(__name__)

SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"
FRAME_SECONDS = 0.1
SIM_HOURS_PER_SECOND_AT_1X = 0.15  # a 10 h shift plays in ~67 s at 1x
ALLOWED_SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0)
LOW_FUEL_SHARE = 0.2


@dataclass
class Session:
    scenario: ScenarioIn
    runs: dict[str, Run]
    running: bool = False
    speed: float = 1.0
    # Changes on every restart or new scenario, so clients can tell a new shift from a longer log.
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    explanations: dict[int, dict] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _explaining: set[int] = field(default_factory=set)

    @classmethod
    def create(cls, scenario: ScenarioIn | None = None) -> "Session":
        scenario = scenario or load_scenario(SCENARIO_PATH)
        runs = {s: engine.start(scenario, s, with_demo_events=scenario.auto_events, record_messages=True) for s in ("baseline", "edf", "coordinator")}
        session = cls(scenario=scenario, runs=runs)
        session.schedule_explanations()
        return session

    # --- clock -------------------------------------------------------------

    def advance(self, real_seconds: float) -> None:
        if not self.running:
            return
        dt = real_seconds * SIM_HOURS_PER_SECOND_AT_1X * self.speed
        self.runs = {
            name: (engine.finalize(run) if engine.finished(run) else engine.tick(run, dt)) for name, run in self.runs.items()
        }
        if all(engine.finished(r) for r in self.runs.values()):
            self.running = False
        self.schedule_explanations()  # a scheduled fault may have just fired and re-planned

    # --- events ------------------------------------------------------------

    def apply_event(self, event: EventIn) -> None:
        coordinator = self.runs["coordinator"]
        _validate_event(coordinator, event)
        event = event.model_copy(update={"at": coordinator.world.time})
        self.runs = {name: engine.apply_event(run, event) for name, run in self.runs.items()}
        self.schedule_explanations()

    def schedule_fault(self, tractor_id: str, delay_hours: float) -> float:
        """A fault that arrives by itself, as tractor telemetry would report it. Returns its time."""
        coordinator = self.runs["coordinator"]
        event = EventIn(at=0, type="breakdown", tractor_id=tractor_id)
        _validate_event(coordinator, event)
        at = round(coordinator.world.time + delay_hours, 2)
        fault = event.model_copy(update={"at": at, "source": "telemetry"})
        self.runs = {
            name: replace(run, pending_events=tuple(sorted((*run.pending_events, fault), key=lambda e: e.at)))
            for name, run in self.runs.items()
        }
        return at

    def add_job(self, job_type: str, field_id: str, priority: int, deadline: float, work_hours: float) -> str:
        world = self.runs["coordinator"].world
        if field_id not in world.fields:
            raise ValueError(f"unknown field {field_id}")
        if deadline <= world.time + work_hours:
            raise ValueError("deadline is too early for this much work")
        job_id = _next_job_id(world.jobs)
        job = Job(id=job_id, type=job_type, field_id=field_id, priority=priority, deadline=deadline,
                  work_hours=work_hours, remaining_hours=work_hours)
        self.runs = {name: engine.add_job(run, job) for name, run in self.runs.items()}
        self.schedule_explanations()
        return job_id

    def what_if(self, event: EventIn) -> dict:
        coordinator = self.runs["coordinator"]
        _validate_event(coordinator, event)
        return forecast(coordinator, event)

    def fault_test(self) -> dict:
        """Show the safety gate a corrupted plan; the live plan is untouched."""
        coordinator = self.runs["coordinator"]
        result = fault_test(coordinator.world, coordinator.network)
        if result is None:
            raise ValueError("nothing is planned yet, so there is no plan to corrupt")
        return {
            "fault": result.fault,
            "accepted": result.report.ok,
            "checked": list(result.report.checked),
            "violations": list(result.report.violations),
        }

    # --- explanations (async, never block the clock) -----------------------

    def schedule_explanations(self) -> None:
        for i, entry in enumerate(self.runs["coordinator"].log):
            if entry.kind != "replan" or i in self.explanations or i in self._explaining:
                continue
            self._explaining.add(i)
            try:
                asyncio.get_running_loop().create_task(self._explain(i, entry.data["diff"]))
            except RuntimeError:  # no loop yet (startup): explain synchronously via template path
                self._store(i, *explain_replan(entry.data["diff"]))

    async def _explain(self, index: int, diff: dict) -> None:
        try:
            started = time.perf_counter()
            explanation, source = await asyncio.to_thread(explain_replan, diff)
            self._store(index, explanation, source, (time.perf_counter() - started) * 1000)
        except Exception:  # explanation must never take the demo down
            logger.exception("explanation %s failed", index)
        finally:
            self._explaining.discard(index)

    def _store(self, index: int, explanation, source: str, latency_ms: float = 0.0) -> None:
        entry = {**explanation.model_dump(), "source": source, "latency_ms": round(latency_ms)}
        self.explanations = {**self.explanations, index: entry}

    # --- views -------------------------------------------------------------

    def view(self) -> dict:
        pending = self.runs["coordinator"].pending_events
        return {
            "running": self.running,
            "speed": self.speed,
            "session_id": self.id,
            "scenario": self.scenario.name,
            "runs": {name: snapshot(run) for name, run in self.runs.items()},
            "explanations": {str(k): v for k, v in self.explanations.items()},
            "weather_holds": weather_holds(self.runs["coordinator"].world),
            "scheduled_faults": [
                {"tractor_id": e.tractor_id, "at": e.at} for e in pending if e.source != SURPRISE
            ],
            # How many generated events are still to come; what and when stays a surprise.
            "surprises_left": sum(1 for e in pending if e.source == SURPRISE),
        }

    def map_view(self) -> dict:
        return {
            **static_map(self.runs["coordinator"].world),
            "speeds": list(ALLOWED_SPEEDS),
            "shift_start_hour": self.scenario.shift_start_hour,
        }

    def briefing_facts(self) -> dict:
        """Verified numbers for the shift briefing, plus the items that need the manager's eye."""
        run = self.runs["coordinator"]
        world = run.world
        start = self.scenario.shift_start_hour
        ours, theirs = engine.metrics(run), engine.metrics(self.runs["baseline"])
        statuses = [j.status.value for j in world.jobs.values()]
        attention = [
            *({"kind": "broken", "id": t.id, "text": f"{t.id} is broken down"}
              for t in world.tractors.values() if t.status.value == "broken"),
            *({"kind": "lost", "id": j.id, "text": f"{j.id} (P{j.priority}, {j.field_id}) cannot be done: {j.reason}"}
              for j in world.jobs.values() if j.status.value == "unassignable"),
            *({"kind": "at_risk", "id": o.job_id,
               "text": f"{o.job_id} finishes at {clock(o.finish, start)}, {abs(round(o.slack * 60))} min "
                       f"{'after' if o.slack < 0 else 'before'} its deadline"}
              for o in at_risk(world, run.network)),
            *({"kind": "low_fuel", "id": t.id, "text": f"{t.id} is at {t.fuel / t.fuel_capacity:.0%} fuel"}
              for t in world.tractors.values() if t.status.value != "broken" and t.fuel < LOW_FUEL_SHARE * t.fuel_capacity),
        ]
        return {
            "scenario": self.scenario.name,
            "clock": clock(world.time, start),
            "jobs": {
                "total": len(statuses),
                "done_on_time": ours["jobs_completed"],
                "in_progress": statuses.count("in_progress"),
                "waiting": statuses.count("assigned") + statuses.count("pending"),
                "not_doable": statuses.count("unassignable"),
            },
            "versus_first_come_first_served": {
                "jobs_done_on_time": [ours["jobs_completed"], theirs["jobs_completed"]],
                "urgent_done": [ours["priority1_completed"], theirs["priority1_completed"]],
                "idle_hours": [ours["idle_hours"], theirs["idle_hours"]],
            },
            "events": [f"{clock(e.time, start)} {e.message}" for e in run.log if e.kind == "event"],
            "attention": attention,
        }

    def agent_facts(self, tractor_id: str, replan_index: int | None = None) -> dict:
        """What one tractor agent knows: its current status and what it said and heard in one
        planning round (the latest, or the round at `replan_index` in the log)."""
        run = self.runs["coordinator"]
        if tractor_id not in run.world.tractors:
            raise KeyError(f"unknown tractor {tractor_id}")
        if replan_index is None:
            entry = next((e for e in reversed(run.log) if e.kind == "replan"), None)
        else:
            entry = run.log[replan_index] if 0 <= replan_index < len(run.log) else None
            if entry is None or entry.kind != "replan":
                raise KeyError(f"log entry {replan_index} is not a planning round")
        heard = entry.data.get("messages", []) if entry else []
        own_topics = {m["topic"] for m in heard if tractor_id in (m["sender"], m["to"]) and m["topic"]}

        def concerns_it(m: dict) -> bool:
            if tractor_id in (m["sender"], m["to"]):
                return True
            return m["to"] == "all" and (m["phase"] == "situation" or m["topic"] in own_topics)

        messages = [
            {"from": m["sender"], "to": m["to"], "kind": m["kind"], "job": m["topic"], "text": m["text"]}
            for m in heard if concerns_it(m)
        ]
        return {
            "tractor_id": tractor_id,
            "status_now": self.copilot_state()["tractors"][tractor_id],
            "round_time_h": entry.time if entry else None,
            "messages": messages,
        }

    def copilot_state(self) -> dict:
        """Everything the copilot may answer from. Counts and durations are worked out here, so the LLM reads them
        instead of counting or subtracting; times of day are clock strings."""
        run = self.runs["coordinator"]
        world = run.world
        start = self.scenario.shift_start_hour
        totals = engine.metrics(run)
        jobs = list(world.jobs.values())
        is_finished = engine.finished(run)

        def count(job_type: str | None, *statuses: str) -> int:
            return sum(1 for j in jobs if (job_type is None or j.type == job_type) and j.status.value in statuses)

        by_type = {
            job_type: {
                "total": count(job_type, "pending", "assigned", "in_progress", "done", "unassignable"),
                "done": count(job_type, "done"),
                "in_progress": count(job_type, "in_progress"),
                "waiting": count(job_type, "pending", "assigned"),
                "cannot_be_done": count(job_type, "unassignable"),
            }
            for job_type in sorted({j.type for j in jobs})
        }
        return {
            "time_h": round(world.time, 2),
            "clock_now": clock(world.time, start),
            "shift": {
                "started_at": clock(0, start),
                "is_finished": is_finished,
                "hours_elapsed": round(world.time, 2),
                # How long the whole shift took, known only once every job is done or given up.
                "total_duration_hours": round(world.time, 2) if is_finished else None,
                "ended_at": clock(world.time, start) if is_finished else None,
            },
            "totals": {
                "jobs": len(jobs),
                "done_on_time": totals["jobs_completed"],
                "done": count(None, "done"),
                "in_progress": count(None, "in_progress"),
                "waiting": count(None, "pending", "assigned"),
                "cannot_be_done": count(None, "unassignable"),
                "urgent_done_on_time": totals["priority1_completed"],
                "driving_hours": totals["travel_hours"],
                "idle_hours": totals["idle_hours"],
                "refuel_stops": totals["refuel_stops"],
                "replans": totals["replans"],
                "by_type": by_type,
            },
            "tractors": {
                t.id: {"implement": t.implement.value, "status": t.status.value, "fuel": round(t.fuel),
                       "fuel_capacity": round(t.fuel_capacity), "current_job": t.current_job, "queue": list(t.queue),
                       "hours_working": round(t.work_time, 2), "hours_driving": round(t.travel_time, 2)}
                for t in world.tractors.values()
            },
            "jobs": {
                j.id: {"type": j.type, "field": j.field_id, "priority": j.priority, "deadline": j.deadline,
                       "due_at": clock(j.deadline, start), "work_hours": j.work_hours,
                       "status": j.status.value, "tractor": j.tractor_id, "reason": j.reason,
                       "finished_at": clock(j.completed_at, start) if j.completed_at is not None else None}
                for j in jobs
            },
            "events": [f"{clock(e.time, start)} {e.message}" for e in run.log if e.kind == "event"],
            "nodes": [world.depot.id, *sorted(world.fields)],
        }


def _validate_event(run: Run, event: EventIn) -> None:
    world = run.world
    if event.type == "breakdown":
        if event.tractor_id not in world.tractors:
            raise ValueError(f"unknown tractor {event.tractor_id}")
        if world.tractors[event.tractor_id].status.value == "broken":
            raise ValueError(f"{event.tractor_id} is already broken")
    elif event.type == "block_road":
        nodes = set(world.node_ids())
        if event.a not in nodes or event.b not in nodes or event.a == event.b:
            raise ValueError(f"unknown road {event.a}–{event.b}")
    elif event.type == "change_priority":
        if event.job_id not in world.jobs:
            raise ValueError(f"unknown job {event.job_id}")
        if event.priority not in (1, 2, 3):
            raise ValueError("priority must be 1, 2 or 3")
        if world.jobs[event.job_id].status.value == "done":
            raise ValueError(f"{event.job_id} is already done")
    elif event.type == "weather":
        if event.job_type is None or event.hours is None:
            raise ValueError("say which work the weather holds (spray or mow) and for how many hours")


def _next_job_id(jobs: dict) -> str:
    numbers = [int(j[1:]) for j in jobs if j[1:].isdigit()]
    return f"J{max(numbers, default=0) + 1:02d}"


def reset_runs(session: Session, scenario: ScenarioIn | None = None) -> Session:
    return replace(Session.create(scenario or session.scenario), speed=session.speed)
