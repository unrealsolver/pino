from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class LLMAction:
    kind: Literal["final", "tool"]
    content: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""


def parse_action(raw_response: str) -> LLMAction:
    parsed = _parse_json_object(raw_response)
    if parsed is None:
        return LLMAction(kind="final", content=raw_response, raw_response=raw_response)

    if "final" in parsed:
        return LLMAction(kind="final", content=str(parsed["final"]), raw_response=raw_response)

    tool_name = parsed.get("tool")
    if isinstance(tool_name, str):
        arguments = parsed.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        return LLMAction(
            kind="tool",
            tool_name=tool_name,
            arguments=arguments,
            raw_response=raw_response,
        )

    return LLMAction(kind="final", content=raw_response, raw_response=raw_response)


def _parse_json_object(raw_response: str) -> dict[str, Any] | None:
    stripped = raw_response.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None

