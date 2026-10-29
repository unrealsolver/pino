from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EventItem(BaseModel):
    images: list[str] = Field(default_factory=list)
    refinement_id: str
    occurrence_id: str
    title: str
    text: str = ""
    source: str
    url: str | None
    location: str | None
    city_id: str | None = None
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


class CityItem(BaseModel):
    id: str
    country_code: str
    slug: str
    name: str
    timezone: str


class CityListResponse(BaseModel):
    cities: list[CityItem]


class StatsRefinementItemCounts(BaseModel):
    """Current refinement output items, with every content kind explicit."""

    model_config = ConfigDict(extra="forbid")

    event: int = Field(default=0, ge=0)
    advertisement: int = Field(default=0, ge=0)
    announcement: int = Field(default=0, ge=0)
    non_event: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)


class StatsRecordMetrics(BaseModel):
    """Raw record counts, kept separate from refinement output items."""

    model_config = ConfigDict(extra="forbid")

    records_total: int = Field(ge=0)
    records_with_refinement_total: int = Field(ge=0)
    pending_records_total: int = Field(ge=0)
    oldest_pending_captured_at: datetime | None = None
    latest_captured_at: datetime | None = None


class StatsRefinementMetrics(BaseModel):
    """Current refinement output item counts."""

    model_config = ConfigDict(extra="forbid")

    refinement_items_total: int = Field(ge=0)
    refinement_items_by_kind: StatsRefinementItemCounts
    event_items_total: int = Field(ge=0)
    last_refined_at: datetime | None = None


class StatsIngestionWeek(BaseModel):
    """One Monday-start half-open ingestion week in the reporting timezone."""

    model_config = ConfigDict(extra="forbid")

    week_start: date
    week_end: date
    starts_at: datetime
    ends_at: datetime
    is_partial: bool
    records: int = Field(ge=0)
    with_refinement: int = Field(ge=0)
    pending: int = Field(ge=0)


class StatsSource(BaseModel):
    """Per-source ingestion, coverage, and refinement output."""

    model_config = ConfigDict(extra="forbid")

    source: str
    ingestion: StatsRecordMetrics
    refinement: StatsRefinementMetrics
    weeks: list[StatsIngestionWeek]


class StatsTotals(BaseModel):
    """All-time totals over every observed source."""

    model_config = ConfigDict(extra="forbid")

    ingestion: StatsRecordMetrics
    refinement: StatsRefinementMetrics


class StatsCity(BaseModel):
    """Registry metadata plus current event refinement output for one city."""

    model_config = ConfigDict(extra="forbid")

    city_id: str
    country_code: str
    slug: str
    name: str
    timezone: str
    event_items_total: int = Field(ge=0)
    sources_with_event_items: int = Field(ge=0)


class StatsResponse(BaseModel):
    """Read-only stored source ingestion and refinement statistics."""

    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    reporting_timezone: str
    ingestion_time_basis: Literal["captured_at"] = "captured_at"
    weeks: list[StatsIngestionWeek]
    totals: StatsTotals
    sources: list[StatsSource]
    cities: list[StatsCity]
    supported_cities_total: int = Field(ge=0)
    unassigned_city_event_items_total: int = Field(ge=0)
    unsupported_city_event_items_total: int = Field(ge=0)


class ErrorResponse(BaseModel):
    detail: str
