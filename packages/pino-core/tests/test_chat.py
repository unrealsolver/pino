from pathlib import Path

from pino_core.chat import ChatAgent
from pino_core.config import ChatConfig
from pino_core.providers import EchoProvider
from pino_core.storage import SQLiteStore
from pino_core.tools import build_tools


def test_chat_agent_can_call_memory_tool(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    agent = ChatAgent(
        store=store,
        provider=EchoProvider(),
        tools=build_tools(store, sources=[]),
        config=ChatConfig(),
    )

    result = agent.respond("remember Boss likes short digests")

    assert "Added active memory" in result.content
    assert result.tool_calls == ["memory.add"]
    assert store.list_memory()[0].content == "Boss likes short digests"

