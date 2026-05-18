import httpx

from pino_llm.errors import LLMError
from pino_llm.messages import LLMMessage
from pino_llm.providers import _openai_messages, _provider_http_error


def test_openai_messages_convert_tool_roles_to_user_context() -> None:
    messages = [
        LLMMessage(role="system", content="system"),
        LLMMessage(role="user", content="hello"),
        LLMMessage(role="tool", content="tool output"),
    ]

    assert _openai_messages(messages) == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "Tool result:\ntool output"},
    ]


def test_provider_http_error_contains_sanitized_request_diagnostics() -> None:
    request = httpx.Request("POST", "https://api.infercom.ai/v1/chat/completions")
    response = httpx.Response(
        400,
        request=request,
        text='{"error":"bad request"}',
    )
    original = httpx.HTTPStatusError("bad request", request=request, response=response)

    error = _provider_http_error(
        original,
        provider="infercom",
        model="MiniMax-M2.5",
        request_body={
            "model": "MiniMax-M2.5",
            "messages": [
                {"role": "system", "content": "secret-ish prompt"},
                {"role": "user", "content": "private user text"},
            ],
            "temperature": 0.1,
            "top_p": 0.1,
        },
    )

    assert isinstance(error, LLMError)
    assert error.status_code == 400
    assert error.response_body == '{"error":"bad request"}'
    assert error.request == {
        "model": "MiniMax-M2.5",
        "temperature": 0.1,
        "top_p": 0.1,
        "message_count": 2,
        "message_roles": ["system", "user"],
    }

