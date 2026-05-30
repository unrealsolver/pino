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


def test_parse_action_still_accepts_exact_json_fenced_final() -> None:
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


def test_parse_action_reads_wrapped_tool_call_list_items() -> None:
    action = parse_action(
        '[TOOL_CALLS]\n[{"name": "memory.list", "arguments": {}}, '
        '{"name": "records.list", "arguments": {"limit": 2}}]\n[/TOOL_CALLS]',
    )

    assert action.kind == "tool"
    assert action.tool_name == "memory.list"
    assert action.arguments == {}
    assert [(call.name, call.arguments) for call in action.tool_calls] == [
        ("memory.list", {}),
        ("records.list", {"limit": 2}),
    ]


def test_parse_action_reads_explicit_multi_tool_request() -> None:
    action = parse_action(
        '{"tools": [{"tool": "web.open", "arguments": {"url": "https://example.com/a"}}, '
        '{"tool": "web.open", "arguments": {"url": "https://example.com/b"}}]}',
    )

    assert [(call.name, call.arguments) for call in action.tool_calls] == [
        ("web.open", {"url": "https://example.com/a"}),
        ("web.open", {"url": "https://example.com/b"}),
    ]


def test_parse_action_does_not_extract_final_json_from_extra_text() -> None:
    action = parse_action('assistant note\n{"final": "done"}\n')

    assert action.kind == "final"
    assert action.content == 'assistant note\n{"final": "done"}\n'


def test_parse_action_extracts_tool_json_from_extra_text() -> None:
    action = parse_action('assistant note\n{"tool": "memory.list", "arguments": {"limit": 3}}\n')

    assert action.kind == "tool"
    assert action.tool_name == "memory.list"
    assert action.arguments == {"limit": 3}


def test_parse_action_reads_multiple_calls_from_concatenated_model_output() -> None:
    action = parse_action(
        '{"tool": "web.open", "arguments": {"url": "https://www.delfi.lt/pagrindinis/", '
        '"max_chars": 3000}} [TOOL_CALL] {"tool": "web.open", "arguments": {"url": '
        '"https://www.google.com/search?q=festivalis", "max_chars": 2000}} [/TOOL_CALL]',
    )

    assert action.kind == "tool"
    assert action.tool_name == "web.open"
    assert action.arguments == {
        "url": "https://www.delfi.lt/pagrindinis/",
        "max_chars": 3000,
    }
    assert [(call.name, call.arguments) for call in action.tool_calls] == [
        (
            "web.open",
            {
                "url": "https://www.delfi.lt/pagrindinis/",
                "max_chars": 3000,
            },
        ),
        (
            "web.open",
            {
                "url": "https://www.google.com/search?q=festivalis",
                "max_chars": 2000,
            },
        ),
    ]


def test_parse_action_skips_embedded_final_json_before_tool_call() -> None:
    action = parse_action(
        'assistant note {"final": "not an exact final"} '
        '{"tool": "memory.list", "arguments": {"limit": 3}}',
    )

    assert action.kind == "tool"
    assert action.tool_name == "memory.list"
    assert action.arguments == {"limit": 3}


def test_parse_action_reads_loose_provider_tool_call_with_cli_style_arguments() -> None:
    action = parse_action("[TOOL_CALL] {tool => 'records.list', arguments => { --limit 50 }} [/TOOL_CALL]")

    assert action.kind == "tool"
    assert action.tool_name == "records.list"
    assert action.arguments == {"limit": 50}
