from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pino_core.config import ChatConfig
from pino_core.models import ChatMessage
from pino_core.providers import LLMMessage, LLMProvider
from pino_core.storage import SQLiteStore
from pino_core.tools import Tool, describe_tools


@dataclass(frozen=True)
class ChatResult:
    content: str
    tool_calls: list[str]


class ChatAgent:
    def __init__(
        self,
        store: SQLiteStore,
        provider: LLMProvider,
        tools: dict[str, Tool],
        config: ChatConfig,
    ) -> None:
        self.store = store
        self.provider = provider
        self.tools = tools
        self.config = config

    def respond(self, user_input: str) -> ChatResult:
        self.store.init_schema()
        self.store.add_chat_message(ChatMessage(role="user", content=user_input))

        tool_calls: list[str] = []
        tool_context: list[LLMMessage] = []

        for _ in range(self.config.max_tool_rounds + 1):
            messages = self._build_messages(tool_context)
            raw_response = self.provider.complete(messages)
            parsed = self._parse_response(raw_response)

            if "final" in parsed:
                final = str(parsed["final"])
                self.store.add_chat_message(ChatMessage(role="assistant", content=final))
                return ChatResult(content=final, tool_calls=tool_calls)

            tool_name = parsed.get("tool")
            arguments = parsed.get("arguments", {})
            if not isinstance(tool_name, str) or tool_name not in self.tools:
                final = raw_response
                self.store.add_chat_message(ChatMessage(role="assistant", content=final))
                return ChatResult(content=final, tool_calls=tool_calls)
            if not isinstance(arguments, dict):
                arguments = {}

            result = self.tools[tool_name].run(arguments)
            tool_calls.append(tool_name)
            self.store.add_chat_message(
                ChatMessage(role="tool", content=result, payload={"tool": tool_name}),
            )
            tool_context.append(LLMMessage(role="assistant", content=raw_response))
            tool_context.append(LLMMessage(role="tool", content=f"{tool_name} result:\n{result}"))

        final = "Boss, I reached the configured tool-call limit."
        self.store.add_chat_message(ChatMessage(role="assistant", content=final))
        return ChatResult(content=final, tool_calls=tool_calls)

    def _build_messages(self, tool_context: list[LLMMessage]) -> list[LLMMessage]:
        system = (
            "You are Pino, a local personal agentic assistant. Address the user as Boss. "
            "Be concise and practical. You are not a generic emotional support chatbot.\n\n"
            "You may request exactly one bounded local tool call at a time.\n"
            "Respond with strict JSON only, using one of these forms:\n"
            '{"final": "message"}\n'
            '{"tool": "tool.name", "arguments": {}}\n\n'
            f"Available tools:\n{describe_tools(self.tools)}"
        )
        messages = [LLMMessage(role="system", content=system)]
        history = list(reversed(self.store.list_chat_messages(limit=self.config.history_limit)))
        messages.extend(LLMMessage(role=message.role, content=message.content) for message in history)
        messages.extend(tool_context)
        return messages

    def _parse_response(self, raw_response: str) -> dict[str, Any]:
        stripped = raw_response.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return {"final": raw_response}
        return parsed if isinstance(parsed, dict) else {"final": raw_response}

