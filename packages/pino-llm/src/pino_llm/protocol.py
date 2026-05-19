from __future__ import annotations

import json
import re
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

    tool_name = parsed.get("tool", parsed.get("name"))
    if isinstance(tool_name, str):
        arguments = _parse_arguments(parsed.get("arguments", {}))
        if arguments is None:
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
    stripped = _strip_tool_call_wrappers(stripped)
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        first = next((item for item in parsed if isinstance(item, dict)), None)
        return first
    return None


def _parse_arguments(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _strip_tool_call_wrappers(value: str) -> str:
    stripped = value.strip()
    for opener, closer in (
        ("[TOOL_CALL]", "[/TOOL_CALL]"),
        ("[TOOL_CALLS]", "[/TOOL_CALLS]"),
    ):
        if stripped.startswith(opener):
            stripped = stripped[len(opener) :].strip()
        if stripped.endswith(closer):
            stripped = stripped[: -len(closer)].strip()
    return stripped
