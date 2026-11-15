"""FastAPI app: live session clock, WebSocket state stream, operator actions."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from fleet.engine import log_as_dicts, metrics  # noqa: E402
from fleet.scenario import EventIn, ScenarioIn  # noqa: E402
from fleet.why import explain_assignment  # noqa: E402
from llm.assistant import answer_why, ask_tractor, copilot, llm_provider, narrate_what_if, parse_jobs  # noqa: E402
from scripts.benchmark import run_benchmark  # noqa: E402

from .session import ALLOWED_SPEEDS, FRAME_SECONDS, Session, reset_runs  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

state: dict[str, Session] = {}
MIN_DEADLINE_MARGIN_H = 0.5


def session() -> Session:
    return state["session"]


async def clock() -> None:
    loop = asyncio.get_running_loop()
    last = loop.time()
    while True:
        await asyncio.sleep(FRAME_SECONDS)
        now = loop.time()
        async with session().lock:
            try:
                session().advance(now - last)
            except Exception:
                logger.exception("simulation tick failed; pausing")
                session().running = False
        last = now


@asynccontextmanager
async def lifespan(_: FastAPI):
    state["session"] = Session.create()
    task = asyncio.create_task(clock())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="Run the Fleet — Coordinator", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ControlIn(BaseModel):
    action: Literal["play", "pause", "reset", "speed"]
    speed: float | None = None


class EventRequest(BaseModel):
    type: Literal["breakdown", "block_road", "change_priority"]
    tractor_id: str | None = None
    a: str | None = None
    b: str | None = None
    job_id: str | None = None
    priority: int | None = Field(default=None, ge=1, le=3)
    source: Literal["operator", "copilot"] = "operator"  # "telemetry" is set by the server only


class ChatTurn(BaseModel):
    role: Literal["operator", "copilot"]
    text: str = Field(max_length=1000)


class CopilotIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class JobRequest(BaseModel):
    type: Literal["spray", "mow"]
    field_id: str
    priority: int = Field(ge=1, le=3)
    deadline: float = Field(gt=0, le=24)
    work_hours: float = Field(gt=0, le=8)


class JobTextIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@app.get("/api/health")
def health() -> dict:
    provider = llm_provider()
    return {"ok": True, "llm": provider != "offline", "provider": provider}


@app.get("/api/map")
def get_map() -> dict:
    return session().map_view()


@app.get("/api/state")
def get_state() -> dict:
    return session().view()


@app.websocket("/api/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(session().view())
            await asyncio.sleep(FRAME_SECONDS)
    except (WebSocketDisconnect, RuntimeError):
        return


@app.post("/api/control")
async def control(body: ControlIn) -> dict:
    async with session().lock:
        s = session()
        if body.action == "play":
            s.running = True
        elif body.action == "pause":
            s.running = False
        elif body.action == "reset":
            state["session"] = reset_runs(s)
        elif body.action == "speed":
            if body.speed not in ALLOWED_SPEEDS:
                raise HTTPException(422, f"speed must be one of {ALLOWED_SPEEDS}")
            s.speed = body.speed
    return {"running": session().running, "speed": session().speed}


@app.post("/api/events")
async def post_event(body: EventRequest) -> dict:
    async with session().lock:
        try:
            session().apply_event(EventIn(at=0, **body.model_dump()))
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
    last = session().runs["coordinator"].log[-1]
    return {"ok": True, "replan": last.data if last.kind == "replan" else None}


class ScheduledFaultIn(BaseModel):
    tractor_id: str
    delay_hours: float = Field(gt=0, le=6)


@app.post("/api/events/schedule")
async def schedule_fault(body: ScheduledFaultIn) -> dict:
    """Nobody clicks when it happens: the fault arrives on the clock and the fleet recovers by itself."""
    async with session().lock:
        try:
            at = session().schedule_fault(body.tractor_id, body.delay_hours)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "at": at}


@app.get("/api/why/{job_id}")
async def why(job_id: str, question: str | None = None) -> dict:
    run = session().runs["coordinator"]
    if job_id not in run.world.jobs:
        raise HTTPException(404, f"unknown job {job_id}")
    facts = explain_assignment(run.world, run.network, job_id)
    answer, source = await asyncio.to_thread(answer_why, facts, question)
    return {"facts": facts, "answer": answer, "source": source}


@app.post("/api/copilot")
async def post_copilot(body: CopilotIn) -> dict:
    history = [t.model_dump() for t in body.history]
    reply, source = await asyncio.to_thread(copilot, body.message, session().copilot_state(), history)
    return {"reply": reply.reply, "events": [e.model_dump(exclude_none=True) for e in reply.events], "source": source}


@app.post("/api/jobs")
async def add_job(body: JobRequest) -> dict:
    async with session().lock:
        try:
            job_id = session().add_job(body.type, body.field_id, body.priority, body.deadline, body.work_hours)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "job_id": job_id}


@app.post("/api/jobs/parse")
async def parse_job_text(body: JobTextIn) -> dict:
    s = session()
    fields = sorted(s.runs["coordinator"].world.fields)
    now = s.runs["coordinator"].world.time
    drafts, source = await asyncio.to_thread(parse_jobs, body.text, fields, s.scenario.shift_start_hour, now)
    valid = [
        {**d.model_dump(), "deadline_hours": round(max(d.deadline_hours, now + d.work_hours + MIN_DEADLINE_MARGIN_H), 2)}
        for d in drafts.jobs
        if d.field_id in fields and 1 <= d.priority <= 3 and 0 < d.work_hours <= 8
    ]
    return {"jobs": valid, "note": drafts.note, "source": source}


@app.post("/api/scenario")
async def load_scenario_json(body: ScenarioIn) -> dict:
    async with session().lock:
        state["session"] = reset_runs(session(), body)
    return {"ok": True, "scenario": body.name, "jobs": len(body.jobs)}


@app.post("/api/whatif")
async def what_if(body: EventRequest) -> dict:
    try:
        facts = session().what_if(EventIn(at=0, **body.model_dump()))
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    narration, source = await asyncio.to_thread(narrate_what_if, facts)
    return {"facts": facts, "headline": narration.headline, "answer": narration.answer, "source": source}


class AgentQuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    # Log index of the planning round the question is about; the latest round when omitted.
    replan_index: int | None = Field(default=None, ge=0)


@app.post("/api/agents/{tractor_id}/ask")
async def ask_agent(tractor_id: str, body: AgentQuestionIn) -> dict:
    try:
        facts = session().agent_facts(tractor_id, body.replan_index)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0])) from exc
    answer, source = await asyncio.to_thread(ask_tractor, facts, body.question)
    return {"answer": answer, "source": source}


@app.post("/api/orchestration/fault-test")
async def orchestration_fault_test() -> dict:
    try:
        return session().fault_test()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/export")
def export() -> dict:
    s = session()
    return {
        "scenario": s.scenario.model_dump(),
        "runs": {
            name: {"metrics": metrics(run), "log": log_as_dicts(run)} for name, run in s.runs.items()
        },
        "explanations": s.explanations,
    }


@lru_cache(maxsize=1)
def _benchmark() -> dict:
    return run_benchmark(50)


@app.get("/api/benchmark")
async def benchmark() -> dict:
    result = await asyncio.to_thread(_benchmark)
    return {k: v for k, v in result.items() if k != "rows"}
