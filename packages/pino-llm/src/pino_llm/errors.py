from __future__ import annotations

from typing import Any


class LLMError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        url: str,
        status_code: int | None = None,
        response_body: str | None = None,
        request: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.url = url
        self.status_code = status_code
        self.response_body = response_body
        self.request = request or {}

