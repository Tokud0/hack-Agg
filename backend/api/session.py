"""Live demo session: baseline and coordinator run side by side on one clock."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from fleet import engine
from fleet.engine import Run
from fleet.scenario import EventIn, ScenarioIn, load_scenario
from fleet.models import Job
from fleet.replan import fault_test
from fleet.whatif import forecast
from llm.assistant import explain_replan

from .serialize import snapshot, static_map

logger = logging.getLogger(__name__)

SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"
FRAME_SECONDS = 0.1
SIM_HOURS_PER_SECOND_AT_1X = 0.15  # a 10 h shift plays in ~67 s at 1x
ALLOWED_SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0)


@dataclass
class Session:
    scenario: ScenarioIn
    runs: dict[str, Run]
    running: bool = False
    speed: float = 1.0
    explanations: dict[int, dict] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _explaining: set[int] = field(default_factory=set)

    @classmethod
    def create(cls, scenario: ScenarioIn | None = None) -> "Session":
        scenario = scenario or load_scenario(SCENARIO_PATH)
        runs = {s: engine.start(scenario, s, with_demo_events=False, record_messages=True) for s in ("baseline", "edf", "coordinator")}
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
        return {
            "running": self.running,
            "speed": self.speed,
            "scenario": self.scenario.name,
            "runs": {name: snapshot(run) for name, run in self.runs.items()},
            "explanations": {str(k): v for k, v in self.explanations.items()},
            "scheduled_faults": [
                {"tractor_id": e.tractor_id, "at": e.at} for e in self.runs["coordinator"].pending_events
            ],
        }

    def map_view(self) -> dict:
        return {
            **static_map(self.runs["coordinator"].world),
            "speeds": list(ALLOWED_SPEEDS),
            "shift_start_hour": self.scenario.shift_start_hour,
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
        world = self.runs["coordinator"].world
        return {
            "time_h": round(world.time, 2),
            "tractors": {
                t.id: {"implement": t.implement.value, "status": t.status.value, "fuel": round(t.fuel),
                       "current_job": t.current_job, "queue": list(t.queue)}
                for t in world.tractors.values()
            },
            "jobs": {
                j.id: {"type": j.type, "field": j.field_id, "priority": j.priority, "deadline": j.deadline,
                       "status": j.status.value, "tractor": j.tractor_id, "reason": j.reason}
                for j in world.jobs.values()
            },
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


def _next_job_id(jobs: dict) -> str:
    numbers = [int(j[1:]) for j in jobs if j[1:].isdigit()]
    return f"J{max(numbers, default=0) + 1:02d}"


def reset_runs(session: Session, scenario: ScenarioIn | None = None) -> Session:
    return replace(Session.create(scenario or session.scenario), speed=session.speed)
