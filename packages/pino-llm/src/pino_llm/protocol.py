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
            parsed = _parse_loose_tool_call(stripped)
            if parsed is None:
                return None
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        first = next((item for item in parsed if isinstance(item, dict)), None)
        return first
    return None


def _parse_loose_tool_call(value: str) -> dict[str, Any] | None:
    tool_match = re.search(r"\b(?:tool|name)\s*=>\s*['\"]([^'\"]+)['\"]", value)
    if tool_match is None:
        return None

    arguments: dict[str, Any] = {}
    arguments_match = re.search(r"\barguments\s*=>\s*\{(?P<body>.*?)\}", value, flags=re.DOTALL)
    if arguments_match is not None:
        arguments = _parse_loose_arguments(arguments_match.group("body"))
    return {"tool": tool_match.group(1), "arguments": arguments}


def _parse_loose_arguments(value: str) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    for key, raw_value in re.findall(
        r"--([A-Za-z_][\w-]*)\s+('(?:[^']*)'|\"(?:[^\"]*)\"|[-+]?\d+|\S+)",
        value,
    ):
        arguments[key.replace("-", "_")] = _parse_loose_value(raw_value)

    for key, raw_value in re.findall(
        r"\b([A-Za-z_][\w-]*)\s*(?:=>|:)\s*('(?:[^']*)'|\"(?:[^\"]*)\"|[-+]?\d+)",
        value,
    ):
        arguments.setdefault(key, _parse_loose_value(raw_value))
    return arguments


def _parse_loose_value(value: str) -> Any:
    stripped = value.strip()
    if (stripped.startswith("'") and stripped.endswith("'")) or (
        stripped.startswith('"') and stripped.endswith('"')
    ):
        return stripped[1:-1]
    try:
        return int(stripped)
    except ValueError:
        return stripped


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
