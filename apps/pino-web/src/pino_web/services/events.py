from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pino_core.config import PinoConfig
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import Refinement
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
) -> list[EventItem]:
    record = result.record
    refinement = result.refinement
    if refinement.relevant_from is None:
        raise ValueError("event query returned an undated refinement")
    occurrences = _expand_scheduled_occurrences(refinement, window_start, window_end)
    if not occurrences:
        occurrences = _expand_default_occurrences(
            refinement,
            window_start,
            window_end,
            display_timezone=local_timezone,
        )
    return [
        EventItem(
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


def _expand_scheduled_occurrences(
    refinement: Refinement,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[str, datetime, datetime | None]]:
    schedule = refinement.schedule
    if not isinstance(schedule, dict):
        return []
    kind = schedule.get("kind")
    if kind not in {"opening_hours", "recurrence"}:
        return []
    timezone_name = schedule.get("timezone")
    if not isinstance(timezone_name, str):
        return []
    try:
        schedule_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return []

    rules = schedule.get("rules")
    if not isinstance(rules, list):
        return []

    envelope_start = refinement.relevant_from.astimezone(schedule_timezone)
    envelope_end = (
        refinement.relevant_to.astimezone(schedule_timezone)
        if refinement.relevant_to is not None
        else None
    )
    window_start = window_start.astimezone(schedule_timezone)
    window_end = window_end.astimezone(schedule_timezone)
    bounded_start = max(envelope_start, window_start)
    bounded_end = min(envelope_end, window_end) if envelope_end is not None else window_end
    if bounded_end < bounded_start:
        return []

    occurrences: list[tuple[str, datetime, datetime | None]] = []
    first_day = _start_of_day(bounded_start)
    last_day = _start_of_day(bounded_end)
    for day in _iter_days(first_day.date(), last_day.date(), schedule_timezone):
        day_code = _weekday_code(day)
        for rule_index, rule in enumerate(rules):
            occurrence = _occurrence_from_rule(
                refinement_id=refinement.id,
                rule=rule,
                rule_index=rule_index,
                day=day,
                day_code=day_code,
                kind=kind,
                bounded_start=bounded_start,
                bounded_end=bounded_end,
            )
            if occurrence is not None:
                occurrences.append(occurrence)
    return occurrences


def _occurrence_from_rule(
    *,
    refinement_id: str,
    rule: object,
    rule_index: int,
    day: datetime,
    day_code: str,
    kind: str,
    bounded_start: datetime,
    bounded_end: datetime,
) -> tuple[str, datetime, datetime | None] | None:
    if not isinstance(rule, dict) or "frequency" in rule:
        return None
    days = rule.get("days")
    if not isinstance(days, list) or day_code not in days:
        return None
    start_time = _parse_rule_time(rule.get("start"))
    if start_time is None:
        return None
    scheduled_start = datetime.combine(day.date(), start_time, tzinfo=day.tzinfo)
    end_time = _parse_rule_time(rule.get("end"))
    scheduled_end: datetime | None = None
    if end_time is not None:
        scheduled_end = datetime.combine(day.date(), end_time, tzinfo=day.tzinfo)
        if scheduled_end <= scheduled_start:
            scheduled_end += timedelta(days=1)

    if kind == "recurrence" and scheduled_end is None:
        if not (bounded_start <= scheduled_start <= bounded_end):
            return None
        occurrence_key = scheduled_start.strftime("%Y-%m-%dT%H%M")
        return f"{refinement_id}:{occurrence_key}:{rule_index}", scheduled_start, None

    occurrence_end = scheduled_end
    if occurrence_end is None:
        occurrence_end = scheduled_start
    starts_at = max(scheduled_start, bounded_start)
    ends_at = min(occurrence_end, bounded_end)
    if ends_at < starts_at:
        return None
    occurrence_key = scheduled_start.strftime("%Y-%m-%dT%H%M")
    return f"{refinement_id}:{occurrence_key}:{rule_index}", starts_at, ends_at


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


def _parse_rule_time(value: object) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return None
    return parsed.replace(second=0, microsecond=0)


def _start_of_day(value: datetime) -> datetime:
    return datetime.combine(value.date(), time.min, tzinfo=value.tzinfo)


def _iter_days(start: date, end: date, timezone_info: tzinfo) -> list[datetime]:
    days: list[datetime] = []
    current = start
    while current <= end:
        days.append(datetime.combine(current, time.min, tzinfo=timezone_info))
        current += timedelta(days=1)
    return days


def _weekday_code(value: datetime) -> str:
    return ("MO", "TU", "WE", "TH", "FR", "SA", "SU")[value.weekday()]
