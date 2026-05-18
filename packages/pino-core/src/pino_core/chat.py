from dataclasses import dataclass

from pino_llm import LLMClient, LLMMessage, parse_action

from pino_core.config import ChatConfig
from pino_core.models import ChatMessage
from pino_core.storage import SQLiteStore
from pino_core.tools import Tool, describe_tools


@dataclass(frozen=True)
class ChatResult:
    content: str
    tool_calls: list[str]
    debug: dict[str, object]


class ChatAgent:
    def __init__(
        self,
        store: SQLiteStore,
        provider: LLMClient,
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
        debug: dict[str, object] = {}

        for _ in range(self.config.max_tool_rounds + 1):
            messages = self._build_messages(tool_context)
            debug = {
                "message_count": len(messages),
                "message_roles": [message.role for message in messages],
                "tool_context_count": len(tool_context),
            }
            raw_response = self.provider.complete(messages)
            action = parse_action(raw_response)

            if action.kind == "final":
                final = action.content or ""
                self.store.add_chat_message(ChatMessage(role="assistant", content=final))
                return ChatResult(content=final, tool_calls=tool_calls, debug=debug)

            if not action.tool_name or action.tool_name not in self.tools:
                final = (
                    "Boss, the model requested an unavailable tool: "
                    f"{action.tool_name or '<missing>'}."
                )
                self.store.add_chat_message(ChatMessage(role="assistant", content=final))
                return ChatResult(content=final, tool_calls=tool_calls, debug=debug)

            result = self.tools[action.tool_name].run(action.arguments)
            tool_calls.append(action.tool_name)
            self.store.add_chat_message(
                ChatMessage(role="tool", content=result, payload={"tool": action.tool_name}),
            )
            tool_context.append(LLMMessage(role="assistant", content=raw_response))
            tool_context.append(
                LLMMessage(role="tool", content=f"{action.tool_name} result:\n{result}"),
            )

        final = "Boss, I reached the configured tool-call limit."
        self.store.add_chat_message(ChatMessage(role="assistant", content=final))
        return ChatResult(content=final, tool_calls=tool_calls, debug=debug)

    def _build_messages(self, tool_context: list[LLMMessage]) -> list[LLMMessage]:
        system = (
            "You are Pino, a local personal agentic assistant. You can occasionally the user as Boss. "
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
