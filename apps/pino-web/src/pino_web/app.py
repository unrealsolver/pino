from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response

from pino_core.config import PinoConfig, load_config
from pino_core.storage import DatabaseStore
from pino_web.middleware import RateLimitMiddleware
from pino_web.routes import router
from pino_web.schemas import ErrorResponse


def create_app(
    *,
    config: PinoConfig | None = None,
    config_path: Path | None = None,
    store: DatabaseStore | None = None,
) -> FastAPI:
    resolved_config = config or load_config(config_path)
    resolved_store = store or DatabaseStore(resolved_config.storage.database_url())
    resolved_store.init_schema()
    app = FastAPI(
        title="Pino Web API",
        version="0.1.0",
        responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    app.add_middleware(RateLimitMiddleware, limit=60, window_seconds=60)
    app.state.config = resolved_config
    app.state.store = resolved_store
    app.include_router(router)

    @app.middleware("http")
    async def add_hardening_headers(request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    return app
