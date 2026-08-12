from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

import httpx

from pino_llm.config import LLMConfig
from pino_llm.errors import LLMError
from pino_llm.messages import LLMMessage

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def complete(self, messages: list[LLMMessage]) -> str:
        """Return assistant text for the supplied messages."""


class EchoClient:
    def complete(self, messages: list[LLMMessage]) -> str:
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
    def __init__(self, config: LLMConfig, *, provider: str) -> None:
        provider_config = getattr(config.providers, provider)
        self.model = config.selected_model()
        self.provider = provider
        self.base_url = provider_config.base_url.rstrip("/")
        self.temperature = config.temperature
        self.top_p = config.top_p
        if not provider_config.api_key:
            raise LLMError(
                f"{provider} provider requires llm.providers.{provider}.api_key",
                provider=provider,
                model=self.model,
                url=f"{self.base_url}/chat/completions",
            )
        self.api_key = provider_config.api_key

    def complete(self, messages: list[LLMMessage]) -> str:
        url = f"{self.base_url}/chat/completions"
        request_body = {
            "model": self.model,
            "messages": _openai_messages(messages),
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=request_body,
                timeout=60,
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
        usage = _response_usage_diagnostics(data)
        if usage:
            logger.debug(
                "%s response usage: %s",
                self.provider,
                usage,
            )
        return data["choices"][0]["message"]["content"]


class InfercomClient(_OpenAICompatibleClient):
    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config, provider="infercom")


class MinimaxClient(_OpenAICompatibleClient):
    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config, provider="minimax")


class OllamaClient:
    def __init__(self, config: LLMConfig) -> None:
        self.model = config.selected_model()
        self.base_url = config.providers.ollama.base_url.rstrip("/")
        self.temperature = config.temperature
        self.top_p = config.top_p

    def complete(self, messages: list[LLMMessage]) -> str:
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
        try:
            response = httpx.post(
                url,
                json=request_body,
                timeout=120,
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
        return data["message"]["content"]


def build_llm_client(config: LLMConfig) -> LLMClient:
    if config.default_provider == "echo":
        return EchoClient()
    if config.default_provider == "infercom":
        return InfercomClient(config)
    if config.default_provider == "minimax":
        return MinimaxClient(config)
    if config.default_provider == "ollama":
        return OllamaClient(config)
    raise ValueError(f"Unsupported LLM provider: {config.default_provider}")


def _openai_messages(messages: list[LLMMessage]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        if message.role in {"system", "user", "assistant"}:
            normalized.append({"role": message.role, "content": message.content})
        elif message.role == "tool":
            normalized.append({"role": "user", "content": f"Tool result:\n{message.content}"})
        else:
            normalized.append({"role": "user", "content": f"{message.role} message:\n{message.content}"})
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
    diagnostic = {
        key: value
        for key, value in request_body.items()
        if key not in {"messages"}
    }
    if isinstance(messages, list):
        diagnostic["message_count"] = len(messages)
        diagnostic["message_roles"] = [
            message.get("role", "unknown")
            for message in messages
            if isinstance(message, dict)
        ]
    return diagnostic


def _response_usage_diagnostics(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return {}

    diagnostics = {
        key: usage[key]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if key in usage
    }
    prompt_details = usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict) and "cached_tokens" in prompt_details:
        diagnostics["cached_tokens"] = prompt_details["cached_tokens"]
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
        if key in usage:
            diagnostics[key] = usage[key]
    return diagnostics
