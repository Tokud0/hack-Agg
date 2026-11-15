"""Claude calls for explanations and the operator copilot.

The LLM never plans. It only (a) turns structured facts into plain language and
(b) translates operator text into typed events that the coordinator then
validates and executes. Every call has a deterministic template fallback, so
the demo works offline or without a key.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 4000

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic | None:
    global _client
    if _client is None and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        _client = anthropic.Anthropic(timeout=30.0, max_retries=1)
    return _client


def llm_available() -> bool:
    return _get_client() is not None


def _parse(system: str, user: str, schema: type[BaseModel]) -> BaseModel | None:
    """One structured call; returns None on any failure so callers fall back."""
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": "low"},
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
    except anthropic.APIConnectionError as exc:
        logger.warning("Claude unreachable: %s", exc)
        return None
    except anthropic.APIStatusError as exc:
        logger.warning("Claude API error %s: %s", exc.status_code, exc.message)
        return None
    if response.stop_reason == "refusal":
        logger.warning("Claude refused: %s", response.stop_details)
        return None
    return response.parsed_output


# --- re-plan explanation -----------------------------------------------------

EXPLAIN_SYSTEM = """You explain fleet re-plans to a farm operator.
You receive a JSON diff produced by a deterministic coordinator: the trigger, and per-job changes
(before -> after tractor, or 'unassignable' with the reason). Write for a busy operator:
- headline: max 8 words.
- summary: 2-3 short sentences. Say what happened, who took over which work, and what could not be done and why.
- Use only facts in the JSON. Never invent numbers. Refer to jobs, fields and tractors by their ids.
Hours are simulated hours since shift start."""


class Explanation(BaseModel):
    headline: str = Field(description="Max 8 words")
    summary: str = Field(description="2-3 short sentences for the operator")
    highlight_jobs: list[str] = Field(description="Job ids the dashboard should highlight")


def template_explanation(diff: dict) -> Explanation:
    trigger = diff.get("trigger", {})
    changes = diff.get("changes", [])
    moved = [c for c in changes if c["after"] not in ("unassignable", "unplanned") and c["before"] not in ("unplanned",)]
    dropped = [c for c in changes if c["after"] == "unassignable"]
    if trigger.get("type") == "initial_plan":
        per = {}
        for c in changes:
            per.setdefault(c["after"], []).append(c["job_id"])
        parts = [f"{t}: {', '.join(js)}" for t, js in sorted(per.items()) if t != "unassignable"]
        summary = "Initial plan. " + "; ".join(parts) + "."
        if dropped:
            summary += f" Cannot be done: {', '.join(c['job_id'] for c in dropped)}."
        return Explanation(headline="Initial plan ready", summary=summary, highlight_jobs=[c["job_id"] for c in changes])
    sentences = []
    if trigger.get("type") == "breakdown":
        sentences.append(f"{trigger.get('tractor_id')} broke down; its unfinished work was released.")
    elif trigger.get("type") == "block_road":
        sentences.append(f"Road {trigger.get('a')}–{trigger.get('b')} closed; routes were recomputed.")
    elif trigger.get("type") == "change_priority":
        sentences.append(f"{trigger.get('job_id')} is now priority P{trigger.get('priority')}.")
    if moved:
        sentences.append("Reassigned: " + ", ".join(f"{c['job_id']} {c['before']}→{c['after']}" for c in moved) + ".")
    for c in dropped:
        sentences.append(f"{c['job_id']} cannot be done: {c['reason']}.")
    if not changes:
        sentences.append("No assignment changes were needed.")
    return Explanation(
        headline=f"Re-plan after {trigger.get('type', 'event').replace('_', ' ')}",
        summary=" ".join(sentences),
        highlight_jobs=[c["job_id"] for c in changes],
    )


def explain_replan(diff: dict) -> tuple[Explanation, str]:
    """Returns the explanation and its source ('claude' or 'template')."""
    if diff.get("trigger", {}).get("type") != "initial_plan":
        compact = {k: diff[k] for k in ("trigger", "time", "changes")}
        result = _parse(EXPLAIN_SYSTEM, json.dumps(compact, sort_keys=True), Explanation)
        if isinstance(result, Explanation):
            return result, "claude"
    return template_explanation(diff), "template"


# --- "why?" ------------------------------------------------------------------

WHY_SYSTEM = """You answer an operator asking why a job was assigned the way it was.
You get the coordinator's facts as JSON: chosen tractor, queue position, travel, planned finish,
deadline slack, fuel before/after, and every alternative tractor with why it was rejected.
Answer in 2-4 short sentences. Mention the decisive constraint (implement, fuel, deadline) with the actual numbers.
Use only the given facts."""


class WhyAnswer(BaseModel):
    answer: str


def template_why(facts: dict) -> str:
    if facts.get("status") == "unassignable":
        return f"{facts['job_id']} has no tractor: {facts.get('reason')}."
    if not facts.get("tractor_id"):
        return f"{facts['job_id']} is {facts['status']}."
    parts = [
        f"{facts['tractor_id']} takes {facts['job_id']} (P{facts['priority']}) as stop #{facts.get('queue_position', 0)}, "
        f"finishing at {facts.get('planned_finish')}h with {facts.get('deadline_slack_hours')}h to spare "
        f"and {facts.get('fuel_after')} fuel left."
    ]
    for alt in facts.get("alternatives", []):
        parts.append(f"{alt['tractor_id']}: {alt['reason']}.")
    return " ".join(parts)


def answer_why(facts: dict, question: str | None = None) -> tuple[str, str]:
    prompt = json.dumps(facts, sort_keys=True)
    if question:
        prompt += f"\n\nOperator question: {question}"
    result = _parse(WHY_SYSTEM, prompt, WhyAnswer)
    if isinstance(result, WhyAnswer):
        return result.answer, "claude"
    return template_why(facts), "template"


# --- copilot -----------------------------------------------------------------

COPILOT_SYSTEM = """You are the dispatch copilot for a small fleet of autonomous tractors.
The operator types free text. Translate it into proposed events; a deterministic coordinator
validates and executes them after the operator confirms. Supported events:
- breakdown: tractor_id
- block_road: a, b (node ids of two fields or the depot)
- change_priority: job_id, priority (1 = most urgent, 3 = least)
If the operator asks a question instead, answer it from the state JSON and propose no events.
Only use ids that exist in the state. If the request is ambiguous, ask a short clarifying question and propose no events.
Keep reply under 3 sentences."""


class ProposedEvent(BaseModel):
    type: Literal["breakdown", "block_road", "change_priority"]
    tractor_id: str | None = None
    a: str | None = None
    b: str | None = None
    job_id: str | None = None
    priority: int | None = None


class CopilotReply(BaseModel):
    reply: str
    events: list[ProposedEvent]


def copilot(message: str, state: dict) -> tuple[CopilotReply, str]:
    prompt = f"State:\n{json.dumps(state, sort_keys=True)}\n\nOperator: {message}"
    result = _parse(COPILOT_SYSTEM, prompt, CopilotReply)
    if isinstance(result, CopilotReply):
        return result, "claude"
    return _rule_based_copilot(message, state), "template"


def _rule_based_copilot(message: str, state: dict) -> CopilotReply:
    """Offline fallback understanding the three demo commands."""
    text = message.upper()
    tractors = [t for t in state.get("tractors", []) if t in text.split() or t in re.findall(r"T\d+", text)]
    jobs = re.findall(r"J\d+", text)
    nodes = re.findall(r"\b(F\d+|D)\b", text)
    lowered = message.lower()
    if tractors and any(w in lowered for w in ("break", "broke", "down", "слом", "полом")):
        return CopilotReply(reply=f"Mark {tractors[0]} as broken down?", events=[ProposedEvent(type="breakdown", tractor_id=tractors[0])])
    if len(nodes) >= 2 and any(w in lowered for w in ("block", "closed", "road", "дорог", "закрыт")):
        return CopilotReply(reply=f"Close the road {nodes[0]}–{nodes[1]}?", events=[ProposedEvent(type="block_road", a=nodes[0], b=nodes[1])])
    if jobs and any(w in lowered for w in ("urgent", "priority", "срочн", "приоритет")):
        prio = int(m.group(1)) if (m := re.search(r"P([123])", text)) else 1
        return CopilotReply(reply=f"Set {jobs[0]} to P{prio}?", events=[ProposedEvent(type="change_priority", job_id=jobs[0], priority=prio)])
    return CopilotReply(
        reply="Offline mode: try 'T1 broke down', 'road F2 F4 closed' or 'J05 urgent'.", events=[]
    )
