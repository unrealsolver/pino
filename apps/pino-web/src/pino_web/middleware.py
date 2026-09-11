from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable
from math import ceil
from time import monotonic

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: FastAPI, *, limit: int, window_seconds: int, max_clients: int = 4096
    ) -> None:
        super().__init__(app)
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._requests: OrderedDict[str, deque[float]] = OrderedDict()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not request.url.path.startswith("/api/") or request.url.path == "/api/health":
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = monotonic()
        while self._requests:
            oldest = next(iter(self._requests.values()))
            if now - oldest[-1] < self.window_seconds:
                break
            self._requests.popitem(last=False)
        history = self._requests.get(client, deque())
        while history and now - history[0] >= self.window_seconds:
            history.popleft()
        if len(history) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded"},
                headers={
                    "Retry-After": str(max(1, ceil(self.window_seconds - (now - history[0]))))
                },
            )
        history.append(now)
        self._requests[client] = history
        self._requests.move_to_end(client)
        if len(self._requests) > self.max_clients:
            self._requests.popitem(last=False)
        return await call_next(request)
