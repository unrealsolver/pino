from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

from pino_core.config import PinoConfig
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import Refinement
from pino_core.schedules import expand_schedule
from pino_core.storage import EventQueryResult
from pino_web.repositories.events import EventRepository
from pino_web.schemas import EventItem, EventListResponse

MAX_QUERY_DAYS = 370
DEFAULT_EVENT_LIMIT = 300


@dataclass(frozen=True)
class EventFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    categories: list[str] = field(default_factory=list)
    min_score: float = 0.0
    query: str = ""
    limit: int = DEFAULT_EVENT_LIMIT


class EventQueryError(ValueError):
    pass


class EventService:
    def __init__(
        self,
        *,
        config: PinoConfig,
        repository: EventRepository,
        local_timezone: ZoneInfo | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.local_timezone = local_timezone or ZoneInfo(DEFAULT_SOURCE_TIMEZONE)

    def list_events(
        self,
        *,
        filters: EventFilters,
    ) -> EventListResponse:
        window_start, window_end = _resolve_window(
            filters.date_from,
            filters.date_to,
            self.local_timezone,
        )
        if window_end < window_start:
            raise EventQueryError("date_to must be on or after date_from")
        if (window_end - window_start).days > MAX_QUERY_DAYS:
            raise EventQueryError(f"date range cannot exceed {MAX_QUERY_DAYS} days")

        known_categories = _known_categories(self.config)
        selected_categories = _validate_categories(filters.categories, known_categories)
        results = self.repository.query_events(
            window_start=window_start.astimezone(timezone.utc),
            window_end=window_end.astimezone(timezone.utc),
            categories=selected_categories,
            min_score=filters.min_score,
            text_query=filters.query,
            limit=filters.limit,
        )
        events = [
            item
            for result in results
            for item in _to_event_items(
                result,
                self.local_timezone,
                window_start=window_start,
                window_end=window_end,
                media_public_url=self.config.media.public_url,
            )
        ]
        events.sort(key=lambda event: event.starts_at)
        return EventListResponse(
            timezone=DEFAULT_SOURCE_TIMEZONE,
            categories=known_categories,
            events=events[: filters.limit],
        )


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
        raise EventQueryError(f"unknown category: {', '.join(unknown)}")
    return selected


def _to_event_items(
    result: EventQueryResult,
    local_timezone: tzinfo,
    *,
    window_start: datetime,
    window_end: datetime,
    media_public_url: str = "/media",
) -> list[EventItem]:
    record = result.record
    refinement = result.refinement
    if refinement.relevant_from is None:
        raise ValueError("event query returned an undated refinement")
    if refinement.schedule is not None:
        occurrences = [
            (item.key, item.starts_at, item.ends_at)
            for item in expand_schedule(
                refinement.schedule,
                window_start=window_start,
                window_end=window_end,
                key_prefix=refinement.id,
            )
        ]
    else:
        occurrences = _expand_default_occurrences(
            refinement,
            window_start,
            window_end,
            display_timezone=local_timezone,
        )
    return [
        EventItem(
            images=[f"{media_public_url.rstrip('/')}/{image.path}" for image in record.images],
            refinement_id=refinement.id,
            occurrence_id=occurrence_id,
            title=record.title or refinement.summary or "Untitled event",
            source=record.source,
            url=record.url,
            summary=refinement.summary,
            location=refinement.location,
            starts_at=starts_at.astimezone(timezone.utc),
            ends_at=ends_at.astimezone(timezone.utc) if ends_at is not None else None,
            relevant_from=refinement.relevant_from.astimezone(timezone.utc),
            relevant_to=refinement.relevant_to.astimezone(timezone.utc)
            if refinement.relevant_to is not None
            else None,
            category_scores=refinement.category_scores,
            matching_score=result.score,
        )
        for occurrence_id, starts_at, ends_at in occurrences
    ]


def _expand_default_occurrences(
    refinement: Refinement,
    window_start: datetime,
    window_end: datetime,
    *,
    display_timezone: tzinfo,
) -> list[tuple[str, datetime, datetime | None]]:
    relevant_from = refinement.relevant_from
    relevant_to = refinement.relevant_to
    if relevant_to is None:
        if not (window_start <= relevant_from <= window_end):
            return []
        occurrence_key = relevant_from.strftime("%Y-%m-%dT%H%M%S")
        return [(f"{refinement.id}:{occurrence_key}", relevant_from, None)]

    starts_at = max(relevant_from, window_start)
    ends_at = min(relevant_to, window_end)
    if ends_at < starts_at:
        return []
    window_timezone = display_timezone
    starts_at = starts_at.astimezone(window_timezone)
    ends_at = ends_at.astimezone(window_timezone)
    if starts_at.date() == ends_at.date():
        occurrence_key = starts_at.strftime("%Y-%m-%dT%H%M%S")
        return [(f"{refinement.id}:{occurrence_key}", starts_at, ends_at)]

    occurrences: list[tuple[str, datetime, datetime | None]] = []
    first_day = _start_of_day(starts_at)
    last_day = _start_of_day(ends_at)
    for day in _iter_days(first_day.date(), last_day.date(), window_timezone):
        day_start = day
        day_end = day + timedelta(days=1)
        occurrence_start = max(day_start, starts_at)
        occurrence_end = min(day_end, ends_at)
        if occurrence_end >= occurrence_start:
            occurrence_key = day.strftime("%Y-%m-%d")
            occurrences.append(
                (f"{refinement.id}:{occurrence_key}", occurrence_start, occurrence_end)
            )
    return occurrences


def _start_of_day(value: datetime) -> datetime:
    return datetime.combine(value.date(), time.min, tzinfo=value.tzinfo)


def _iter_days(start: date, end: date, timezone_info: tzinfo) -> list[datetime]:
    days: list[datetime] = []
    current = start
    while current <= end:
        days.append(datetime.combine(current, time.min, tzinfo=timezone_info))
        current += timedelta(days=1)
    return days
