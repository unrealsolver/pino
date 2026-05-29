import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from pino_llm import LLMAction, LLMClient, LLMMessage, parse_action

from pino_core.config import ChatConfig, GoalConfig
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import ChatMessage, MemoryEntry, utc_now
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
        goals: list[GoalConfig] | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.store = store
        self.provider = provider
        self.tools = tools
        self.config = config
        self.goals = goals or []
        self.now = now

    def respond(self, user_input: str) -> ChatResult:
        self.store.init_schema()
        user_message = ChatMessage(role="user", content=user_input)
        self.store.add_chat_message(user_message)
        current_turn_message_ids = {user_message.id}

        tool_calls: list[str] = []
        tool_context: list[LLMMessage] = []
        rounds: list[dict[str, object]] = []
        tool_usage: list[dict[str, object]] = []
        debug: dict[str, object] = {"rounds": rounds, "tool_usage": tool_usage}

        for round_index in range(self.config.max_tool_rounds + 1):
            messages = self._build_messages(
                tool_context,
                current_message=user_message,
                current_turn_message_ids=current_turn_message_ids,
            )
            round_debug: dict[str, object] = {
                "round": round_index + 1,
                "message_count": len(messages),
                "message_roles": [message.role for message in messages],
                "tool_context_count": len(tool_context),
            }
            raw_response = self.provider.complete(messages)
            action = parse_action(raw_response)
            round_debug["action"] = action.kind
            if action.tool_name is not None:
                round_debug["tool"] = action.tool_name
            rounds.append(round_debug)

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
            tool_usage.append(
                {
                    "name": action.tool_name,
                    "arguments": action.arguments,
                    "result": result,
                },
            )
            tool_message = ChatMessage(role="tool", content=result, payload={"tool": action.tool_name})
            self.store.add_chat_message(tool_message)
            current_turn_message_ids.add(tool_message.id)
            tool_context.append(LLMMessage(role="assistant", content=_tool_action_json(action)))
            tool_context.append(
                LLMMessage(role="tool", content=f"{action.tool_name} result:\n{result}"),
            )

        final = "Boss, I reached the configured tool-call limit."
        self.store.add_chat_message(ChatMessage(role="assistant", content=final))
        return ChatResult(
            content=final,
            tool_calls=tool_calls,
            debug={"rounds": rounds, "tool_usage": tool_usage},
        )

    def render_system_prompt(self) -> str:
        return render_chat_system_prompt(
            store=self.store,
            tools=self.tools,
            config=self.config,
            goals=self.goals,
            now=self.now,
        )

    def _build_messages(
        self,
        tool_context: list[LLMMessage],
        *,
        current_message: ChatMessage,
        current_turn_message_ids: set[str],
    ) -> list[LLMMessage]:
        messages = [LLMMessage(role="system", content=self.render_system_prompt())]
        history = recent_chat_history(
            self.store,
            self.config.history_limit,
            exclude_ids=current_turn_message_ids,
        )
        messages.extend(LLMMessage(role=message.role, content=message.content) for message in history)
        messages.append(LLMMessage(role=current_message.role, content=current_message.content))
        messages.extend(tool_context)
        return messages


def render_chat_system_prompt(
    *,
    store: SQLiteStore,
    tools: dict[str, Tool],
    config: ChatConfig,
    goals: list[GoalConfig] | None = None,
    now: Callable[[], datetime] = utc_now,
) -> str:
    system = (
        "You are Pino, a local personal agentic assistant. You can occasionally the user as Boss. "
        "Be concise and practical. You are not a generic emotional support chatbot.\n\n"
        "You may request exactly one bounded local tool call at a time.\n"
        "Output exactly one raw JSON object and nothing else.\n"
        "Do not use markdown fences, provider-specific tool-call wrappers, => syntax, single quotes, "
        "or CLI-style flags.\n"
        "Use one of these forms:\n"
        '{"final": "message"}\n'
        '{"tool": "tool.name", "arguments": {}}\n'
        '{"tool": "records.relevant", "arguments": {"limit": 20, "days": 14, "min_score": 0.3}}\n\n'
        f"Available tools:\n{describe_tools(tools)}"
    )
    current_time = _format_current_time(now())
    if current_time:
        system = f"{system}\n\nCurrent time:\n{current_time}"
    goal_text = _format_goals(goals or [])
    if goal_text:
        system = f"{system}\n\nGoals:\n{goal_text}"
    active_memory = _format_active_memory(
        store.list_memory(limit=config.active_memory_limit),
    )
    if active_memory:
        system = f"{system}\n\nActive memory:\n{active_memory}"
    return system


def recent_chat_history(
    store: SQLiteStore,
    limit: int,
    *,
    exclude_ids: set[str] | None = None,
) -> list[ChatMessage]:
    """Return previous chat messages in chronological order for context/display."""
    if limit <= 0:
        return []
    excluded = exclude_ids or set()
    fetch_limit = limit + len(excluded)
    latest = store.list_chat_messages(limit=fetch_limit)
    filtered = [
        message
        for message in latest
        if message.id not in excluded and message.role != "tool" and not _is_raw_tool_call_message(message)
    ]
    return list(reversed(filtered[:limit]))


def _format_current_time(value: datetime) -> str:
    local = value.astimezone(ZoneInfo(DEFAULT_SOURCE_TIMEZONE))
    return f"{local:%Y-%m-%d %H:%M %Z} ({DEFAULT_SOURCE_TIMEZONE})"


def _format_goals(goals: list[GoalConfig]) -> str:
    return "\n".join(f"- {goal.name}: {goal.description}" for goal in goals)


def _format_active_memory(memories: list[MemoryEntry]) -> str:
    return "\n".join(f"- {memory.content}" for memory in memories)


def _tool_action_json(action: LLMAction) -> str:
    return json.dumps(
        {"tool": action.tool_name, "arguments": action.arguments},
        ensure_ascii=False,
    )


def _is_raw_tool_call_message(message: ChatMessage) -> bool:
    if message.role != "assistant":
        return False
    content = message.content.strip()
    return content.startswith(("[TOOL_CALL]", "[TOOL_CALLS]"))
