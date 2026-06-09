from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone, tzinfo
from time import monotonic
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from pino_core.config import PinoConfig, load_config
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.storage import DatabaseStore, EventQueryResult

MAX_QUERY_DAYS = 370
DEFAULT_EVENT_LIMIT = 300


class EventItem(BaseModel):
    id: str
    record_id: str
    title: str
    source: str
    url: str | None
    summary: str | None
    location: str | None
    starts_at: datetime
    ends_at: datetime | None
    original_starts_at: datetime
    original_ends_at: datetime | None
    category_scores: dict[str, float]
    matching_score: float


class EventListResponse(BaseModel):
    timezone: str
    categories: list[str]
    events: list[EventItem]


class ErrorResponse(BaseModel):
    detail: str


StoreDependency = Callable[[], DatabaseStore]


def create_app(
    *,
    config: PinoConfig | None = None,
    store: DatabaseStore | None = None,
) -> FastAPI:
    resolved_config = config or load_config()
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

    @app.middleware("http")
    async def add_hardening_headers(request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.get("/api/events", response_model=EventListResponse)
    def list_events(
        request: Request,
        date_from: Annotated[datetime | None, Query(description="Inclusive start datetime.")] = None,
        date_to: Annotated[datetime | None, Query(description="Inclusive end datetime.")] = None,
        category: Annotated[
            list[str],
            Query(description="Category names. Repeat the parameter to select multiple."),
        ] = [],
        min_score: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
        q: Annotated[str, Query(max_length=200)] = "",
        limit: Annotated[int, Query(ge=1, le=500)] = DEFAULT_EVENT_LIMIT,
        store: DatabaseStore = Depends(get_store),
    ) -> EventListResponse:
        local_timezone = ZoneInfo(DEFAULT_SOURCE_TIMEZONE)
        window_start, window_end = _resolve_window(date_from, date_to, local_timezone)
        if window_end < window_start:
            raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
        if (window_end - window_start).days > MAX_QUERY_DAYS:
            raise HTTPException(status_code=400, detail=f"date range cannot exceed {MAX_QUERY_DAYS} days")

        categories = _known_categories(request.app.state.config)
        selected_categories = _validate_categories(category, categories)
        results = store.query_events(
            window_start=window_start.astimezone(timezone.utc),
            window_end=window_end.astimezone(timezone.utc),
            categories=selected_categories,
            min_score=min_score,
            text_query=q,
            limit=limit,
        )
        return EventListResponse(
            timezone=DEFAULT_SOURCE_TIMEZONE,
            categories=categories,
            events=[
                _to_event_item(
                    result,
                    local_timezone,
                    window_start=window_start,
                    window_end=window_end,
                )
                for result in results
            ],
        )

    return app


def get_store(request: Request) -> DatabaseStore:
    return request.app.state.store


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


def _resolve_window(
    date_from: datetime | None,
    date_to: datetime | None,
    local_timezone: ZoneInfo,
) -> tuple[datetime, datetime]:
    if date_from is None:
        now = datetime.now(local_timezone)
        date_from = datetime.combine(now.date(), time.min, tzinfo=local_timezone)
    else:
        date_from = _ensure_timezone(date_from, local_timezone)
    if date_to is None:
        date_to = date_from + timedelta(days=MAX_QUERY_DAYS)
    else:
        date_to = _ensure_timezone(date_to, local_timezone)
    return date_from, date_to


def _ensure_timezone(value: datetime, local_timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=local_timezone)
    return value


def _known_categories(config: PinoConfig) -> list[str]:
    return [category.name for category in config.refinement.categories]


def _validate_categories(values: list[str], known_categories: list[str]) -> list[str]:
    selected = [value.strip() for value in values if value.strip()]
    unknown = sorted(set(selected) - set(known_categories))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"unknown category: {', '.join(unknown)}",
        )
    return selected


def _to_event_item(
    result: EventQueryResult,
    local_timezone: tzinfo,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> EventItem:
    record = result.record
    refinement = result.refinement
    if refinement.relevant_from is None:
        raise ValueError("event query returned an undated refinement")
    starts_at = max(refinement.relevant_from, window_start) if window_start else refinement.relevant_from
    ends_at = refinement.relevant_to
    if ends_at is not None and window_end is not None:
        ends_at = min(ends_at, window_end)
    return EventItem(
        id=refinement.id,
        record_id=record.id,
        title=record.title or refinement.summary or "Untitled event",
        source=record.source,
        url=record.url,
        summary=refinement.summary,
        location=refinement.location,
        starts_at=starts_at.astimezone(local_timezone),
        ends_at=ends_at.astimezone(local_timezone) if ends_at is not None else None,
        original_starts_at=refinement.relevant_from.astimezone(local_timezone),
        original_ends_at=refinement.relevant_to.astimezone(local_timezone)
        if refinement.relevant_to is not None
        else None,
        category_scores=refinement.category_scores,
        matching_score=result.score,
    )
