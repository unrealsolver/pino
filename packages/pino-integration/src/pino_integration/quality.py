from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pino_core.config import SourceConfig
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import Record, Refinement
from pino_core.quality import QCFlag, QCReport, RefinementQC, no_refinement_qc
from pino_core.schedules import expand_schedule


_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
_DATE_TAG = re.compile(
    rf"(?<!\w)#(?P<day>\d{{1,2}})(?P<month>{'|'.join(_MONTHS)})(?!\w)",
    re.IGNORECASE,
)


def check_afisha_vilnius(record: Record, refinement: Refinement) -> QCReport:
    tagged_dates = _tagged_dates(record)
    if not tagged_dates:
        return QCReport()
    if refinement.schedule is None:
        return QCReport(
            schedule=QCFlag(
                "error",
                f"source date tag(s) have no schedule: {_render_dates(tagged_dates)}",
            )
        )

    if refinement.schedule["kind"] == "recurrence":
        missing = {
            tagged_date
            for tagged_date in tagged_dates
            if not _recurrence_covers(refinement.schedule, tagged_date)
        }
        return _missing_dates_report(missing)

    scheduled_dates = {
        datetime.fromisoformat(item["start"]).date() for item in refinement.schedule["occurrences"]
    }
    missing = tagged_dates - scheduled_dates
    if missing:
        return _missing_dates_report(missing)
    extras = scheduled_dates - tagged_dates
    if extras:
        return QCReport(
            schedule=QCFlag(
                "warning",
                f"schedule contains untagged occurrence date(s): {_render_dates(extras)}",
            )
        )
    return QCReport()


def build_refinement_qc(configs: list[SourceConfig]) -> RefinementQC:
    profiles: dict[str, RefinementQC] = {
        "afisha_vilnius": check_afisha_vilnius,
    }
    checks: dict[str, RefinementQC] = {}
    for config in configs:
        profile = config.settings.get("qc")
        if profile is None:
            continue
        try:
            checks[config.name] = profiles[str(profile)]
        except KeyError as exc:
            raise ValueError(f"unknown refinement QC profile: {profile!r}") from exc
    if not checks:
        return no_refinement_qc

    def check(record: Record, refinement: Refinement) -> QCReport:
        source_check = checks.get(record.source)
        return source_check(record, refinement) if source_check is not None else QCReport()

    return check


def _tagged_dates(record: Record) -> frozenset[date]:
    year = _publication_year(record.published_at)
    if year is None:
        return frozenset()
    dates: set[date] = set()
    for match in _DATE_TAG.finditer(record.text):
        try:
            dates.add(date(year, _MONTHS[match.group("month").casefold()], int(match.group("day"))))
        except ValueError:
            continue
    return frozenset(dates)


def _publication_year(value: Any) -> int | None:
    try:
        published = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        )
    except (TypeError, ValueError):
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published.astimezone(ZoneInfo(DEFAULT_SOURCE_TIMEZONE)).year


def _recurrence_covers(schedule: dict[str, Any], tagged_date: date) -> bool:
    timezone_info = ZoneInfo(schedule["timezone"])
    window_start = datetime.combine(tagged_date, time.min, tzinfo=timezone_info)
    window_end = datetime.combine(
        tagged_date + timedelta(days=1),
        time.min,
        tzinfo=timezone_info,
    ) - timedelta(microseconds=1)
    occurrences = expand_schedule(
        schedule,
        window_start=window_start,
        window_end=window_end,
        key_prefix="qc",
    )
    return any(
        occurrence.starts_at.astimezone(timezone_info).date() == tagged_date
        for occurrence in occurrences
    )


def _missing_dates_report(missing: set[date]) -> QCReport:
    if not missing:
        return QCReport()
    return QCReport(
        schedule=QCFlag(
            "error",
            f"tagged date(s) not covered by schedule: {_render_dates(missing)}",
        )
    )


def _render_dates(dates: set[date] | frozenset[date]) -> str:
    return ", ".join(item.isoformat() for item in sorted(dates))
