"""LLM features: re-plan explanations, "why?", copilot chat, what-if, job intake.

The LLM never plans. It (a) turns structured facts into plain language and
(b) translates operator text into typed events or job drafts that the
coordinator validates before anything runs. Every call has a deterministic
fallback, so the demo works offline.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from fleet.scenario import ScenarioDraft, ScenarioIn, random_live_scenario, scenario_from_draft

from .provider import provider_name, structured

logger = logging.getLogger(__name__)

NO_INVENTION = "Use only facts present in the JSON. Never invent causes, people, repairs, weather or numbers."


def llm_available() -> bool:
    return provider_name() is not None


def llm_provider() -> str:
    return provider_name() or "offline"


def _ask(system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel | None, str]:
    result, source = structured(f"{system}\n{NO_INVENTION}", user, schema)
    return (result, source) if isinstance(result, schema) else (None, "template")


# --- re-plan explanation -----------------------------------------------------

EXPLAIN_SYSTEM = """You explain fleet re-plans to a farm operator.
You receive a JSON diff produced by a deterministic coordinator: the trigger and per-job changes
(before -> after tractor, or 'unassignable' with the reason).
- headline: max 7 words, plain.
- summary: 2-3 short sentences: what happened, who took over which work, what cannot be done and why.
- highlight_jobs: ids of the jobs that changed.
Refer to jobs, fields and tractors by their ids. Times are hours since shift start."""


class Explanation(BaseModel):
    headline: str = Field(description="Max 7 words")
    summary: str = Field(description="2-3 short sentences for the operator")
    highlight_jobs: list[str] = Field(description="Job ids the dashboard should highlight")


def template_explanation(diff: dict) -> Explanation:
    trigger = diff.get("trigger", {})
    changes = diff.get("changes", [])
    moved = [c for c in changes if c["after"] not in ("unassignable", "unplanned") and c["before"] != "unplanned"]
    dropped = [c for c in changes if c["after"] == "unassignable"]
    if trigger.get("type") == "initial_plan":
        per: dict[str, list[str]] = {}
        for c in changes:
            per.setdefault(c["after"], []).append(c["job_id"])
        parts = [f"{t}: {', '.join(js)}" for t, js in sorted(per.items()) if t != "unassignable"]
        summary = "Initial plan. " + "; ".join(parts) + "."
        if dropped:
            summary += f" Cannot be done: {', '.join(c['job_id'] for c in dropped)}."
        return Explanation(headline="Initial plan ready", summary=summary, highlight_jobs=[])
    sentences = []
    kind = trigger.get("type")
    if kind == "breakdown":
        sentences.append(f"{trigger.get('tractor_id')} broke down; its unfinished work was released.")
    elif kind == "block_road":
        sentences.append(f"Road {trigger.get('a')}–{trigger.get('b')} closed; routes were recomputed.")
    elif kind == "change_priority":
        sentences.append(f"{trigger.get('job_id')} is now priority P{trigger.get('priority')}.")
    elif kind == "add_job":
        sentences.append(f"New job {trigger.get('job_id')} was added.")
    if moved:
        sentences.append("Reassigned: " + ", ".join(f"{c['job_id']} {c['before']}→{c['after']}" for c in moved) + ".")
    for c in dropped:
        sentences.append(f"{c['job_id']} cannot be done: {c['reason']}.")
    if not changes:
        sentences.append("No assignment changes were needed.")
    return Explanation(
        headline=f"Re-plan after {str(kind or 'event').replace('_', ' ')}",
        summary=" ".join(sentences),
        highlight_jobs=[c["job_id"] for c in changes],
    )


def explain_replan(diff: dict) -> tuple[Explanation, str]:
    """Returns the explanation and its source (provider name or 'template')."""
    if diff.get("trigger", {}).get("type") == "initial_plan":
        return template_explanation(diff), "template"
    compact = {k: diff[k] for k in ("trigger", "time", "changes")}
    result, source = _ask(EXPLAIN_SYSTEM, json.dumps(compact, sort_keys=True), Explanation)
    return (result, source) if isinstance(result, Explanation) else (template_explanation(diff), "template")


# --- ask one tractor agent ---------------------------------------------------

AGENT_SYSTEM = """You are the on-board agent of one tractor in a farm fleet. The operator asks you a question.
You get JSON facts: your id, your status right now, and what you said and heard in one planning round
held at round_time_h hours into the shift (announcements, your bids and passes, awards, routes, claims,
trades, your confirmed queue). The round may be older than your current status.
Answer in first person, in 2-3 short sentences. Quote the actual numbers and job ids from your messages.
If the facts do not contain the answer, say you do not know."""


class AgentAnswer(BaseModel):
    answer: str


def template_agent_answer(facts: dict) -> str:
    own = [m["text"] for m in facts["messages"] if m["from"] == facts["tractor_id"]]
    if not own:
        return "I took no part in the last planning round."
    return f"Here is what I said in the last planning round: {' '.join(own[-3:])}"


def ask_tractor(facts: dict, question: str) -> tuple[str, str]:
    payload = json.dumps({"question": question, **facts}, sort_keys=True)
    result, source = _ask(AGENT_SYSTEM, payload, AgentAnswer)
    return (result.answer, source) if isinstance(result, AgentAnswer) else (template_agent_answer(facts), "template")


# --- "why?" ------------------------------------------------------------------

WHY_SYSTEM = """You answer an operator asking why a job was assigned the way it was.
You get the coordinator's facts as JSON: chosen tractor, queue position, travel, planned finish,
deadline slack, fuel before/after, and every alternative tractor with why it was rejected.
Answer in 2-4 short sentences. Name the decisive constraint (implement, fuel, deadline) with the actual numbers.
Times in the facts are hours since the 06:00 shift start: write them as times of day (11.0 is 17:00, 10.25 is 16:15);
keep durations such as slack or travel in hours or minutes. Fuel is in tank units, not litres."""


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
    parts.extend(f"{alt['tractor_id']}: {alt['reason']}." for alt in facts.get("alternatives", []))
    return " ".join(parts)


def answer_why(facts: dict, question: str | None = None) -> tuple[str, str]:
    prompt = json.dumps(facts, sort_keys=True)
    if question:
        prompt += f"\n\nOperator question: {question}"
    result, source = _ask(WHY_SYSTEM, prompt, WhyAnswer)
    return (result.answer, source) if isinstance(result, WhyAnswer) else (template_why(facts), "template")


# --- copilot chat ------------------------------------------------------------

COPILOT_SYSTEM = """You are the dispatch copilot for a small fleet of autonomous tractors.
The operator types free text. Either answer a question about the current state, or translate a report
into proposed events. A deterministic coordinator validates and executes events after the operator confirms.
Supported events:
- breakdown: tractor_id
- block_road: a, b (two node ids: fields or the depot)
- change_priority: job_id, priority (1 = most urgent, 3 = least)
For questions, answer from the state JSON and propose no events.
- Counts: read them from `totals` and `totals.by_type`. Never count the jobs yourself.
- How long, how much time, "how many times did it take": these all ask for a duration. Read `shift` (started_at, hours_elapsed, total_duration_hours, ended_at),
  a job's `finished_at` and `work_hours`, a tractor's `hours_working` and `hours_driving`. If the shift
  is not finished, say so and give the time elapsed so far.
- Times of day in the state are clock times (06:00 is the shift start); use them as written.
- A job with status "unassignable" cannot be done; its `reason` says why. Say so when it is relevant.
Answer the question that was asked. If the state does not hold the answer, say that plainly.
Only use ids that exist in the state. If ambiguous, ask a short clarifying question and propose no events.
For fields you do not use in an event, return null. Keep reply under 3 sentences."""


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


def copilot(message: str, state: dict, history: list[dict] | None = None) -> tuple[CopilotReply, str]:
    recent = (history or [])[-6:]
    prompt = f"State:\n{json.dumps(state, sort_keys=True)}\n\nRecent chat:\n{json.dumps(recent)}\n\nOperator: {message}"
    result, source = _ask(COPILOT_SYSTEM, prompt, CopilotReply)
    if isinstance(result, CopilotReply):
        return result, source
    return _rule_based_copilot(message, state), "template"


def _rule_based_copilot(message: str, state: dict) -> CopilotReply:
    """Offline fallback understanding the three demo commands."""
    text = message.upper()
    tractors = [t for t in re.findall(r"T\d+", text) if t in state.get("tractors", {})]
    jobs = re.findall(r"J\d+", text)
    nodes = re.findall(r"\b(F\d+|D)\b", text)
    lowered = message.lower()
    if tractors and any(w in lowered for w in ("break", "broke", "down", "stuck", "слом", "полом")):
        return CopilotReply(reply=f"Mark {tractors[0]} as broken down?", events=[ProposedEvent(type="breakdown", tractor_id=tractors[0])])
    if len(nodes) >= 2 and any(w in lowered for w in ("block", "closed", "road", "flood", "дорог", "закрыт")):
        return CopilotReply(reply=f"Close the road {nodes[0]}–{nodes[1]}?", events=[ProposedEvent(type="block_road", a=nodes[0], b=nodes[1])])
    if jobs and any(w in lowered for w in ("urgent", "priority", "срочн", "приоритет")):
        prio = int(m.group(1)) if (m := re.search(r"P([123])", text)) else 1
        return CopilotReply(reply=f"Set {jobs[0]} to P{prio}?", events=[ProposedEvent(type="change_priority", job_id=jobs[0], priority=prio)])
    return CopilotReply(reply=f"{_state_summary(state)} Offline mode: I can also take 'T1 broke down', 'road F2 F4 closed' or 'J05 urgent'.", events=[])


def _state_summary(state: dict) -> str:
    """One factual sentence about the shift, for when no LLM is there to answer a question."""
    totals, shift = state.get("totals"), state.get("shift")
    if not totals or not shift:
        return ""
    when = (f"The shift ended at {shift['ended_at']} after {shift['total_duration_hours']} h" if shift["is_finished"]
            else f"At {state['clock_now']}, {shift['hours_elapsed']} h into the shift")
    return f"{when}: {totals['done_on_time']} of {totals['jobs']} jobs done on time, {totals['cannot_be_done']} cannot be done."


# --- what-if forecast --------------------------------------------------------

WHATIF_SYSTEM = """You narrate a what-if forecast for a farm operator.
The JSON has the hypothetical event and two simulated outcomes of the rest of the shift, computed by
the deterministic simulator: 'current' (nothing happens) and 'what_if' (the event happens now), plus
the jobs that would be lost. Answer in 2-3 short sentences: impact on finished jobs, which jobs are lost and why."""


class WhatIfNarration(BaseModel):
    headline: str
    answer: str


def narrate_what_if(facts: dict) -> tuple[WhatIfNarration, str]:
    result, source = _ask(WHATIF_SYSTEM, json.dumps(facts, sort_keys=True), WhatIfNarration)
    if isinstance(result, WhatIfNarration):
        return result, source
    cur, alt = facts["current"]["jobs_completed"], facts["what_if"]["jobs_completed"]
    lost = ", ".join(f"{j['job_id']} ({j['reason']})" for j in facts["lost_jobs"]) or "none"
    return WhatIfNarration(
        headline=f"{cur} → {alt} jobs done on time",
        answer=f"If this happens now, finished jobs go from {cur} to {alt}. Lost: {lost}.",
    ), "template"


# --- job intake from free text -----------------------------------------------

JOBS_SYSTEM = """You turn an operator's free-text work order into job drafts.
Each job: type ('spray' or 'mow'), field_id (must be one of the given fields), priority (1 urgent .. 3 low),
deadline_hours (hours since shift start; the shift starts at 06:00, so 'by noon' = 6, 'by 14:00' = 8),
work_hours (default 1.5 if not stated). One job per field and type mentioned.
'now_hours' is the current time. A deadline must be later than now_hours + work_hours;
for 'asap'/'urgent' use priority 1 and deadline = now_hours + work_hours + 2.
If something is unclear, still return your best drafts and say what you assumed in 'note'."""


class JobDraft(BaseModel):
    type: Literal["spray", "mow"]
    field_id: str
    priority: int
    deadline_hours: float
    work_hours: float


class JobDrafts(BaseModel):
    jobs: list[JobDraft]
    note: str


def parse_jobs(text: str, fields: list[str], shift_start_hour: float, now_hours: float) -> tuple[JobDrafts, str]:
    prompt = json.dumps({"fields": fields, "shift_start_hour": shift_start_hour, "now_hours": round(now_hours, 2), "order": text})
    result, source = _ask(JOBS_SYSTEM, prompt, JobDrafts)
    if isinstance(result, JobDrafts):
        return result, source
    return _rule_based_jobs(text, fields, now_hours), "template"


def _rule_based_jobs(text: str, fields: list[str], now_hours: float) -> JobDrafts:
    lowered = text.lower()
    kind: Literal["spray", "mow"] = "mow" if any(w in lowered for w in ("mow", "кос")) else "spray"
    found = [f for f in re.findall(r"F\d+", text.upper()) if f in fields]
    priority = 1 if any(w in lowered for w in ("urgent", "asap", "срочн")) else 2
    return JobDrafts(
        jobs=[JobDraft(type=kind, field_id=f, priority=priority, deadline_hours=now_hours + 4, work_hours=1.5)
              for f in found],
        note="Offline parser: deadline in 4 h and 1.5 h of work assumed.",
    )


# --- scenario from a description ---------------------------------------------

SCENARIO_SYSTEM = """You set up a farm shift for a fleet simulator from an operator's description.
Return a scenario draft:
- name: short title.
- tractors: 1 to 4, each with implement "sprayer" or "mower" and fuel_capacity (60 to 100; use 100 if not said).
- fields: 1 to 10 points on a 10 by 10 grid (x 0..10, y 1..10), spread apart; the depot is at x=5, y=0.
- jobs: 1 to 14. type "spray" needs a sprayer, "mow" needs a mower. field_number is the 1-based position in fields.
  priority 1 is most urgent, 3 least. deadline_hours is hours after the 06:00 shift start (a 14:00 deadline is 8).
  work_hours between 0.5 and 3.
Follow every number and detail the operator gives. Fill in whatever they leave out with sensible values,
and make sure every job type has at least one tractor that can do it."""

_COUNT = r"(\d+)\s*(?:x\s*)?"


def _count(text: str, word: str) -> int | None:
    found = re.search(_COUNT + word, text.lower())
    return int(found.group(1)) if found else None


def scenario_from_text(text: str, seed: int) -> tuple[ScenarioIn, str]:
    """Build a scenario from plain words. Offline, only the counts of tractors, fields and jobs are read."""
    result, source = _ask(SCENARIO_SYSTEM, text, ScenarioDraft)
    if isinstance(result, ScenarioDraft):
        try:
            return scenario_from_draft(result), source
        except ValueError:
            logger.warning("LLM scenario draft was unusable, falling back to a generated one")
    counts = (_count(text, "tractor"), _count(text, "field"), _count(text, r"(?:job|task)"))
    return random_live_scenario(seed, *counts), "template"


# --- shift briefing ----------------------------------------------------------

BRIEFING_SYSTEM = """You brief a farm fleet manager on the shift so far. You get verified facts as JSON:
the time, job counts, how the fleet compares with a simple first-come-first-served dispatcher on the same
shift, the events so far, and an "attention" list of things that need a decision or a close eye.
- headline: max 9 words, the single most important thing.
- summary: 3 to 4 short sentences. Start with progress, then what went wrong and how the fleet adapted,
  then what the manager should look at. Use the job, field and tractor ids and the clock times given.
Do not list every item; the attention list is shown next to your text."""


class Briefing(BaseModel):
    headline: str
    summary: str


def template_briefing(facts: dict) -> Briefing:
    jobs = facts["jobs"]
    attention = facts["attention"]
    headline = f"{len(attention)} thing{'s' if len(attention) != 1 else ''} need attention" if attention else "Shift is on plan"
    events = f" {len(facts['events'])} event(s) so far, each re-planned." if facts["events"] else " No events so far."
    summary = (
        f"At {facts['clock']}, {jobs['done_on_time']} of {jobs['total']} jobs are done on time, {jobs['in_progress']} in progress "
        f"and {jobs['waiting']} waiting; {jobs['not_doable']} cannot be done.{events}"
    )
    return Briefing(headline=headline, summary=summary)


def shift_briefing(facts: dict) -> tuple[Briefing, str]:
    result, source = _ask(BRIEFING_SYSTEM, json.dumps(facts, sort_keys=True), Briefing)
    return (result, source) if isinstance(result, Briefing) else (template_briefing(facts), "template")
