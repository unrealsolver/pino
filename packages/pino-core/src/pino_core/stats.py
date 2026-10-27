"""Typed read model for stored source ingestion and refinement statistics.

The report describes current stored data only. It never fetches sources, writes
to the database, or consults a capped event query.

``records.captured_at`` is used as the ingestion-time proxy with the explicit
``captured_at`` basis. It is the original capture time retained on first insert,
so duplicate fetches do not count again. Imported or static records may carry a
historical capture time; these values are not database insertion timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from pino_core.cities import CITY_REGISTRY, list_cities, normalize_city_id
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE

if TYPE_CHECKING:
    from pino_core.storage import DatabaseStore

REFINEMENT_CONTENT_KINDS: tuple[str, ...] = (
    "event",
    "advertisement",
    "announcement",
    "non_event",
    "unknown",
)


@dataclass(frozen=True)
class WeekRecordCount:
    """Stored aggregate for one ingestion week, before zero filling."""

    index: int
    records: int
    pending: int

    @property
    def with_refinement(self) -> int:
        return self.records - self.pending


@dataclass(frozen=True)
class RecordTotalsAggregate:
    records_total: int
    records_with_refinement_total: int
    pending_records_total: int
    oldest_pending_captured_at: datetime | None
    latest_captured_at: datetime | None


@dataclass(frozen=True)
class RefinementTotalsAggregate:
    items_by_kind: dict[str, int]
    last_refined_at: datetime | None


@dataclass(frozen=True)
class SourceRecordAggregate:
    source: str
    records_total: int
    records_with_refinement_total: int
    pending_records_total: int
    oldest_pending_captured_at: datetime | None
    latest_captured_at: datetime | None
    weeks: tuple[WeekRecordCount, ...]


@dataclass(frozen=True)
class SourceRefinementAggregate:
    source: str
    items_by_kind: dict[str, int]
    last_refined_at: datetime | None


@dataclass(frozen=True)
class CityEventAggregate:
    city_id: str | None
    items: int
    sources: frozenset[str]


@dataclass(frozen=True)
class SourceStatusSnapshot:
    """Raw aggregate rows returned by the storage boundary."""

    records: RecordTotalsAggregate
    refinements: RefinementTotalsAggregate
    sources: tuple[SourceRecordAggregate, ...]
    source_refinements: tuple[SourceRefinementAggregate, ...]
    city_events: tuple[CityEventAggregate, ...]


class RefinementItemCounts(BaseModel):
    """Current refinement output items, with every content kind explicit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: int = Field(default=0, ge=0)
    advertisement: int = Field(default=0, ge=0)
    announcement: int = Field(default=0, ge=0)
    non_event: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)

    @property
    def total(self) -> int:
        return self.event + self.advertisement + self.announcement + self.non_event + self.unknown


class RecordMetrics(BaseModel):
    """Raw record counts, intentionally separate from refinement output items."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    records_total: int = Field(ge=0)
    records_with_refinement_total: int = Field(ge=0)
    pending_records_total: int = Field(ge=0)
    oldest_pending_captured_at: datetime | None = None
    latest_captured_at: datetime | None = None


class RefinementMetrics(BaseModel):
    """Current refinement output item counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    refinement_items_total: int = Field(ge=0)
    refinement_items_by_kind: RefinementItemCounts
    event_items_total: int = Field(ge=0)
    last_refined_at: datetime | None = None


class IngestionWeek(BaseModel):
    """One Monday-start half-open ingestion week.

    ``week_start`` and ``week_end`` are local reporting-zone dates. ``week_end``
    is exclusive. ``starts_at``/``ends_at`` are the explicit UTC instants used
    for aggregation; for the current partial week ``ends_at`` is capped at the
    report ``as_of`` instant and ``is_partial`` is true.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    week_start: date
    week_end: date
    starts_at: datetime
    ends_at: datetime
    is_partial: bool
    records: int = Field(ge=0)
    with_refinement: int = Field(ge=0)
    pending: int = Field(ge=0)


class SourceStats(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    ingestion: RecordMetrics
    refinement: RefinementMetrics
    weeks: tuple[IngestionWeek, ...]


class SourceStatsTotals(BaseModel):
    """All-time totals over every observed source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ingestion: RecordMetrics
    refinement: RefinementMetrics


class CityStats(BaseModel):
    """Registry metadata plus current event refinement output for one city."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    city_id: str
    country_code: str
    slug: str
    name: str
    timezone: str
    event_items_total: int = Field(ge=0)
    sources_with_event_items: int = Field(ge=0)


class SourceStatsReport(BaseModel):
    """Typed source ingestion, refinement coverage, and city output report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: datetime
    reporting_timezone: str
    ingestion_time_basis: Literal["captured_at"] = "captured_at"
    weeks: tuple[IngestionWeek, ...]
    totals: SourceStatsTotals
    sources: tuple[SourceStats, ...]
    cities: tuple[CityStats, ...]
    supported_cities_total: int = Field(ge=0)
    unassigned_city_event_items_total: int = Field(ge=0)
    unsupported_city_event_items_total: int = Field(ge=0)


def build_source_stats_report(
    store: DatabaseStore,
    *,
    weeks: int = 8,
    as_of: datetime | None = None,
    reporting_timezone: str = DEFAULT_SOURCE_TIMEZONE,
) -> SourceStatsReport:
    """Build the stored source ingestion/refinement statistics report.

    ``as_of`` is an injectable timezone-aware instant; when omitted the current
    UTC instant is used. Naive datetimes are rejected so the report never falls
    back to the machine timezone. Week boundaries are computed explicitly in
    ``reporting_timezone`` (``Europe/Vilnius`` by default).
    """
    _validate_weeks(weeks)
    timezone_info = ZoneInfo(reporting_timezone)
    as_of_utc = _resolve_as_of(as_of)
    week_windows = _build_week_windows(as_of_utc, timezone_info, weeks)
    snapshot = store.load_source_status_snapshot(
        week_bounds=[(window.starts_at, window.ends_at) for window in week_windows],
    )

    source_aggregates = {aggregate.source: aggregate for aggregate in snapshot.sources}
    source_refinements = {aggregate.source: aggregate for aggregate in snapshot.source_refinements}
    sources = tuple(
        _source_stats(
            source_aggregates[source],
            source_refinements.get(source),
            week_windows,
        )
        for source in sorted(source_aggregates)
    )

    cities, unassigned, unsupported = _city_stats(snapshot.city_events)

    return SourceStatsReport(
        as_of=as_of_utc,
        reporting_timezone=reporting_timezone,
        weeks=tuple(
            _ingestion_week(window, _week_record_count(snapshot, window.index))
            for window in week_windows
        ),
        totals=SourceStatsTotals(
            ingestion=_record_metrics(snapshot.records),
            refinement=_refinement_metrics(snapshot.refinements),
        ),
        sources=sources,
        cities=cities,
        supported_cities_total=len(CITY_REGISTRY),
        unassigned_city_event_items_total=unassigned,
        unsupported_city_event_items_total=unsupported,
    )


@dataclass(frozen=True)
class _WeekWindow:
    index: int
    week_start: date
    week_end: date
    starts_at: datetime
    ends_at: datetime
    is_partial: bool


def _validate_weeks(weeks: int) -> None:
    if isinstance(weeks, bool) or not isinstance(weeks, int):
        raise ValueError("weeks must be an integer between 1 and 52")
    if not 1 <= weeks <= 52:
        raise ValueError("weeks must be between 1 and 52")


def _resolve_as_of(as_of: datetime | None) -> datetime:
    if as_of is None:
        return datetime.now(timezone.utc)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    return as_of.astimezone(timezone.utc)


def _build_week_windows(
    as_of: datetime,
    timezone_info: ZoneInfo,
    weeks: int,
) -> tuple[_WeekWindow, ...]:
    local_date = as_of.astimezone(timezone_info).date()
    current_week_start = local_date - timedelta(days=local_date.weekday())
    windows: list[_WeekWindow] = []
    for index in range(weeks):
        week_start = current_week_start - timedelta(weeks=weeks - 1 - index)
        week_end = week_start + timedelta(weeks=1)
        starts_at = datetime.combine(week_start, time.min, tzinfo=timezone_info).astimezone(
            timezone.utc
        )
        full_week_end = datetime.combine(
            week_end,
            time.min,
            tzinfo=timezone_info,
        ).astimezone(timezone.utc)
        ends_at = min(full_week_end, as_of)
        windows.append(
            _WeekWindow(
                index=index,
                week_start=week_start,
                week_end=week_end,
                starts_at=starts_at,
                ends_at=ends_at,
                is_partial=ends_at < full_week_end,
            )
        )
    return tuple(windows)


def _week_record_count(snapshot: SourceStatusSnapshot, index: int) -> WeekRecordCount:
    totals = WeekRecordCount(index=index, records=0, pending=0)
    for source in snapshot.sources:
        for week in source.weeks:
            if week.index == index:
                totals = WeekRecordCount(
                    index=index,
                    records=totals.records + week.records,
                    pending=totals.pending + week.pending,
                )
    return totals


def _source_stats(
    aggregate: SourceRecordAggregate,
    refinement: SourceRefinementAggregate | None,
    week_windows: tuple[_WeekWindow, ...],
) -> SourceStats:
    week_counts = {week.index: week for week in aggregate.weeks}
    return SourceStats(
        source=aggregate.source,
        ingestion=_record_metrics(aggregate),
        refinement=_refinement_metrics(refinement),
        weeks=tuple(
            _ingestion_week(
                window,
                week_counts.get(
                    window.index, WeekRecordCount(index=window.index, records=0, pending=0)
                ),
            )
            for window in week_windows
        ),
    )


def _record_metrics(aggregate: RecordTotalsAggregate | SourceRecordAggregate) -> RecordMetrics:
    return RecordMetrics(
        records_total=aggregate.records_total,
        records_with_refinement_total=aggregate.records_with_refinement_total,
        pending_records_total=aggregate.pending_records_total,
        oldest_pending_captured_at=aggregate.oldest_pending_captured_at,
        latest_captured_at=aggregate.latest_captured_at,
    )


def _refinement_metrics(
    aggregate: RefinementTotalsAggregate | SourceRefinementAggregate | None,
) -> RefinementMetrics:
    items_by_kind = _kind_counts(aggregate.items_by_kind if aggregate is not None else {})
    counts = RefinementItemCounts(**items_by_kind)
    return RefinementMetrics(
        refinement_items_total=counts.total,
        refinement_items_by_kind=counts,
        event_items_total=counts.event,
        last_refined_at=aggregate.last_refined_at if aggregate is not None else None,
    )


def _kind_counts(items_by_kind: dict[str, int]) -> dict[str, int]:
    return {kind: int(items_by_kind.get(kind, 0)) for kind in REFINEMENT_CONTENT_KINDS}


def _ingestion_week(window: _WeekWindow, counts: WeekRecordCount) -> IngestionWeek:
    return IngestionWeek(
        week_start=window.week_start,
        week_end=window.week_end,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        is_partial=window.is_partial,
        records=counts.records,
        with_refinement=counts.with_refinement,
        pending=counts.pending,
    )


def _city_stats(
    aggregates: tuple[CityEventAggregate, ...],
) -> tuple[tuple[CityStats, ...], int, int]:
    event_items: dict[str, int] = {city.id: 0 for city in list_cities()}
    event_sources: dict[str, set[str]] = {city.id: set() for city in list_cities()}
    unassigned = 0
    unsupported = 0
    for aggregate in aggregates:
        if aggregate.city_id is None or not aggregate.city_id.strip():
            unassigned += aggregate.items
            continue
        city_id = normalize_city_id(aggregate.city_id)
        if city_id is None:
            unsupported += aggregate.items
            continue
        event_items[city_id] += aggregate.items
        event_sources[city_id].update(aggregate.sources)
    cities = tuple(
        CityStats(
            city_id=city.id,
            country_code=city.country_code,
            slug=city.slug,
            name=city.name,
            timezone=city.timezone,
            event_items_total=event_items[city.id],
            sources_with_event_items=len(event_sources[city.id]),
        )
        for city in list_cities()
    )
    return cities, unassigned, unsupported
