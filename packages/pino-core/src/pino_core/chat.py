import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from pino_llm import LLMClient, LLMMessage, LLMToolCall, parse_action

from pino_core.config import ChatConfig, GoalConfig
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import ChatMessage, MemoryEntry, utc_now
from pino_core.storage import DatabaseStore
from pino_core.tools import Tool, describe_tools

PARALLEL_READ_ONLY_TOOLS = frozenset(
    {"memory.list", "records.list", "records.relevant", "web.open"}
)


@dataclass(frozen=True)
class ChatResult:
    content: str
    tool_calls: list[str]
    debug: dict[str, object]


class ChatAgent:
    def __init__(
        self,
        store: DatabaseStore,
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
            if action.tool_calls:
                round_debug["tool"] = action.tool_calls[0].name
                round_debug["tools"] = [call.name for call in action.tool_calls]
            rounds.append(round_debug)

            if action.kind == "final":
                final = action.content or ""
                self.store.add_chat_message(ChatMessage(role="assistant", content=final))
                return ChatResult(content=final, tool_calls=tool_calls, debug=debug)

            selected_calls = action.tool_calls[: self.config.max_tools_per_round]
            truncated_count = len(action.tool_calls) - len(selected_calls)
            if truncated_count:
                round_debug["truncated_tool_calls"] = truncated_count
            unavailable = next(
                (call.name for call in selected_calls if call.name not in self.tools), None
            )
            if not selected_calls or unavailable is not None:
                final = (
                    f"Boss, the model requested an unavailable tool: {unavailable or '<missing>'}."
                )
                self.store.add_chat_message(ChatMessage(role="assistant", content=final))
                return ChatResult(content=final, tool_calls=tool_calls, debug=debug)

            results = _run_tool_calls(selected_calls, self.tools)
            tool_context.append(
                LLMMessage(role="assistant", content=_tool_actions_json(selected_calls))
            )
            for call, result in results:
                tool_calls.append(call.name)
                tool_usage.append(
                    {
                        "name": call.name,
                        "arguments": call.arguments,
                        "result": result,
                    },
                )
                tool_message = ChatMessage(role="tool", content=result, payload={"tool": call.name})
                self.store.add_chat_message(tool_message)
                current_turn_message_ids.add(tool_message.id)
                tool_context.append(
                    LLMMessage(role="tool", content=f"{call.name} result:\n{result}"),
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
        messages.extend(
            LLMMessage(role=message.role, content=message.content) for message in history
        )
        messages.append(LLMMessage(role=current_message.role, content=current_message.content))
        messages.extend(tool_context)
        return messages


def render_chat_system_prompt(
    *,
    store: DatabaseStore,
    tools: dict[str, Tool],
    config: ChatConfig,
    goals: list[GoalConfig] | None = None,
    now: Callable[[], datetime] = utc_now,
) -> str:
    system = (
        "You are Pino, a local personal agentic assistant. You can occasionally the user as Boss. "
        "Be concise and practical. You are not a generic emotional support chatbot.\n"
        "Prefer printing records in a small table form\n\n"
        f"You may request up to {config.max_tools_per_round} bounded local tool calls at a time.\n"
        "For normal final answers, reply in plain text.\n"
        "For tool calls, output exactly one raw JSON object and nothing else.\n"
        "Request multiple tools only when the calls are independent.\n"
        "For tool calls, do not use markdown fences, provider-specific tool-call wrappers, "
        "=> syntax, single quotes, or CLI-style flags.\n"
        "Use these forms for tool calls:\n"
        '{"tool": "tool.name", "arguments": {}}\n'
        '{"tools": [{"tool": "tool.name", "arguments": {}}, {"tool": "tool.name", "arguments": {}}]}\n'
        '{"tool": "records.relevant", "arguments": {"limit": 20, "days": 14, "min_score": 0.3, "categories": ["electronic_music"]}}\n\n'
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
    store: DatabaseStore,
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
        if message.id not in excluded
        and message.role != "tool"
        and not _is_raw_tool_call_message(message)
    ]
    return list(reversed(filtered[:limit]))


def _format_current_time(value: datetime) -> str:
    local = value.astimezone(ZoneInfo(DEFAULT_SOURCE_TIMEZONE))
    return f"{local:%Y-%m-%d %H:%M %Z} ({DEFAULT_SOURCE_TIMEZONE})"


def _format_goals(goals: list[GoalConfig]) -> str:
    return "\n".join(f"- {goal.name}: {goal.description}" for goal in goals)


def _format_active_memory(memories: list[MemoryEntry]) -> str:
    return "\n".join(f"- {memory.content}" for memory in memories)


def _run_tool_calls(
    calls: list[LLMToolCall],
    tools: dict[str, Tool],
) -> list[tuple[LLMToolCall, str]]:
    results: list[tuple[LLMToolCall, str]] = []
    read_only_batch: list[LLMToolCall] = []

    def flush_read_only_batch() -> None:
        if not read_only_batch:
            return
        with ThreadPoolExecutor(max_workers=len(read_only_batch)) as executor:
            outputs = executor.map(
                lambda call: tools[call.name].run(call.arguments),
                read_only_batch,
            )
            results.extend(zip(read_only_batch, outputs, strict=True))
        read_only_batch.clear()

    for call in calls:
        if call.name in PARALLEL_READ_ONLY_TOOLS:
            read_only_batch.append(call)
            continue
        flush_read_only_batch()
        results.append((call, tools[call.name].run(call.arguments)))
    flush_read_only_batch()
    return results


def _tool_actions_json(calls: list[LLMToolCall]) -> str:
    actions = [{"tool": call.name, "arguments": call.arguments} for call in calls]
    payload = actions[0] if len(actions) == 1 else {"tools": actions}
    return json.dumps(payload, ensure_ascii=False)


def _is_raw_tool_call_message(message: ChatMessage) -> bool:
    if message.role != "assistant":
        return False
    content = message.content.strip()
    return content.startswith(("[TOOL_CALL]", "[TOOL_CALLS]"))
