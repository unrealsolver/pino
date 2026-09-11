from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pino_core.config import PinoConfig, load_config
from pino_core.db import require_current_schema
from pino_core.storage import DatabaseStore
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from pino_web.middleware import RateLimitMiddleware
from pino_web.routes import router
from pino_web.schemas import ErrorResponse

API_TIMEOUT_SECONDS = 10


def create_app(
    *,
    config: PinoConfig | None = None,
    config_path: Path | None = None,
    store: DatabaseStore | None = None,
    serve_media: bool = False,
    migrate: bool = True,
) -> FastAPI:
    resolved_config = config or load_config(config_path)
    resolved_store = store or DatabaseStore(resolved_config.storage.database_url())
    if migrate:
        resolved_store.init_schema()
    else:
        require_current_schema(resolved_store.engine)
    app = FastAPI(
        title="Pino Web API",
        version="0.1.0",
        responses={
            400: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
            504: {"model": ErrorResponse},
        },
    )
    app.add_middleware(RateLimitMiddleware, limit=60, window_seconds=60)
    app.state.config = resolved_config
    app.state.store = resolved_store
    app.include_router(router)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logging.getLogger(__name__).error("Database request failed", exc_info=exc)
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict[str, str]:
        with resolved_store.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    media_mount = None
    if serve_media:
        media_mount = urlsplit(resolved_config.media.public_url).path.rstrip("/") or "/media"
        if media_mount == "/api" or media_mount.startswith("/api/"):
            raise ValueError("media URL must not overlap /api")
        resolved_config.media.directory.mkdir(parents=True, exist_ok=True)
        app.mount(media_mount, StaticFiles(directory=resolved_config.media.directory), name="media")

    @app.middleware("http")
    async def add_hardening_headers(request: Request, call_next: Callable) -> Response:
        if request.url.path == "/api" or request.url.path.startswith("/api/"):
            deadline = asyncio.timeout(API_TIMEOUT_SECONDS)
            try:
                async with deadline:
                    response = await call_next(request)
            except TimeoutError:
                if not deadline.expired():
                    raise
                logging.getLogger(__name__).warning("API request exceeded 10-second deadline")
                response = JSONResponse(status_code=504, content={"detail": "Request timed out"})
        else:
            response = await call_next(request)
        if (
            media_mount
            and request.url.path.startswith(media_mount + "/")
            and response.status_code == 200
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    return app
