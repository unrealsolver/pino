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


def test_parse_action_reads_tool_call_wrapped_json() -> None:
    action = parse_action('[TOOL_CALL]\n{"tool": "records.list", "arguments": {}}\n[/TOOL_CALL]')

    assert action.kind == "tool"
    assert action.tool_name == "records.list"
    assert action.arguments == {}


def test_parse_action_reads_provider_style_tool_name() -> None:
    action = parse_action(
        '[TOOL_CALL]\n{"name": "memory.add", "arguments": "{\\"content\\": \\"x\\"}"}\n[/TOOL_CALL]',
    )

    assert action.kind == "tool"
    assert action.tool_name == "memory.add"
    assert action.arguments == {"content": "x"}


def test_parse_action_reads_first_wrapped_tool_call_list_item() -> None:
    action = parse_action('[TOOL_CALLS]\n[{"name": "memory.list", "arguments": {}}]\n[/TOOL_CALLS]')

    assert action.kind == "tool"
    assert action.tool_name == "memory.list"
    assert action.arguments == {}


def test_parse_action_extracts_json_from_extra_text() -> None:
    action = parse_action('assistant note\n{"final": "done"}\n')

    assert action.kind == "final"
    assert action.content == "done"
