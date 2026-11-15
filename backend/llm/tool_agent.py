"""A bounded tool-using agent: the model decides which registered tools to call, the server runs them.

The loop is deliberately small. Only tools in the registry can run, arguments are validated against
each tool's schema, the number of turns and calls is capped, and every call is recorded with its
arguments, result and duration. Nothing here can change the fleet: the registry decides what a
tool may do, and the incident tools are read-only.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from . import provider

logger = logging.getLogger(__name__)

MAX_TURNS = 8
MAX_CALLS = 8
RESULT_PREVIEW_CHARS = 2000


class NoArguments(BaseModel):
    """For tools that take nothing."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: type[BaseModel]
    run: Callable[[BaseModel], dict]

    def schema(self) -> dict:
        parameters = self.arguments.model_json_schema()
        parameters.pop("title", None)
        parameters.pop("description", None)
        parameters.setdefault("properties", {})
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": parameters}}


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: dict
    ok: bool
    result: dict
    duration_ms: float
    # "model" when the LLM chose to make this call, "script" when the fixed fallback sequence made it.
    chosen_by: str = "model"


@dataclass(frozen=True)
class AgentRun:
    calls: tuple[ToolCall, ...] = ()
    # Arguments of the finishing tool call, once the agent has made it.
    conclusion: dict | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    # What the model wrote if it ended in plain text instead of the finishing call.
    prose: str = ""


def call_tool(registry: dict[str, Tool], name: str, raw_arguments: dict, chosen_by: str = "model") -> ToolCall:
    """Run one registered tool with validated arguments. Unknown tools and bad arguments are refused, not run."""
    started = time.perf_counter()

    def done(ok: bool, result: dict, arguments: dict) -> ToolCall:
        return ToolCall(name, arguments, ok, result, round((time.perf_counter() - started) * 1000, 2), chosen_by)

    tool = registry.get(name)
    if tool is None:
        return done(False, {"error": f"unknown tool {name}; available: {', '.join(sorted(registry))}"}, raw_arguments)
    try:
        arguments = tool.arguments.model_validate(raw_arguments)
    except ValidationError as exc:
        return done(False, {"error": f"invalid arguments: {exc.errors(include_url=False)[0]['msg']}"}, raw_arguments)
    try:
        return done(True, tool.run(arguments), arguments.model_dump())
    except (KeyError, ValueError) as exc:
        return done(False, {"error": str(exc.args[0]) if exc.args else "tool failed"}, arguments.model_dump())


def _arguments_of(tool_call: dict) -> dict:
    try:
        parsed = json.loads(tool_call["function"].get("arguments") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {"_unparseable": True}
    return parsed if isinstance(parsed, dict) else {"_unparseable": True}


def run_agent(system: str, task: str, registry: dict[str, Tool], finish_with: str) -> AgentRun:
    """Let the model work through the task with the registry's tools until it calls `finish_with`.

    Returns what it did. `conclusion` stays None if no model answered, it ran out of turns or calls,
    or it stopped without finishing; the caller decides what to do then.
    """
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    schemas = [tool.schema() for tool in registry.values()]
    calls: list[ToolCall] = []
    has_been_reminded = False
    for _ in range(MAX_TURNS):
        reply = provider.chat_with_tools(messages, schemas)
        if reply is None:
            return AgentRun(tuple(calls), None, ("no model answered",))
        requested = reply.get("tool_calls") or []
        if not requested:
            prose = reply.get("content") or ""
            if has_been_reminded:
                return AgentRun(tuple(calls), None, ("the model stopped without filing its conclusion",), prose)
            # It answered in prose instead of filing. Keep what it said and remind it once.
            messages.append({"role": "assistant", "content": prose})
            messages.append({"role": "user", "content": f"Do not answer in text. Call {finish_with} now with your conclusion."})
            has_been_reminded = True
            continue
        messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": requested})
        for request in requested:
            if len(calls) >= MAX_CALLS:
                return AgentRun(tuple(calls), None, ("call limit reached",))
            call = call_tool(registry, request["function"]["name"], _arguments_of(request))
            calls.append(call)
            messages.append({"role": "tool", "tool_call_id": request["id"], "content": json.dumps(call.result)[:RESULT_PREVIEW_CHARS]})
            if call.ok and call.tool == finish_with:
                return AgentRun(tuple(calls), call.arguments)
    return AgentRun(tuple(calls), None, ("turn limit reached",))
