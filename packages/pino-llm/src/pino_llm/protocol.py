from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class LLMToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMAction:
    kind: Literal["final", "tool"]
    content: str | None = None
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    raw_response: str = ""

    @property
    def tool_name(self) -> str | None:
        return self.tool_calls[0].name if self.tool_calls else None

    @property
    def arguments(self) -> dict[str, Any]:
        return self.tool_calls[0].arguments if self.tool_calls else {}


def parse_action(raw_response: str) -> LLMAction:
    parsed = _parse_json_object(raw_response)
    action = _action_from_parsed(parsed, raw_response=raw_response, allow_final=True)
    if action is not None:
        return action

    tool_calls: list[LLMToolCall] = []
    for embedded in _parse_embedded_json_values(raw_response):
        action = _action_from_parsed(embedded, raw_response=raw_response, allow_final=False)
        if action is not None and action.kind == "tool":
            tool_calls.extend(action.tool_calls)
    if tool_calls:
        return LLMAction(kind="tool", tool_calls=tool_calls, raw_response=raw_response)
    return LLMAction(kind="final", content=raw_response, raw_response=raw_response)


def _action_from_parsed(
    parsed: Any,
    *,
    raw_response: str,
    allow_final: bool,
) -> LLMAction | None:
    if parsed is None:
        return None

    if allow_final and isinstance(parsed, dict) and "final" in parsed:
        return LLMAction(kind="final", content=str(parsed["final"]), raw_response=raw_response)

    tool_calls = _parse_tool_calls(parsed)
    if tool_calls:
        return LLMAction(kind="tool", tool_calls=tool_calls, raw_response=raw_response)
    return None


def _parse_json_object(raw_response: str) -> Any:
    stripped = raw_response.strip()
    stripped = _strip_tool_call_wrappers(stripped)
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = _parse_loose_tool_call(stripped)
        if parsed is None:
            return None
    return parsed


def _parse_embedded_json_values(raw_response: str) -> list[Any]:
    stripped = _strip_tool_call_wrappers(raw_response.strip())
    decoder = json.JSONDecoder()
    values: list[Any] = []
    cursor = 0
    while match := re.search(r"[\{\[]", stripped[cursor:]):
        start = cursor + match.start()
        try:
            parsed, end = decoder.raw_decode(stripped[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        values.append(parsed)
        cursor = start + end
    return values


def _parse_tool_calls(parsed: Any) -> list[LLMToolCall]:
    if isinstance(parsed, dict) and isinstance(parsed.get("tools"), list):
        candidates = parsed["tools"]
    elif isinstance(parsed, list):
        candidates = parsed
    else:
        candidates = [parsed]

    tool_calls: list[LLMToolCall] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        tool_name = candidate.get("tool", candidate.get("name"))
        if not isinstance(tool_name, str):
            continue
        arguments = _parse_arguments(candidate.get("arguments", {}))
        tool_calls.append(LLMToolCall(name=tool_name, arguments=arguments or {}))
    return tool_calls


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
