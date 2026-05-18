from pathlib import Path

from pino_llm import LLMMessage
from pino_llm.providers import EchoClient

from pino_core.chat import ChatAgent
from pino_core.config import ChatConfig
from pino_core.storage import SQLiteStore
from pino_core.tools import build_tools


class StaticClient:
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, messages: list[LLMMessage]) -> str:
        return self.response


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
