from datetime import datetime, timezone
from pathlib import Path

from pino_llm import LLMMessage
from pino_llm.providers import EchoClient

from pino_core.chat import ChatAgent
from pino_core.config import ChatConfig, GoalConfig
from pino_core.models import ChatMessage, MemoryEntry
from pino_core.storage import SQLiteStore
from pino_core.tools import build_tools


class StaticClient:
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, messages: list[LLMMessage]) -> str:
        return self.response


class SequenceClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0
        self.messages: list[list[LLMMessage]] = []

    def complete(self, messages: list[LLMMessage]) -> str:
        self.messages.append(messages)
        response = self.responses[self.calls]
        self.calls += 1
        return response


def test_chat_agent_can_call_memory_tool(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    agent = ChatAgent(
        store=store,
        provider=EchoClient(),
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    result = agent.respond("remember Boss likes short digests")

    assert "Added active memory" in result.content
    assert result.tool_calls == ["memory.add"]
    assert result.debug["tool_usage"] == [
        {
            "name": "memory.add",
            "arguments": {"content": "Boss likes short digests"},
            "result": "Added active memory: Boss likes short digests",
        },
    ]
    assert result.debug["rounds"][0]["action"] == "tool"
    assert result.debug["rounds"][0]["tool"] == "memory.add"
    assert store.list_memory()[0].content == "Boss likes short digests"


def test_chat_agent_echo_provider_uses_current_user_after_old_tool_history(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    agent = ChatAgent(
        store=store,
        provider=EchoClient(),
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    agent.respond("show memory")
    result = agent.respond("remember Boss wants terse useful digests")

    assert result.tool_calls == ["memory.add"]
    assert store.list_memory()[0].content == "Boss wants terse useful digests"


def test_chat_agent_recovers_from_unknown_tool(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    agent = ChatAgent(
        store=store,
        provider=StaticClient('{"tool": "missing.tool", "arguments": {}}'),
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    result = agent.respond("do thing")

    assert "unavailable tool" in result.content
    assert result.tool_calls == []


def test_chat_agent_keeps_current_message_when_history_limit_is_zero(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    agent = ChatAgent(
        store=store,
        provider=EchoClient(),
        tools=build_tools(store, sources=[]),
        config=ChatConfig(history_limit=0),
    )

    result = agent.respond("remember Boss wants visible tool debug")

    assert result.tool_calls == ["memory.add"]
    assert store.list_memory()[0].content == "Boss wants visible tool debug"


def test_chat_agent_receives_history_limit_previous_messages(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_chat_message(
        ChatMessage(
            role="user",
            content="old user",
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        ),
    )
    store.add_chat_message(
        ChatMessage(
            role="assistant",
            content="old assistant",
            created_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
        ),
    )
    store.add_chat_message(
        ChatMessage(
            role="user",
            content="recent user",
            created_at=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc),
        ),
    )
    store.add_chat_message(
        ChatMessage(
            role="assistant",
            content="recent assistant",
            created_at=datetime(2026, 1, 1, 10, 3, tzinfo=timezone.utc),
        ),
    )
    client = SequenceClient(['{"final": "ok"}'])
    agent = ChatAgent(
        store=store,
        provider=client,
        tools=build_tools(store, sources=[]),
        config=ChatConfig(history_limit=2),
    )

    result = agent.respond("current user")

    assert result.content == "ok"
    assert [message.content for message in client.messages[0][1:]] == [
        "recent user",
        "recent assistant",
        "current user",
    ]
    assert [message.role for message in client.messages[0]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert all(message.content != "old user" for message in client.messages[0])
    assert all(message.content != "old assistant" for message in client.messages[0])


def test_chat_agent_omits_stored_tool_messages_from_history(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_chat_message(
        ChatMessage(
            role="tool",
            content="old persisted tool result",
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        ),
    )
    client = SequenceClient(['{"final": "ok"}'])
    agent = ChatAgent(
        store=store,
        provider=client,
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    result = agent.respond("hello")

    assert result.content == "ok"
    assert all(message.role != "tool" for message in client.messages[0])
    assert all(message.content != "old persisted tool result" for message in client.messages[0])


def test_chat_agent_includes_active_memory_in_system_prompt(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_memory(MemoryEntry(content="Boss prefers evaluated event recommendations."))
    client = SequenceClient(['{"final": "ok"}'])
    agent = ChatAgent(
        store=store,
        provider=client,
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    result = agent.respond("what should I do this week?")

    assert result.content == "ok"
    system_message = client.messages[0][0]
    assert system_message.role == "system"
    assert "Active memory:" in system_message.content
    assert "- Boss prefers evaluated event recommendations." in system_message.content


def test_chat_agent_keeps_current_turn_tool_context(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    client = SequenceClient(
        [
            '{"tool": "memory.list", "arguments": {}}',
            '{"final": "Done."}',
        ],
    )
    agent = ChatAgent(
        store=store,
        provider=client,
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    result = agent.respond("show memory")

    assert result.content == "Done."
    assert result.tool_calls == ["memory.list"]
    assert any(message.role == "tool" for message in client.messages[1])
    assert any("memory.list result:" in message.content for message in client.messages[1])


def test_chat_agent_handles_wrapped_tool_call_response(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    client = SequenceClient(
        [
            '[TOOL_CALL]\n{"name": "memory.add", "arguments": {"content": "Boss likes synths"}}\n[/TOOL_CALL]',
            '{"final": "Saved."}',
        ],
    )
    agent = ChatAgent(
        store=store,
        provider=client,
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    result = agent.respond("remember Boss likes synths")

    assert result.content == "Saved."
    assert result.tool_calls == ["memory.add"]
    assert store.list_memory()[0].content == "Boss likes synths"
    assert not any("[TOOL_CALL]" in message.content for message in client.messages[1])


def test_chat_agent_omits_stored_raw_tool_call_messages_from_history(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_chat_message(
        ChatMessage(
            role="assistant",
            content='[TOOL_CALL]\n{"name": "memory.list", "arguments": {}}\n[/TOOL_CALL]',
        ),
    )
    client = SequenceClient(['{"final": "ok"}'])
    agent = ChatAgent(
        store=store,
        provider=client,
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    result = agent.respond("hello")

    assert result.content == "ok"
    assert not any("[TOOL_CALL]" in message.content for message in client.messages[0])


def test_chat_agent_prompt_forbids_tool_call_wrapper_syntax(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    client = SequenceClient(['{"final": "ok"}'])
    agent = ChatAgent(
        store=store,
        provider=client,
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    agent.respond("list events")

    prompt = client.messages[0][0].content
    assert "Output exactly one raw JSON object and nothing else." in prompt
    assert "Do not use markdown fences, provider-specific tool-call wrappers" in prompt
    assert "CLI-style flags" in prompt
    assert '{"tool": "records.relevant", "arguments": {"limit": 20, "days": 14, "min_score": 0.3}}' in prompt


def test_chat_agent_includes_goals_and_current_time_in_system_prompt(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    client = SequenceClient(['{"final": "ok"}'])
    agent = ChatAgent(
        store=store,
        provider=client,
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
        goals=[
            GoalConfig(name="metal_music", description="Metal concerts and related events."),
            GoalConfig(name="synth_music", description="Synth, IDM, and participatory electronic music."),
        ],
        now=lambda: datetime(2026, 5, 25, 17, 38, tzinfo=timezone.utc),
    )

    agent.respond("Any events this week?")

    prompt = client.messages[0][0].content
    assert "Current time:" in prompt
    assert "2026-05-25 20:38 EEST (Europe/Vilnius)" in prompt
    assert "Goals:" in prompt
    assert "- metal_music: Metal concerts and related events." in prompt
    assert "- synth_music: Synth, IDM, and participatory electronic music." in prompt
