from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


DEFAULT_SOURCE_TIMEZONE = "Europe/Vilnius"


def parse_source_datetime(value: str | None, timezone_name: str = DEFAULT_SOURCE_TIMEZONE) -> datetime | None:
    """Parse common source datetime strings as timezone-aware local datetimes."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return _with_timezone(parsed, timezone_name)

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _with_timezone(parsed, timezone_name)


def parse_source_date_range(
    value: str | None,
    timezone_name: str = DEFAULT_SOURCE_TIMEZONE,
) -> tuple[datetime | None, datetime | None]:
    """Parse simple listing display dates into a relevance window."""
    if value is None:
        return None, None
    text = value.strip()
    if not text:
        return None, None

    if " - " in text:
        start_text, end_text = (part.strip() for part in text.split(" - ", 1))
        start = parse_source_datetime(start_text, timezone_name)
        end = parse_source_datetime(end_text, timezone_name)
        if end is not None and _looks_like_date_only(end_text):
            end = datetime.combine(end.date(), time.max, tzinfo=end.tzinfo)
        return start, end

    parsed = parse_source_datetime(text, timezone_name)
    return parsed, parsed


def to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc)


def utc_iso(value: datetime | None) -> str | None:
    utc_value = to_utc(value)
    return utc_value.isoformat() if utc_value is not None else None


def _with_timezone(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=ZoneInfo(timezone_name))


def _looks_like_date_only(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True
