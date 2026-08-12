import httpx
import pytest

from pino_llm.config import LLMConfig
from pino_llm.errors import LLMError
from pino_llm.messages import LLMMessage
from pino_llm.providers import (
    EchoClient,
    build_llm_client,
    _openai_messages,
    _provider_http_error,
    _response_usage_diagnostics,
)


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


def test_response_usage_diagnostics_include_cached_tokens() -> None:
    diagnostics = _response_usage_diagnostics(
        {
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 300,
                "total_tokens": 1500,
                "prompt_tokens_details": {"cached_tokens": 800},
            },
        },
    )

    assert diagnostics == {
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "total_tokens": 1500,
        "cached_tokens": 800,
    }


def test_infercom_client_requires_api_key_when_selected() -> None:
    with pytest.raises(LLMError, match="api_key"):
        build_llm_client(LLMConfig(default_provider="infercom"))


def test_minimax_client_requires_api_key_when_selected() -> None:
    with pytest.raises(LLMError, match="llm.providers.minimax.api_key"):
        build_llm_client(LLMConfig(default_provider="minimax"))


def test_echo_client_can_request_web_open_for_urls() -> None:
    response = EchoClient().complete(
        [LLMMessage(role="user", content="open https://example.com/event")],
    )

    assert response == '{"tool": "web.open", "arguments": {"url": "https://example.com/event"}}'
