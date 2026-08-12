from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EventItem(BaseModel):
    refinement_id: str
    occurrence_id: str
    title: str
    source: str
    url: str | None
    summary: str | None
    location: str | None
    starts_at: datetime
    ends_at: datetime | None
    relevant_from: datetime
    relevant_to: datetime | None
    category_scores: dict[str, float]
    matching_score: float


class EventListResponse(BaseModel):
    timezone: str
    categories: list[str]
    events: list[EventItem]


class ErrorResponse(BaseModel):
    detail: str
