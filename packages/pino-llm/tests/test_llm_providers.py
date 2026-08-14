import httpx
import pytest

from pino_llm.config import LLMConfig
from pino_llm.errors import LLMError
from pino_llm.messages import LLMMessage
from pino_llm.providers import (
    EchoClient,
    build_llm_client,
    _ollama_usage_from_response,
    _openai_messages,
    _openai_usage_from_response,
    _provider_http_error,
)
from pino_llm.usage import LLMUsage


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


def test_openai_usage_from_response_normalizes_cached_tokens() -> None:
    usage = _openai_usage_from_response(
        {
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 300,
                "prompt_tokens_details": {"cached_tokens": 800},
            },
        },
        provider="minimax",
        model="MiniMax-M3",
        operation="refinement.extract",
        duration_ms=1234,
    )

    assert usage == LLMUsage(
        provider="minimax",
        model="MiniMax-M3",
        operation="refinement.extract",
        input_tokens=1200,
        output_tokens=300,
        cached_input_tokens=800,
        duration_ms=1234,
    )


def test_ollama_usage_from_response_normalizes_eval_counts() -> None:
    usage = _ollama_usage_from_response(
        {"prompt_eval_count": 42, "eval_count": 12},
        provider="ollama",
        model="gpt-oss-20b",
        operation="chat",
        duration_ms=99,
    )

    assert usage == LLMUsage(
        provider="ollama",
        model="gpt-oss-20b",
        operation="chat",
        input_tokens=42,
        output_tokens=12,
        cached_input_tokens=0,
        duration_ms=99,
    )


def test_openai_compatible_client_records_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[LLMUsage] = []
    config = LLMConfig.model_validate(
        {
            "default_provider": "minimax",
            "providers": {"minimax": {"api_key": "test-key"}},
        },
    )

    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", "https://api.minimax.io/v1/chat/completions")
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "prompt_tokens_details": {"cached_tokens": 4},
                },
            },
        )

    monkeypatch.setattr("pino_llm.providers.httpx.post", fake_post)

    client = build_llm_client(config, usage_recorder=recorded.append)
    result = client.complete([LLMMessage(role="user", content="hello")], operation="chat")

    assert result == "ok"
    assert len(recorded) == 1
    assert recorded[0].provider == "minimax"
    assert recorded[0].model == "MiniMax-M3"
    assert recorded[0].operation == "chat"
    assert recorded[0].input_tokens == 10
    assert recorded[0].output_tokens == 3
    assert recorded[0].cached_input_tokens == 4


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
