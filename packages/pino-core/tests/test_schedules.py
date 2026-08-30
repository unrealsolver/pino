from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pino_core.models import Refinement
from pino_core.schedules import (
    compile_query_weekly_pattern,
    compile_weekly_pattern,
    expand_schedule,
    normalize_schedule,
)


def test_normalize_explicit_occurrences() -> None:
    schedule = normalize_schedule(
        {
            "version": 1,
            "timezone": "Europe/Vilnius",
            "kind": "occurrences",
            "occurrences": [
                {"start": "2026-06-01T18:30", "end": "2026-06-01T20:10"}
            ],
        }
    )

    assert schedule == {
        "version": 1,
        "timezone": "Europe/Vilnius",
        "kind": "occurrences",
        "occurrences": [
            {"start": "2026-06-01T18:30", "end": "2026-06-01T20:10"}
        ],
    }


def test_normalize_legacy_schedule_uses_existing_envelope() -> None:
    schedule = normalize_schedule(
        {
            "timezone": "Europe/Vilnius",
            "kind": "opening_hours",
            "rules": [{"days": ["TU", "thursday"], "start": "18:00", "end": "19:30"}],
            "exceptions": [],
        },
        relevant_from=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        relevant_to=datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc),
    )

    assert schedule == {
        "version": 1,
        "timezone": "Europe/Vilnius",
        "kind": "recurrence",
        "frequency": "weekly",
        "from": "2026-06-01",
        "until": "2026-07-01",
        "rules": [
            {
                "weekdays": ["tuesday", "thursday"],
                "start": "18:00",
                "end": "19:30",
            }
        ],
    }


def test_refinement_derives_explicit_schedule_envelope() -> None:
    refinement = Refinement(
        record_id="record",
        content_kind="event",
        relevant_from=datetime(2000, 1, 1, tzinfo=timezone.utc),
        relevant_to=datetime(2000, 1, 2, tzinfo=timezone.utc),
        schedule={
            "version": 1,
            "timezone": "Europe/Vilnius",
            "kind": "occurrences",
            "occurrences": [
                {"start": "2026-06-01T18:30", "end": "2026-06-01T20:10"},
                {"start": "2026-06-08T18:30", "end": None},
            ],
        },
        refiner="test",
    )

    assert refinement.relevant_from == datetime(2026, 6, 1, 15, 30, tzinfo=timezone.utc)
    assert refinement.relevant_to == datetime(2026, 6, 8, 15, 30, tzinfo=timezone.utc)


def test_expand_weekly_recurrence_and_overnight_end() -> None:
    schedule = normalize_schedule(
        {
            "version": 1,
            "timezone": "Europe/Vilnius",
            "kind": "recurrence",
            "frequency": "weekly",
            "from": "2026-06-01",
            "until": "2026-06-30",
            "rules": [
                {"weekdays": ["tuesday"], "start": "23:00", "end": "01:00"}
            ],
        }
    )
    assert schedule is not None

    occurrences = expand_schedule(
        schedule,
        window_start=datetime(2026, 6, 9, 23, 30, tzinfo=ZoneInfo("Europe/Vilnius")),
        window_end=datetime(2026, 6, 10, 0, 30, tzinfo=ZoneInfo("Europe/Vilnius")),
        key_prefix="event",
    )

    assert len(occurrences) == 1
    assert occurrences[0].starts_at == datetime(
        2026, 6, 9, 23, 0, tzinfo=ZoneInfo("Europe/Vilnius")
    )
    assert occurrences[0].ends_at == datetime(
        2026, 6, 10, 1, 0, tzinfo=ZoneInfo("Europe/Vilnius")
    )

    refinement = Refinement(
        record_id="record",
        content_kind="event",
        schedule=schedule,
        refiner="test",
    )
    assert refinement.relevant_to == datetime(
        2026, 7, 1, 20, 59, 59, 999999, tzinfo=timezone.utc
    )


def test_expand_schedule_returns_no_nonmatching_recurrence() -> None:
    schedule = normalize_schedule(
        {
            "version": 1,
            "timezone": "Europe/Vilnius",
            "kind": "recurrence",
            "frequency": "weekly",
            "from": "2026-06-01",
            "until": "2026-06-30",
            "rules": [{"weekdays": ["tuesday"], "start": "19:00", "end": None}],
        }
    )
    assert schedule is not None

    occurrences = expand_schedule(
        schedule,
        window_start=datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc),
        key_prefix="event",
    )

    assert occurrences == []


def test_normalize_schedule_rejects_offset_datetime() -> None:
    assert (
        normalize_schedule(
            {
                "version": 1,
                "timezone": "Europe/Vilnius",
                "kind": "occurrences",
                "occurrences": [{"start": "2026-06-01T18:30+03:00", "end": None}],
            }
        )
        is None
    )
    assert (
        normalize_schedule(
            {
                "timezone": "Europe/Vilnius",
                "kind": "recurrence",
                "rules": None,
            }
        )
        is None
    )


def test_compile_weekly_pattern_collapses_rules_and_wraps_week() -> None:
    schedule = normalize_schedule(
        {
            "version": 1,
            "timezone": "Europe/Vilnius",
            "kind": "recurrence",
            "frequency": "weekly",
            "from": "2026-06-01",
            "until": None,
            "rules": [
                {"weekdays": ["monday"], "start": "09:00", "end": "12:00"},
                {"weekdays": ["monday"], "start": "11:00", "end": "14:00"},
                {"weekdays": ["sunday"], "start": "23:00", "end": "01:00"},
            ],
        }
    )
    assert schedule is not None

    pattern = compile_weekly_pattern(schedule)

    assert pattern.timezone == "Europe/Vilnius"
    assert pattern.ranges == ((0, 61), (540, 841), (10020, 10080))
    assert pattern.as_postgresql_multirange() == "{[0,61),[540,841),[10020,10080)}"


def test_compile_explicit_occurrences_uses_one_minute_for_start_only() -> None:
    schedule = normalize_schedule(
        {
            "version": 1,
            "timezone": "Europe/Vilnius",
            "kind": "occurrences",
            "occurrences": [
                {"start": "2026-06-01T18:30", "end": None},
                {"start": "2026-06-02T23:30", "end": "2026-06-03T00:30"},
            ],
        }
    )
    assert schedule is not None

    pattern = compile_weekly_pattern(schedule)

    assert pattern.ranges == ((1110, 1111), (2850, 2911))


def test_compile_query_weekly_pattern_wraps_and_saturates() -> None:
    timezone_info = ZoneInfo("Europe/Vilnius")

    wrapped = compile_query_weekly_pattern(
        datetime(2026, 6, 7, 23, 30, tzinfo=timezone_info),
        datetime(2026, 6, 8, 0, 30, tzinfo=timezone_info),
        "Europe/Vilnius",
    )
    saturated = compile_query_weekly_pattern(
        datetime(2026, 6, 1, 12, 0, tzinfo=timezone_info),
        datetime(2026, 6, 8, 12, 0, tzinfo=timezone_info),
        "Europe/Vilnius",
    )

    assert wrapped.ranges == ((0, 31), (10050, 10080))
    assert saturated.ranges == ((0, 10080),)


def test_compile_query_weekly_pattern_is_conservative_across_dst_fallback() -> None:
    pattern = compile_query_weekly_pattern(
        datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 25, 1, 15, tzinfo=timezone.utc),
        "Europe/Vilnius",
    )

    assert pattern.ranges == ((0, 10080),)
