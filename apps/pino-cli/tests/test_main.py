from io import StringIO
from types import SimpleNamespace

from rich.console import Console

from pino_cli import main
from pino_core.config import PinoConfig


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
