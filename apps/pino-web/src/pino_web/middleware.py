from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from time import monotonic

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, *, limit: int, window_seconds: int) -> None:
        super().__init__(app)
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client = request.client.host if request.client else "unknown"
        now = monotonic()
        history = self._requests[client]
        while history and now - history[0] >= self.window_seconds:
            history.popleft()
        if len(history) >= self.limit:
            return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})
        history.append(now)
        return await call_next(request)
