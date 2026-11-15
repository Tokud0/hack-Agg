"""Incident Response Agent: after the fleet has recovered by itself, an LLM agent investigates the
incident with real tool calls and files a review for the manager.

It never changes the plan. Recovery is done by the deterministic planner before this agent starts,
so the fleet keeps working whether or not a model is reachable. Every tool here is read-only.
When no model answers, the same tools are run in a fixed order and the review is rule-based; the
record says which of the two happened.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, field_validator

from fleet import engine
from fleet.models import clock_time
from fleet.risk import at_risk, outlook
from llm import provider
from llm.tool_agent import AgentRun, NoArguments, Tool, call_tool, run_agent

if TYPE_CHECKING:
    from .session import Session

FINISH_TOOL = "file_incident_review"

SYSTEM = """You are the Incident Response Agent of an autonomous tractor fleet.
An incident has just happened and the fleet has ALREADY re-planned by itself; a safety check has passed.
You cannot change the plan. Your job is to investigate and tell the fleet manager what matters.
Work with the tools:
1. Call get_incident first.
2. Call at least two more tools to check the consequences (the fleet, a specific job, deadline risk, the forecast).
3. Call file_incident_review exactly once, and stop.
Use only facts the tools returned: job, field and tractor ids and clock times exactly as given.
finding: at most 2 sentences. recommendation: one sentence the manager can act on, or "No action needed."
severity: high if urgent (P1) work is lost or will be late, medium if any job is lost or at risk, low otherwise."""


class JobQuery(BaseModel):
    job_id: str = Field(description="A job id from the incident or the fleet snapshot, e.g. J05")


# Typographic characters some models emit; plain ones read the same and never show as boxes.
PLAIN = str.maketrans({"\u202f": " ", "\u00a0": " ", "\u2011": "-", "\u2013": "-", "\u2014": "-", "\u201c": '"', "\u201d": '"', "\u2019": "'"})


class IncidentReview(BaseModel):
    severity: Literal["low", "medium", "high"]
    finding: str = Field(max_length=600)
    recommendation: str = Field(max_length=400)

    @field_validator("finding", "recommendation")
    @classmethod
    def _plain_text(cls, text: str) -> str:
        return text.translate(PLAIN).strip()


def build_registry(session: Session, replan_index: int) -> dict[str, Tool]:
    """The tools the agent may use for one incident, bound to the live session. All of them only read."""
    start = session.scenario.shift_start_hour

    def at(hours: float) -> str:
        return clock_time(hours, start)

    def run():
        return session.runs["coordinator"]

    def get_incident(_: BaseModel) -> dict:
        entry = run().log[replan_index]
        diff = entry.data["diff"]
        return {
            "happened_at": at(entry.time),
            "trigger": {k: v for k, v in diff["trigger"].items() if k != "at"},
            "plan_accepted_by_safety_check": entry.data["accepted"],
            "replanned_in_ms": entry.data["duration_ms"],
            "changes": [
                {"job": c["job_id"], "field": c["field_id"], "priority": c["priority"], "from": c["before"],
                 "to": "cannot be done" if c["after"] == "unassignable" else c["after"], "reason": c["reason"]}
                for c in diff["changes"]
            ],
        }

    def get_fleet_snapshot(_: BaseModel) -> dict:
        world = run().world
        return {
            "clock": at(world.time),
            "tractors": [
                {"id": t.id, "implement": t.implement.value, "status": t.status.value, "fuel_percent": round(100 * t.fuel / t.fuel_capacity),
                 "current_job": t.current_job, "queue": list(t.queue)}
                for t in sorted(world.tractors.values(), key=lambda t: t.id)
            ],
        }

    def get_job_detail(query: BaseModel) -> dict:
        world = run().world
        job_id = getattr(query, "job_id", "")
        if job_id not in world.jobs:
            raise KeyError(f"unknown job {job_id}; jobs are {', '.join(sorted(world.jobs))}")
        job = world.jobs[job_id]
        ahead = outlook(world, run().network).get(job_id)
        return {
            "job": job.id, "type": job.type, "field": job.field_id, "priority": job.priority, "due": at(job.deadline),
            "status": "cannot be done" if job.status.value == "unassignable" else job.status.value,
            "tractor": job.tractor_id, "progress_percent": round(job.progress * 100), "reason": job.reason,
            "projected_finish": at(ahead.finish) if ahead else None,
            "spare_minutes_before_deadline": round(ahead.slack * 60) if ahead else None,
        }

    def evaluate_deadline_risk(_: BaseModel) -> dict:
        world = run().world
        return {
            "rule": "a job is at risk when the plan finishes it less than 30 minutes before its deadline",
            "at_risk": [
                {"job": o.job_id, "priority": world.jobs[o.job_id].priority, "tractor": o.tractor_id, "projected_finish": at(o.finish),
                 "due": at(o.deadline), "spare_minutes": round(o.slack * 60)}
                for o in at_risk(world, run().network)
            ],
        }

    def forecast_rest_of_shift(_: BaseModel) -> dict:
        """Play the rest of the shift on a copy; the live shift is not touched."""
        def finish(name: str) -> dict:
            return engine.metrics(engine.run_to_end(replace(session.runs[name], pending_events=(), record_messages=False)))
        ours, fcfs = finish("coordinator"), finish("baseline")
        ended = engine.run_to_end(replace(run(), pending_events=(), record_messages=False)).world
        return {
            "if_nothing_else_happens": {
                "jobs_done_on_time": ours["jobs_completed"], "jobs_total": ours["jobs_total"],
                "urgent_done_on_time": ours["priority1_completed"],
                "jobs_not_done": sorted(j.id for j in ended.jobs.values() if j.status.value != "done"),
            },
            "simple_first_come_first_served_dispatcher_on_the_same_shift": {
                "jobs_done_on_time": fcfs["jobs_completed"], "urgent_done_on_time": fcfs["priority1_completed"],
            },
        }

    def file_incident_review(review: BaseModel) -> dict:
        return {"filed": True}

    tools = [
        Tool("get_incident", "What happened, when, and what the automatic re-plan changed. Call this first.", NoArguments, get_incident),
        Tool("get_fleet_snapshot", "Every tractor right now: status, fuel, current job and queue.", NoArguments, get_fleet_snapshot),
        Tool("get_job_detail", "One job: priority, deadline, status, who has it, projected finish and spare time.", JobQuery, get_job_detail),
        Tool("evaluate_deadline_risk", "Jobs the current plan finishes less than 30 minutes before their deadline.", NoArguments, evaluate_deadline_risk),
        Tool("forecast_rest_of_shift", "Simulate the rest of the shift on a copy: how many jobs will be done on time, which will not, and how a simple dispatcher would do.", NoArguments, forecast_rest_of_shift),
        Tool(FINISH_TOOL, "File your review for the fleet manager. Call exactly once, last.", IncidentReview, file_incident_review),
    ]
    return {tool.name: tool for tool in tools}


def _scripted_review(registry: dict[str, Tool]) -> AgentRun:
    """No model available: run the same tools in a fixed order and write the review by rule."""
    calls = [call_tool(registry, name, {}, chosen_by="script") for name in ("get_incident", "evaluate_deadline_risk", "forecast_rest_of_shift")]
    incident, risk, forecast = (c.result for c in calls)
    lost = [c for c in incident.get("changes", []) if c["to"] == "cannot be done"]
    moved = [c for c in incident.get("changes", []) if c["to"] != "cannot be done"]
    risky = risk.get("at_risk", [])
    outcome = forecast.get("if_nothing_else_happens", {})
    severity = "high" if any(c["priority"] == 1 for c in lost) else "medium" if lost or risky else "low"
    finding = (
        f"{len(moved)} job(s) moved to another tractor and {len(lost)} can no longer be done"
        + (f" ({', '.join(c['job'] for c in lost)})" if lost else "")
        + f". Forecast: {outcome.get('jobs_done_on_time', '?')} of {outcome.get('jobs_total', '?')} jobs on time."
    )
    recommendation = (
        f"Watch {', '.join(r['job'] for r in risky)}: little spare time before the deadline." if risky
        else "Decide whether the lost jobs can wait for the next shift." if lost else "No action needed."
    )
    review = IncidentReview(severity=severity, finding=finding, recommendation=recommendation)
    return AgentRun((*calls, call_tool(registry, FINISH_TOOL, review.model_dump(), chosen_by="script")), review.model_dump())


MIN_CALLS_TO_CONCLUDE = 2

FILE_SYSTEM = """Turn an incident investigation into the review form. You get the tool results the agent gathered and
whatever conclusion it wrote in plain text (it may be empty). Fill the form from them; add nothing that is not there.
finding: at most 2 sentences. recommendation: one sentence the manager can act on, or "No action needed."
severity: high if urgent (P1) work is lost or will be late, medium if any job is lost or at risk, low otherwise."""


def _file_from_findings(registry: dict[str, Tool], attempt: AgentRun) -> AgentRun:
    """The model investigated with tools but did not make the finishing call (it wrote text, or ran out of turns).
    Its findings are put into the review form by one more model call with a strict schema."""
    facts = json.dumps({"tool_results": [{"tool": c.tool, "result": c.result} for c in attempt.calls if c.ok], "conclusion": attempt.prose})
    review, _ = provider.structured(FILE_SYSTEM, facts, IncidentReview)
    if not isinstance(review, IncidentReview):
        return attempt
    filed = call_tool(registry, FINISH_TOOL, review.model_dump())
    return replace(attempt, calls=(*attempt.calls, filed), conclusion=filed.arguments if filed.ok else None)


def review_incident(session: Session, replan_index: int) -> dict:
    """Investigate one re-plan and return the record for the dashboard and the event log."""
    registry = build_registry(session, replan_index)
    source = provider.provider_name() or "template"
    attempt = run_agent(SYSTEM, "A new incident has been handled automatically. Investigate it and file your review.", registry, FINISH_TOOL) if source == "groq" else AgentRun()
    notes = attempt.notes
    if attempt.conclusion is None and sum(c.ok for c in attempt.calls) >= MIN_CALLS_TO_CONCLUDE:
        attempt = _file_from_findings(registry, attempt)
    if attempt.conclusion is None:  # no model, or it did not finish: fall back, and keep what it tried for the record
        scripted = _scripted_review(registry)
        attempt, source = replace(scripted, calls=(*attempt.calls, *scripted.calls)), "template"
    return {
        "source": source,
        "review": attempt.conclusion,
        "calls": [asdict(c) for c in attempt.calls],
        "notes": list(notes),
    }
