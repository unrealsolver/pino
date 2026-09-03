import httpx
import pytest

from pino_llm.config import LLMConfig
from pino_llm.errors import LLMError
from pino_llm.messages import LLMMessage
from pino_llm.providers import (
    EchoClient,
    OllamaClient,
    build_llm_client,
    _ollama_usage_from_response,
    _openai_messages,
    _openai_usage_from_response,
    _provider_http_error,
)
from pino_llm.usage import LLMUsage


def llm_config(provider: str, model: str, **profile_options) -> LLMConfig:
    reference = f"{provider}:test"
    return LLMConfig(
        model=reference,
        models={
            provider: {
                "test": {
                    "model": model,
                    **profile_options,
                }
            }
        },
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


def test_ollama_client_preserves_native_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    config = llm_config(
        "ollama",
        "gemma4:e4b",
        temperature=0,
        top_p=0.2,
        think=False,
        num_ctx=4096,
        num_predict=768,
    )
    seen_request = {}

    def fake_post(*args, **kwargs):
        seen_request.update(kwargs["json"])
        seen_request["timeout"] = kwargs["timeout"]
        request = httpx.Request("POST", "http://localhost:11434/api/chat")
        return httpx.Response(
            200,
            request=request,
            json={
                "message": {
                    "role": "assistant",
                    "thinking": "check the calendar claims",
                    "content": '{"items": []}',
                },
                "prompt_eval_count": 10,
                "eval_count": 5,
                "eval_duration": 250_000_000,
            },
        )

    monkeypatch.setattr("pino_llm.providers.httpx.post", fake_post)

    client = OllamaClient(config, timeout_seconds=15)
    result = client.complete([LLMMessage(role="user", content="hello")], operation="refine")

    assert result == '{"items": []}'
    assert getattr(client, "last_reasoning") == "check the calendar claims"
    assert client.last_output_tokens == 5
    assert client.last_generation_duration_ms == 250.0
    assert client.last_tokens_per_second == 20.0
    assert seen_request["model"] == "gemma4:e4b"
    assert seen_request["think"] is False
    assert seen_request["options"] == {
        "temperature": 0.0,
        "top_p": 0.2,
        "num_ctx": 4096,
        "num_predict": 768,
    }
    assert seen_request["timeout"] == 15
    assert OllamaClient(config).timeout_seconds == 120


def test_openai_compatible_client_records_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[LLMUsage] = []
    seen_request = {}
    config = LLMConfig.model_validate(
        {
            "model": "minimax:chat",
            "models": {
                "minimax": {
                    "chat": {
                        "model": "MiniMax-M3",
                    }
                }
            },
            "providers": {"minimax": {"api_key": "test-key"}},
        },
    )

    def fake_post(*args, **kwargs):
        seen_request.update(kwargs)
        request = httpx.Request("POST", "https://api.minimax.io/v1/chat/completions")
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"message": {"reasoning_content": "brief reasoning", "content": "ok"}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "prompt_tokens_details": {"cached_tokens": 4},
                },
            },
        )

    monkeypatch.setattr("pino_llm.providers.httpx.post", fake_post)

    client = build_llm_client(
        config,
        usage_recorder=recorded.append,
        timeout_seconds=15,
    )
    result = client.complete([LLMMessage(role="user", content="hello")], operation="chat")

    assert result == "ok"
    assert len(recorded) == 1
    assert recorded[0].provider == "minimax"
    assert recorded[0].model == "MiniMax-M3"
    assert recorded[0].operation == "chat"
    assert recorded[0].input_tokens == 10
    assert recorded[0].output_tokens == 3
    assert recorded[0].cached_input_tokens == 4
    assert seen_request["timeout"] == 15
    assert getattr(client, "last_reasoning") == "brief reasoning"


def test_infercom_client_requires_api_key_when_selected() -> None:
    with pytest.raises(LLMError, match="api_key"):
        build_llm_client(llm_config("infercom", "MiniMax-M2.5"))


def test_minimax_client_requires_api_key_when_selected() -> None:
    with pytest.raises(LLMError, match="llm.providers.minimax.api_key"):
        build_llm_client(llm_config("minimax", "MiniMax-M3"))


def test_echo_client_can_request_web_open_for_urls() -> None:
    response = EchoClient().complete(
        [LLMMessage(role="user", content="open https://example.com/event")],
    )

    assert response == '{"tool": "web.open", "arguments": {"url": "https://example.com/event"}}'
