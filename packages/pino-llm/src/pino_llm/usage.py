from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMUsage:
    provider: str
    model: str
    operation: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    duration_ms: int


class UsageRecorder(Protocol):
    def __call__(self, usage: LLMUsage) -> None:
        """Record normalized token usage for one completed LLM request."""
