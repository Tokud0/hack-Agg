"""LLM provider: Groq (OpenAI-compatible) first, Claude second, None if no key.

`structured()` returns a validated Pydantic object or None; callers then fall
back to deterministic templates, so the demo never depends on the network.
"""

from __future__ import annotations

import copy
import logging
import os

import anthropic
import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TIMEOUT_S = 20.0
CLAUDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 4000


def groq_model() -> str:
    return os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")


def groq_backup_model() -> str:
    return os.environ.get("GROQ_BACKUP_MODEL", "openai/gpt-oss-20b")


def claude_model() -> str:
    return os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")


def provider_name() -> str | None:
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "claude"
    return None


def strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic schema made strict-mode compatible: every property required, no extras."""
    schema = copy.deepcopy(model.model_json_schema())

    def walk(node: object) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            node.pop("title", None)
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return schema


HTTP_TOO_MANY_REQUESTS = 429


def _groq_once(model: str, api_key: str, system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel | None, bool]:
    """One call to one model with one key. Returns the parsed answer (or None) and whether it was rate limited."""
    payload = {
        "model": model,
        "reasoning_effort": "low",
        "temperature": 0.2,
        "max_completion_tokens": MAX_TOKENS,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "strict": True, "schema": strict_schema(schema)},
        },
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        res = httpx.post(GROQ_URL, json=payload, headers=headers, timeout=GROQ_TIMEOUT_S)
        res.raise_for_status()
        content = res.json()["choices"][0]["message"]["content"]
        return schema.model_validate_json(content), False
    except httpx.HTTPStatusError as exc:
        logger.warning("Groq %s HTTP %s: %s", model, exc.response.status_code, exc.response.text[:300])
        return None, exc.response.status_code == HTTP_TOO_MANY_REQUESTS
    except httpx.HTTPError as exc:
        logger.warning("Groq unreachable: %s", exc)
    except (KeyError, IndexError, ValidationError) as exc:
        logger.warning("Groq %s returned an unusable answer: %s", model, exc)
    return None, False


def groq_keys() -> list[str]:
    """The main key, then an optional second one. Groq counts usage per account, so a second key only
    adds allowance when it belongs to a different account."""
    return [key for key in (os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_API_KEY_2")) if key]


def _groq(system: str, user: str, schema: type[BaseModel]) -> BaseModel | None:
    """Ask the main model; while the answer is "rate limited", move on: the second key if there is one,
    then the backup model, which has its own per-minute allowance, on each key."""
    attempts = [(model, key) for model in (groq_model(), groq_backup_model()) for key in groq_keys()]
    for model, key in attempts:
        result, is_rate_limited = _groq_once(model, key, system, user, schema)
        if result is not None or not is_rate_limited:
            return result
    return None


_claude_client: anthropic.Anthropic | None = None


def _claude(system: str, user: str, schema: type[BaseModel]) -> BaseModel | None:
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic(timeout=30.0, max_retries=1)
    try:
        response = _claude_client.beta.messages.parse(
            model=claude_model(),
            max_tokens=MAX_TOKENS,
            betas=[CLAUDE_FALLBACK_BETA],
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


def structured(system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel | None, str]:
    """Returns (parsed object or None, provider name)."""
    name = provider_name()
    if name == "groq":
        return _groq(system, user, schema), name
    if name == "claude":
        return _claude(system, user, schema), name
    return None, "template"
