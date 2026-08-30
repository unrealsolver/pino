from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_MINUTES_PER_DAY = 24 * 60
_MINUTES_PER_WEEK = 7 * _MINUTES_PER_DAY
_LEGACY_WEEKDAYS = {
    "MO": "monday",
    "TU": "tuesday",
    "WE": "wednesday",
    "TH": "thursday",
    "FR": "friday",
    "SA": "saturday",
    "SU": "sunday",
    "MONDAY": "monday",
    "TUESDAY": "tuesday",
    "WEDNESDAY": "wednesday",
    "THURSDAY": "thursday",
    "FRIDAY": "friday",
    "SATURDAY": "saturday",
    "SUNDAY": "sunday",
}


class _ScheduleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: Literal[1] = 1
    timezone: str
    source_text: str | None = None


class ScheduleOccurrence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime | None = None

    @field_validator("start", "end")
    @classmethod
    def _require_local_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError("schedule occurrence datetimes must be local wall times")
        return value


class OccurrencesSchedule(_ScheduleModel):
    kind: Literal["occurrences"]
    occurrences: list[ScheduleOccurrence] = Field(min_length=1)


class RecurrenceRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekdays: list[str] = Field(min_length=1)
    start: time
    end: time | None = None

    @field_validator("weekdays")
    @classmethod
    def _normalize_weekdays(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for weekday in value:
            name = str(weekday).strip().casefold()
            if name not in _WEEKDAYS:
                raise ValueError(f"invalid weekday: {weekday}")
            if name not in normalized:
                normalized.append(name)
        return normalized

    @field_validator("start", "end")
    @classmethod
    def _require_minute_time(cls, value: time | None) -> time | None:
        if value is not None and (value.tzinfo is not None or value.second or value.microsecond):
            raise ValueError("schedule rule times must use local HH:MM precision")
        return value


class RecurrenceSchedule(_ScheduleModel):
    kind: Literal["recurrence"]
    frequency: Literal["weekly"]
    from_date: date | None = Field(alias="from")
    until: date | None = None
    rules: list[RecurrenceRule] = Field(min_length=1)


@dataclass(frozen=True)
class ScheduleEnvelope:
    start: datetime | None
    end: datetime | None


@dataclass(frozen=True)
class ProjectedOccurrence:
    key: str
    starts_at: datetime
    ends_at: datetime | None


@dataclass(frozen=True)
class WeeklyPattern:
    timezone: str
    ranges: tuple[tuple[int, int], ...]

    def as_postgresql_multirange(self) -> str:
        return "{" + ",".join(f"[{start},{end})" for start, end in self.ranges) + "}"


def normalize_schedule(
    value: Any,
    *,
    relevant_from: datetime | None = None,
    relevant_to: datetime | None = None,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    candidate = value
    if "version" not in candidate:
        candidate = _upgrade_legacy_schedule(
            candidate,
            relevant_from=relevant_from,
            relevant_to=relevant_to,
        )
        if candidate is None:
            return None
    try:
        timezone_name = str(candidate.get("timezone", "")).strip()
        ZoneInfo(timezone_name)
        candidate = {**candidate, "timezone": timezone_name}
        kind = candidate.get("kind")
        if kind == "occurrences":
            model = OccurrencesSchedule.model_validate(candidate)
            return _dump_occurrences(model)
        if kind == "recurrence":
            model = RecurrenceSchedule.model_validate(candidate)
            if (
                model.from_date is not None
                and model.until is not None
                and model.until < model.from_date
            ):
                return None
            return _dump_recurrence(model)
    except (ValidationError, ValueError, ZoneInfoNotFoundError):
        return None
    return None


def derive_schedule_envelope(schedule: dict[str, Any]) -> ScheduleEnvelope:
    timezone_info = ZoneInfo(schedule["timezone"])
    if schedule["kind"] == "occurrences":
        intervals = [_occurrence_interval(item, timezone_info) for item in schedule["occurrences"]]
        return ScheduleEnvelope(
            start=min(item[0] for item in intervals).astimezone(timezone.utc),
            end=max((item[1] or item[0]) for item in intervals).astimezone(timezone.utc),
        )
    from_date = _parse_date(schedule.get("from"))
    until = _parse_date(schedule.get("until"))
    start = (
        datetime.combine(from_date, time.min, tzinfo=timezone_info).astimezone(timezone.utc)
        if from_date is not None
        else None
    )
    end = (
        datetime.combine(
            until + timedelta(days=1) if _has_overnight_rule(schedule) else until,
            time.max,
            tzinfo=timezone_info,
        ).astimezone(timezone.utc)
        if until is not None
        else None
    )
    return ScheduleEnvelope(start=start, end=end)


def expand_schedule(
    schedule: dict[str, Any],
    *,
    window_start: datetime,
    window_end: datetime,
    key_prefix: str,
) -> list[ProjectedOccurrence]:
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("schedule expansion window must be timezone-aware")
    if window_end < window_start:
        return []
    timezone_info = ZoneInfo(schedule["timezone"])
    if schedule["kind"] == "occurrences":
        return _expand_explicit_occurrences(
            schedule,
            timezone_info=timezone_info,
            window_start=window_start,
            window_end=window_end,
            key_prefix=key_prefix,
        )
    return _expand_weekly_recurrence(
        schedule,
        timezone_info=timezone_info,
        window_start=window_start,
        window_end=window_end,
        key_prefix=key_prefix,
    )


def compile_weekly_pattern(schedule: dict[str, Any]) -> WeeklyPattern:
    ranges: list[tuple[int, int]] = []
    if schedule["kind"] == "occurrences":
        timezone_info = ZoneInfo(schedule["timezone"])
        for item in schedule["occurrences"]:
            starts_at, ends_at = _occurrence_interval(item, timezone_info)
            start = starts_at.weekday() * _MINUTES_PER_DAY + _minute_of_day(
                starts_at.timetz().replace(tzinfo=None)
            )
            duration = (
                # Exact window matching treats the end instant as inclusive.
                max(1, round((ends_at - starts_at).total_seconds() / 60) + 1)
                if ends_at is not None
                else 1
            )
            _append_cyclic_range(ranges, start, start + duration)
    else:
        for rule in schedule["rules"]:
            start_time = time.fromisoformat(rule["start"])
            end_time = time.fromisoformat(rule["end"]) if rule["end"] is not None else None
            for weekday in rule["weekdays"]:
                start = _WEEKDAYS.index(weekday) * _MINUTES_PER_DAY + _minute_of_day(start_time)
                duration = 1
                if end_time is not None:
                    duration = _minute_of_day(end_time) - _minute_of_day(start_time)
                    if duration <= 0:
                        duration += _MINUTES_PER_DAY
                    # Keep the lossy index conservative at the inclusive end.
                    duration += 1
                _append_cyclic_range(ranges, start, start + duration)
    return WeeklyPattern(
        timezone=schedule["timezone"],
        ranges=tuple(_collapse_ranges(ranges)),
    )


def compile_query_weekly_pattern(
    window_start: datetime,
    window_end: datetime,
    timezone_name: str,
) -> WeeklyPattern:
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("schedule query window must be timezone-aware")
    utc_start = window_start.astimezone(timezone.utc).replace(second=0, microsecond=0)
    utc_end = window_end.astimezone(timezone.utc).replace(second=0, microsecond=0)
    if utc_end < utc_start:
        return WeeklyPattern(timezone=timezone_name, ranges=())
    timezone_info = ZoneInfo(timezone_name)
    local_start = window_start.astimezone(timezone_info).replace(second=0, microsecond=0)
    local_end = window_end.astimezone(timezone_info).replace(second=0, microsecond=0)
    wall_start = local_start.replace(tzinfo=None)
    wall_end = local_end.replace(tzinfo=None)
    wall_minutes = int((wall_end - wall_start).total_seconds() / 60)
    if wall_minutes < 0:
        return WeeklyPattern(timezone=timezone_name, ranges=((0, _MINUTES_PER_WEEK),))
    elapsed_minutes = int((utc_end - utc_start).total_seconds() / 60)
    duration = max(wall_minutes, elapsed_minutes) + 1
    start = local_start.weekday() * _MINUTES_PER_DAY + _minute_of_day(local_start.time())
    ranges: list[tuple[int, int]] = []
    _append_cyclic_range(ranges, start, start + duration)
    return WeeklyPattern(timezone=timezone_name, ranges=tuple(_collapse_ranges(ranges)))


def _upgrade_legacy_schedule(
    value: dict[str, Any],
    *,
    relevant_from: datetime | None,
    relevant_to: datetime | None,
) -> dict[str, Any] | None:
    if value.get("kind") not in {"opening_hours", "recurrence"}:
        return None
    timezone_name = value.get("timezone")
    if not isinstance(timezone_name, str):
        return None
    try:
        timezone_info = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None
    raw_rules = value.get("rules")
    if not isinstance(raw_rules, list):
        return None
    rules: list[dict[str, Any]] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict) or "frequency" in raw_rule:
            continue
        raw_days = raw_rule.get("days")
        if not isinstance(raw_days, list):
            continue
        weekdays = [
            _LEGACY_WEEKDAYS.get(str(day).strip().upper()) for day in raw_days
        ]
        weekdays = [day for day in weekdays if day is not None]
        if not weekdays:
            continue
        rules.append(
            {
                "weekdays": weekdays,
                "start": raw_rule.get("start"),
                "end": raw_rule.get("end"),
            }
        )
    if not rules:
        return None
    candidate: dict[str, Any] = {
        "version": 1,
        "timezone": timezone_name,
        "kind": "recurrence",
        "frequency": "weekly",
        "from": _local_date(relevant_from, timezone_info),
        "until": _local_date(relevant_to, timezone_info),
        "rules": rules,
    }
    source_text = value.get("source_text")
    if isinstance(source_text, str) and source_text.strip():
        candidate["source_text"] = source_text.strip()
    return candidate


def _dump_occurrences(model: OccurrencesSchedule) -> dict[str, Any]:
    schedule: dict[str, Any] = {
        "version": 1,
        "timezone": model.timezone,
        "kind": "occurrences",
        "occurrences": [
            {
                "start": _format_local_datetime(item.start),
                "end": _format_local_datetime(item.end) if item.end is not None else None,
            }
            for item in model.occurrences
        ],
    }
    if model.source_text:
        schedule["source_text"] = model.source_text.strip()
    return schedule


def _dump_recurrence(model: RecurrenceSchedule) -> dict[str, Any]:
    schedule: dict[str, Any] = {
        "version": 1,
        "timezone": model.timezone,
        "kind": "recurrence",
        "frequency": "weekly",
        "from": model.from_date.isoformat() if model.from_date is not None else None,
        "until": model.until.isoformat() if model.until is not None else None,
        "rules": [
            {
                "weekdays": rule.weekdays,
                "start": _format_time(rule.start),
                "end": _format_time(rule.end) if rule.end is not None else None,
            }
            for rule in model.rules
        ],
    }
    if model.source_text:
        schedule["source_text"] = model.source_text.strip()
    return schedule


def _expand_explicit_occurrences(
    schedule: dict[str, Any],
    *,
    timezone_info: ZoneInfo,
    window_start: datetime,
    window_end: datetime,
    key_prefix: str,
) -> list[ProjectedOccurrence]:
    projected: list[ProjectedOccurrence] = []
    for index, item in enumerate(schedule["occurrences"]):
        starts_at, ends_at = _occurrence_interval(item, timezone_info)
        if not _overlaps(starts_at, ends_at, window_start, window_end):
            continue
        key = f"{key_prefix}:{starts_at:%Y-%m-%dT%H%M}:{index}"
        projected.append(ProjectedOccurrence(key=key, starts_at=starts_at, ends_at=ends_at))
    return projected


def _expand_weekly_recurrence(
    schedule: dict[str, Any],
    *,
    timezone_info: ZoneInfo,
    window_start: datetime,
    window_end: datetime,
    key_prefix: str,
) -> list[ProjectedOccurrence]:
    local_start = window_start.astimezone(timezone_info)
    local_end = window_end.astimezone(timezone_info)
    first_date = local_start.date() - timedelta(days=1)
    last_date = local_end.date()
    from_date = _parse_date(schedule.get("from"))
    until = _parse_date(schedule.get("until"))
    if from_date is not None:
        first_date = max(first_date, from_date)
    if until is not None:
        last_date = min(last_date, until)
    if last_date < first_date:
        return []

    projected: list[ProjectedOccurrence] = []
    current = first_date
    while current <= last_date:
        weekday = _WEEKDAYS[current.weekday()]
        for index, rule in enumerate(schedule["rules"]):
            if weekday not in rule["weekdays"]:
                continue
            starts_at = datetime.combine(current, time.fromisoformat(rule["start"]), timezone_info)
            ends_at = None
            if rule["end"] is not None:
                ends_at = datetime.combine(current, time.fromisoformat(rule["end"]), timezone_info)
                if ends_at <= starts_at:
                    ends_at += timedelta(days=1)
            if not _overlaps(starts_at, ends_at, window_start, window_end):
                continue
            key = f"{key_prefix}:{starts_at:%Y-%m-%dT%H%M}:{index}"
            projected.append(
                ProjectedOccurrence(key=key, starts_at=starts_at, ends_at=ends_at)
            )
        current += timedelta(days=1)
    return projected


def _occurrence_interval(
    item: dict[str, Any],
    timezone_info: ZoneInfo,
) -> tuple[datetime, datetime | None]:
    starts_at = datetime.fromisoformat(item["start"]).replace(tzinfo=timezone_info)
    ends_at = None
    if item.get("end") is not None:
        ends_at = datetime.fromisoformat(item["end"]).replace(tzinfo=timezone_info)
        if ends_at <= starts_at:
            ends_at += timedelta(days=1)
    return starts_at, ends_at


def _overlaps(
    starts_at: datetime,
    ends_at: datetime | None,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    if ends_at is None:
        return window_start <= starts_at <= window_end
    return starts_at <= window_end and ends_at >= window_start


def _has_overnight_rule(schedule: dict[str, Any]) -> bool:
    for rule in schedule["rules"]:
        if rule["end"] is None:
            continue
        if time.fromisoformat(rule["end"]) <= time.fromisoformat(rule["start"]):
            return True
    return False


def _append_cyclic_range(
    ranges: list[tuple[int, int]],
    start: int,
    end: int,
) -> None:
    duration = end - start
    if duration >= _MINUTES_PER_WEEK:
        ranges.append((0, _MINUTES_PER_WEEK))
        return
    start %= _MINUTES_PER_WEEK
    end = start + duration
    if end <= _MINUTES_PER_WEEK:
        ranges.append((start, end))
        return
    ranges.append((start, _MINUTES_PER_WEEK))
    ranges.append((0, end - _MINUTES_PER_WEEK))


def _collapse_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    collapsed: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if not collapsed or start > collapsed[-1][1]:
            collapsed.append((start, end))
            continue
        previous_start, previous_end = collapsed[-1]
        collapsed[-1] = (previous_start, max(previous_end, end))
    return collapsed


def _minute_of_day(value: time) -> int:
    return value.hour * 60 + value.minute


def _local_date(value: datetime | None, timezone_info: ZoneInfo) -> str | None:
    return value.astimezone(timezone_info).date().isoformat() if value is not None else None


def _parse_date(value: Any) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else None


def _format_local_datetime(value: datetime) -> str:
    return value.isoformat(timespec="minutes")


def _format_time(value: time) -> str:
    return value.isoformat(timespec="minutes")
