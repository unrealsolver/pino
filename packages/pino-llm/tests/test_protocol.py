from pino_llm.protocol import parse_action


def test_parse_action_treats_plain_text_as_final() -> None:
    action = parse_action("hello")

    assert action.kind == "final"
    assert action.content == "hello"


def test_parse_action_reads_tool_request() -> None:
    action = parse_action('{"tool": "memory.list", "arguments": {"limit": 3}}')

    assert action.kind == "tool"
    assert action.tool_name == "memory.list"
    assert action.arguments == {"limit": 3}


def test_parse_action_reads_json_fenced_final() -> None:
    action = parse_action('```json\n{"final": "done"}\n```')

    assert action.kind == "final"
    assert action.content == "done"

