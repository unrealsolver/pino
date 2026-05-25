from io import StringIO
from types import SimpleNamespace
from datetime import datetime, timezone

from rich.console import Console

from pino_cli import main
from pino_core.config import PinoConfig
from pino_core.models import ChatMessage
from pino_core.storage import SQLiteStore


def test_chat_debug_prints_tool_markup_as_plain_text(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=True, width=100))
    result = SimpleNamespace(
        tool_calls=["records.list"],
        debug={
            "rounds": [
                {
                    "round": 1,
                    "message_count": 2,
                    "message_roles": ["system", "user"],
                    "tool_context_count": 0,
                    "action": "tool",
                    "tool": "records.list",
                },
            ],
            "tool_usage": [
                {
                    "name": "records.list",
                    "arguments": {},
                    "result": "model emitted [/TOOL_CALL] marker",
                },
            ],
        },
    )

    main.print_chat_debug(PinoConfig(), result)

    assert "[/TOOL_CALL]" in output.getvalue()


def test_chat_result_renders_markdown(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=100))
    result = SimpleNamespace(content="**Important** note", tool_calls=[], debug={})

    main.print_chat_result(result)

    rendered = output.getvalue()
    assert "Important note" in rendered
    assert "**Important**" not in rendered


def test_chat_result_prints_compact_tool_usage(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=100))
    result = SimpleNamespace(
        content="Done",
        tool_calls=["records.list"],
        debug={
            "tool_usage": [
                {
                    "name": "records.list",
                    "arguments": {"limit": 2},
                    "result": "hidden from compact output",
                },
            ],
        },
    )

    main.print_chat_result(result)

    rendered = output.getvalue()
    assert "-> records.list {\"limit\":2}" in rendered
    assert "hidden from compact output" not in rendered
    assert "Done" in rendered


def test_recent_chat_history_formats_stored_markdown(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_chat_message(
        ChatMessage(
            role="assistant",
            content="**recent assistant**",
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        ),
    )
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))

    main.print_recent_chat_history(store, limit=1)

    rendered = output.getvalue()
    assert "Pino> recent assistant" in rendered
    assert "**recent assistant**" not in rendered


def test_recent_chat_history_prints_chat_transcript_without_tools(tmp_path, monkeypatch) -> None:
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
            role="tool",
            content="tool implementation detail",
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
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))

    main.print_recent_chat_history(store, limit=3)

    rendered = output.getvalue()
    assert "Boss> recent user" in rendered
    assert "Pino> recent assistant" in rendered
    assert "tool implementation detail" not in rendered
    assert "old user" not in rendered
