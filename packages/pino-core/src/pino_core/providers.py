from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol

import httpx

from pino_core.config import LLMConfig


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


class LLMProvider(Protocol):
    def complete(self, messages: list[LLMMessage]) -> str:
        """Return assistant text for the supplied messages."""


class EchoProvider:
    def complete(self, messages: list[LLMMessage]) -> str:
        last_tool = next((m.content for m in reversed(messages) if m.role == "tool"), None)
        if last_tool:
            return json.dumps({"final": f"Boss, tool result:\n{last_tool}"})

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
            return '{"tool": "records.list", "arguments": {}}'

        return '{"final": "Boss, echo provider is configured. I can test local tools, but not real language reasoning."}'


class InfercomProvider:
    def __init__(self, config: LLMConfig) -> None:
        self.model = config.selected_model()
        self.base_url = config.infercom.base_url.rstrip("/")
        self.temperature = config.temperature
        self.top_p = config.top_p
        self.api_key = config.infercom.api_key_file.read_text(encoding="utf-8").strip()

    def complete(self, messages: list[LLMMessage]) -> str:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [message.__dict__ for message in messages],
                "temperature": self.temperature,
                "top_p": self.top_p,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


class OllamaProvider:
    def __init__(self, config: LLMConfig) -> None:
        self.model = config.selected_model()
        self.base_url = config.ollama.base_url.rstrip("/")
        self.temperature = config.temperature
        self.top_p = config.top_p

    def complete(self, messages: list[LLMMessage]) -> str:
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [message.__dict__ for message in messages],
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]


def build_provider(config: LLMConfig) -> LLMProvider:
    if config.provider == "echo":
        return EchoProvider()
    if config.provider == "infercom":
        return InfercomProvider(config)
    if config.provider == "ollama":
        return OllamaProvider(config)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")
