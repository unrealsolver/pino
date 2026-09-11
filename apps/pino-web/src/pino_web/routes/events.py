from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from pino_web.deps import get_event_service
from pino_web.schemas import EventListResponse
from pino_web.services.events import (
    DEFAULT_EVENT_LIMIT,
    EventFilters,
    EventQueryError,
    EventService,
)

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events", response_model=EventListResponse)
def list_events(
    service: Annotated[EventService, Depends(get_event_service)],
    date_from: Annotated[datetime | None, Query(description="Inclusive start datetime.")] = None,
    date_to: Annotated[datetime | None, Query(description="Inclusive end datetime.")] = None,
    category: Annotated[
        list[str] | None,
        Query(max_length=64, description="Category names. Repeat to select up to 64."),
    ] = None,
    min_score: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=500)] = DEFAULT_EVENT_LIMIT,
) -> EventListResponse:
    try:
        filters = EventFilters(
            date_from=date_from,
            date_to=date_to,
            categories=category or [],
            min_score=min_score,
            query=q,
            limit=limit,
        )
        return service.list_events(filters=filters)
    except EventQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
