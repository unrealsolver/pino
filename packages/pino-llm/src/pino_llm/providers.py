from __future__ import annotations

import json
import logging
import re
from time import perf_counter
from typing import Any, Protocol

import httpx

from pino_llm.config import LLMConfig
from pino_llm.errors import LLMError
from pino_llm.messages import LLMMessage
from pino_llm.usage import LLMUsage, UsageRecorder

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def complete(self, messages: list[LLMMessage], *, operation: str = "unknown") -> str:
        """Return assistant text for the supplied messages."""


class EchoClient:
    def complete(self, messages: list[LLMMessage], *, operation: str = "unknown") -> str:
        last_user_index = _last_role_index(messages, "user")
        last_tool_index = _last_role_index(messages, "tool")
        if last_tool_index is not None and (
            last_user_index is None or last_tool_index > last_user_index
        ):
            return f"Boss, tool result:\n{messages[last_tool_index].content}"

        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        lower = last_user.lower()

        if lower.startswith("remember "):
            content = last_user[len("remember ") :].strip()
            return json.dumps({"tool": "memory.add", "arguments": {"content": content}})
        if "memory" in lower and ("list" in lower or "show" in lower):
            return '{"tool": "memory.list", "arguments": {}}'
        if "digest" in lower:
            return '{"tool": "digest.create", "arguments": {}}'
        if "check" in lower or "source" in lower:
            return '{"tool": "sources.check", "arguments": {}}'
        if "record" in lower:
            return '{"tool": "records.relevant", "arguments": {}}'
        url_match = re.search(r"https?://\S+", last_user)
        if url_match is not None:
            return json.dumps({"tool": "web.open", "arguments": {"url": url_match.group(0)}})

        return "Boss, echo provider is configured. I can test local tools, but not real language reasoning."


class _OpenAICompatibleClient:
    def __init__(
        self,
        config: LLMConfig,
        *,
        provider: str,
        usage_recorder: UsageRecorder | None = None,
        timeout_seconds: float = 60,
    ) -> None:
        profile = config.selected_profile()
        if profile.provider != provider:
            raise ValueError(
                f"model profile {config.model!r} uses {profile.provider!r}, not {provider!r}"
            )
        provider_config = getattr(config.providers, provider)
        self.model = profile.model
        self.provider = provider
        self.base_url = provider_config.base_url.rstrip("/")
        self.temperature = profile.temperature
        self.top_p = profile.top_p
        self.usage_recorder = usage_recorder
        self.timeout_seconds = timeout_seconds
        self.last_reasoning: str | None = None
        if not provider_config.api_key:
            raise LLMError(
                f"{provider} provider requires llm.providers.{provider}.api_key",
                provider=provider,
                model=self.model,
                url=f"{self.base_url}/chat/completions",
            )
        self.api_key = provider_config.api_key

    def complete(self, messages: list[LLMMessage], *, operation: str = "unknown") -> str:
        self.last_reasoning = None
        url = f"{self.base_url}/chat/completions"
        request_body = {
            "model": self.model,
            "messages": _openai_messages(messages),
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        started = perf_counter()
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=request_body,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _provider_http_error(
                exc,
                provider=self.provider,
                model=self.model,
                request_body=request_body,
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(
                f"{self.provider} request failed: {exc}",
                provider=self.provider,
                model=self.model,
                url=url,
                request=_diagnostic_request(request_body),
            ) from exc
        data = response.json()
        duration_ms = _duration_ms(started)
        usage = _openai_usage_from_response(
            data,
            provider=self.provider,
            model=self.model,
            operation=operation,
            duration_ms=duration_ms,
        )
        if usage:
            logger.debug(
                "%s response usage: %s",
                self.provider,
                _usage_diagnostics(usage),
            )
            if self.usage_recorder is not None:
                self.usage_recorder(usage)
        message = data["choices"][0]["message"]
        reasoning = message.get("reasoning_content") or message.get("thinking")
        if isinstance(reasoning, str) and reasoning.strip():
            self.last_reasoning = reasoning
        return message["content"]


class InfercomClient(_OpenAICompatibleClient):
    def __init__(
        self,
        config: LLMConfig,
        *,
        usage_recorder: UsageRecorder | None = None,
        timeout_seconds: float = 60,
    ) -> None:
        super().__init__(
            config,
            provider="infercom",
            usage_recorder=usage_recorder,
            timeout_seconds=timeout_seconds,
        )


class MinimaxClient(_OpenAICompatibleClient):
    def __init__(
        self,
        config: LLMConfig,
        *,
        usage_recorder: UsageRecorder | None = None,
        timeout_seconds: float = 60,
    ) -> None:
        super().__init__(
            config,
            provider="minimax",
            usage_recorder=usage_recorder,
            timeout_seconds=timeout_seconds,
        )


class OllamaClient:
    def __init__(
        self,
        config: LLMConfig,
        *,
        usage_recorder: UsageRecorder | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        profile = config.selected_profile()
        if profile.provider != "ollama":
            raise ValueError(
                f"model profile {config.model!r} uses {profile.provider!r}, not 'ollama'"
            )
        self.model = profile.model
        self.base_url = config.providers.ollama.base_url.rstrip("/")
        self.temperature = profile.temperature
        self.top_p = profile.top_p
        self.think = profile.think
        self.num_ctx = profile.num_ctx
        self.num_predict = profile.num_predict
        self.usage_recorder = usage_recorder
        self.timeout_seconds = timeout_seconds
        self.last_reasoning: str | None = None
        self.last_output_tokens: int | None = None
        self.last_generation_duration_ms: float | None = None
        self.last_tokens_per_second: float | None = None

    def complete(self, messages: list[LLMMessage], *, operation: str = "unknown") -> str:
        self.last_reasoning = None
        self.last_output_tokens = None
        self.last_generation_duration_ms = None
        self.last_tokens_per_second = None
        url = f"{self.base_url}/api/chat"
        request_body = {
            "model": self.model,
            "messages": _ollama_messages(messages),
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
            },
        }
        if self.think is not None:
            request_body["think"] = self.think
        if self.num_ctx is not None:
            request_body["options"]["num_ctx"] = self.num_ctx
        if self.num_predict is not None:
            request_body["options"]["num_predict"] = self.num_predict
        started = perf_counter()
        try:
            response = httpx.post(
                url,
                json=request_body,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _provider_http_error(
                exc,
                provider="ollama",
                model=self.model,
                request_body=request_body,
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(
                f"ollama request failed: {exc}",
                provider="ollama",
                model=self.model,
                url=url,
                request=_diagnostic_request(request_body),
            ) from exc
        data = response.json()
        usage = _ollama_usage_from_response(
            data,
            provider="ollama",
            model=self.model,
            operation=operation,
            duration_ms=_duration_ms(started),
        )
        if usage and self.usage_recorder is not None:
            self.usage_recorder(usage)
        output_tokens = _integer_usage_value(data.get("eval_count"))
        eval_duration_ns = _integer_usage_value(data.get("eval_duration"))
        if output_tokens is not None and eval_duration_ns is not None:
            self.last_output_tokens = output_tokens
            self.last_generation_duration_ms = eval_duration_ns / 1_000_000
            if eval_duration_ns > 0:
                self.last_tokens_per_second = round(
                    output_tokens * 1_000_000_000 / eval_duration_ns,
                    2,
                )
        message = data["message"]
        reasoning = message.get("thinking")
        if isinstance(reasoning, str) and reasoning.strip():
            self.last_reasoning = reasoning
        return message["content"]


def build_llm_client(
    config: LLMConfig,
    *,
    usage_recorder: UsageRecorder | None = None,
    timeout_seconds: float | None = None,
) -> LLMClient:
    provider = config.selected_provider()
    if provider == "echo":
        return EchoClient()
    if provider == "infercom":
        return InfercomClient(
            config,
            usage_recorder=usage_recorder,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else 60,
        )
    if provider == "minimax":
        return MinimaxClient(
            config,
            usage_recorder=usage_recorder,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else 60,
        )
    if provider == "ollama":
        return OllamaClient(
            config,
            usage_recorder=usage_recorder,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else 120,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


def _openai_messages(messages: list[LLMMessage]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        if message.role in {"system", "user", "assistant"}:
            normalized.append({"role": message.role, "content": message.content})
        elif message.role == "tool":
            normalized.append({"role": "user", "content": f"Tool result:\n{message.content}"})
        else:
            normalized.append(
                {"role": "user", "content": f"{message.role} message:\n{message.content}"}
            )
    return normalized


def _ollama_messages(messages: list[LLMMessage]) -> list[dict[str, str]]:
    return _openai_messages(messages)


def _last_role_index(messages: list[LLMMessage], role: str) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == role:
            return index
    return None


def _provider_http_error(
    exc: httpx.HTTPStatusError,
    *,
    provider: str,
    model: str,
    request_body: dict[str, Any],
) -> LLMError:
    response = exc.response
    return LLMError(
        f"{provider} returned HTTP {response.status_code}",
        provider=provider,
        model=model,
        url=str(response.url),
        status_code=response.status_code,
        response_body=response.text[:4000],
        request=_diagnostic_request(request_body),
    )


def _diagnostic_request(request_body: dict[str, Any]) -> dict[str, Any]:
    messages = request_body.get("messages", [])
    diagnostic = {key: value for key, value in request_body.items() if key not in {"messages"}}
    if isinstance(messages, list):
        diagnostic["message_count"] = len(messages)
        diagnostic["message_roles"] = [
            message.get("role", "unknown") for message in messages if isinstance(message, dict)
        ]
    return diagnostic


def _openai_usage_from_response(
    data: dict[str, Any],
    *,
    provider: str,
    model: str,
    operation: str,
    duration_ms: int,
) -> LLMUsage | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = _integer_usage_value(usage.get("prompt_tokens"))
    output_tokens = _integer_usage_value(usage.get("completion_tokens"))
    if input_tokens is None or output_tokens is None:
        input_tokens = _integer_usage_value(usage.get("input_tokens"))
        output_tokens = _integer_usage_value(usage.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return None

    cached_input_tokens = 0
    prompt_details = usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict) and "cached_tokens" in prompt_details:
        cached_input_tokens = _integer_usage_value(prompt_details.get("cached_tokens")) or 0
    if "cache_read_input_tokens" in usage:
        cached_input_tokens = _integer_usage_value(usage.get("cache_read_input_tokens")) or 0

    return LLMUsage(
        provider=provider,
        model=model,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        duration_ms=duration_ms,
    )


def _ollama_usage_from_response(
    data: dict[str, Any],
    *,
    provider: str,
    model: str,
    operation: str,
    duration_ms: int,
) -> LLMUsage | None:
    input_tokens = _integer_usage_value(data.get("prompt_eval_count"))
    output_tokens = _integer_usage_value(data.get("eval_count"))
    if input_tokens is None or output_tokens is None:
        return None
    return LLMUsage(
        provider=provider,
        model=model,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=0,
        duration_ms=duration_ms,
    )


def _usage_diagnostics(usage: LLMUsage) -> dict[str, int | str]:
    return {
        "operation": usage.operation,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "duration_ms": usage.duration_ms,
    }


def _integer_usage_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(0, value)
    return None


def _duration_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
