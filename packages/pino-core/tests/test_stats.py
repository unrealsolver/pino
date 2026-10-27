from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from pino_core import DatabaseStore, Record, Refinement, SQLiteStore
from pino_core.stats import build_source_stats_report
from pino_core.storage import (
    _city_event_query,
    _record_totals_query,
    _refinement_totals_query,
    _source_record_totals_query,
    _source_refinement_query,
    _source_week_records_query,
)

AS_OF = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
WEEK_STARTS = (
    date(2026, 9, 7),
    date(2026, 9, 14),
    date(2026, 9, 21),
    date(2026, 9, 28),
    date(2026, 10, 5),
    date(2026, 10, 12),
    date(2026, 10, 19),
    date(2026, 10, 26),
)


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    database = SQLiteStore(tmp_path / "pino.sqlite")
    database.init_schema()
    return database


def _add_record(
    store: SQLiteStore,
    *,
    source: str = "alpha",
    captured_at: datetime = AS_OF - timedelta(hours=1),
    external_id: str | None = None,
) -> Record:
    return store.add_record(
        Record(
            kind="note",
            source=source,
            external_id=external_id,
            text=f"{source} record {external_id or captured_at.isoformat()}",
            captured_at=captured_at,
        )
    ).record


def _refinement(
    record_id: str,
    *,
    item_index: int = 0,
    content_kind: str = "event",
    city_id: str | None = None,
    refined_at: datetime = AS_OF,
    schedule: dict[str, object] | None = None,
    refiner: str = "test",
) -> Refinement:
    return Refinement(
        record_id=record_id,
        item_index=item_index,
        content_kind=content_kind,
        city_id=city_id,
        refined_at=refined_at,
        schedule=schedule,
        refiner=refiner,
    )


def _refine(store: SQLiteStore, record: Record, *refinements: Refinement) -> None:
    store.replace_refinements(record.id, list(refinements))


def _record_status(report, source: str):
    return next(item for item in report.sources if item.source == source)


def test_empty_database_returns_zero_filled_report(store: SQLiteStore) -> None:
    report = build_source_stats_report(store, weeks=8, as_of=AS_OF)

    assert report.as_of == AS_OF
    assert report.reporting_timezone == "Europe/Vilnius"
    assert report.ingestion_time_basis == "captured_at"
    assert report.totals.ingestion.records_total == 0
    assert report.totals.ingestion.records_with_refinement_total == 0
    assert report.totals.ingestion.pending_records_total == 0
    assert report.totals.ingestion.oldest_pending_captured_at is None
    assert report.totals.ingestion.latest_captured_at is None
    assert report.totals.refinement.refinement_items_total == 0
    assert report.totals.refinement.refinement_items_by_kind.total == 0
    assert report.totals.refinement.event_items_total == 0
    assert report.totals.refinement.last_refined_at is None
    assert report.sources == ()
    assert [week.week_start for week in report.weeks] == list(WEEK_STARTS)
    assert all(week.records == week.with_refinement == week.pending == 0 for week in report.weeks)
    assert report.weeks[-1].is_partial is True
    assert report.weeks[-1].ends_at == AS_OF
    assert report.supported_cities_total == 1
    assert [city.city_id for city in report.cities] == ["lt/vilnius"]
    assert report.cities[0].event_items_total == 0
    assert report.cities[0].sources_with_event_items == 0
    assert report.unassigned_city_event_items_total == 0
    assert report.unsupported_city_event_items_total == 0


def test_multiple_refinements_count_each_record_once_and_each_item_separately(
    store: SQLiteStore,
) -> None:
    multi = _add_record(store, captured_at=datetime(2026, 10, 27, 8, tzinfo=timezone.utc))
    pending = _add_record(
        store,
        captured_at=datetime(2026, 10, 20, 8, tzinfo=timezone.utc),
        external_id="pending",
    )
    beta_record = _add_record(
        store,
        source="beta",
        captured_at=datetime(2026, 10, 27, 9, tzinfo=timezone.utc),
        external_id="beta-non-event",
    )

    recurring = {
        "version": 1,
        "timezone": "Europe/Vilnius",
        "kind": "occurrences",
        "occurrences": [
            {"start": "2026-10-27T18:00", "end": None},
            {"start": "2026-10-28T18:00", "end": None},
        ],
    }
    _refine(
        store,
        multi,
        _refinement(multi.id, item_index=0, schedule=recurring),
        _refinement(multi.id, item_index=1),
        _refinement(multi.id, item_index=2, content_kind="advertisement"),
    )
    _refine(store, beta_record, _refinement(beta_record.id, content_kind="non_event"))

    report = build_source_stats_report(store, as_of=AS_OF)

    assert report.totals.ingestion.records_total == 3
    assert report.totals.ingestion.records_with_refinement_total == 2
    assert report.totals.ingestion.pending_records_total == 1
    assert report.totals.ingestion.oldest_pending_captured_at == pending.captured_at
    assert report.totals.refinement.refinement_items_total == 4
    assert report.totals.refinement.refinement_items_by_kind.model_dump() == {
        "event": 2,
        "advertisement": 1,
        "announcement": 0,
        "non_event": 1,
        "unknown": 0,
    }
    assert report.totals.refinement.event_items_total == 2

    alpha = _record_status(report, "alpha")
    assert alpha.ingestion.records_total == 2
    assert alpha.ingestion.records_with_refinement_total == 1
    assert alpha.ingestion.pending_records_total == 1
    assert alpha.refinement.refinement_items_total == 3
    assert alpha.refinement.event_items_total == 2
    assert alpha.ingestion.oldest_pending_captured_at == pending.captured_at
    current = alpha.weeks[-1]
    assert (current.records, current.with_refinement, current.pending) == (1, 1, 0)
    previous = alpha.weeks[-2]
    assert (previous.records, previous.with_refinement, previous.pending) == (1, 0, 1)
    assert len(alpha.weeks) == 8
    beta = _record_status(report, "beta")
    assert beta.refinement.refinement_items_by_kind.non_event == 1
    assert beta.refinement.event_items_total == 0


def test_qc_unknown_and_non_event_outputs_are_coverage_not_backlog(
    store: SQLiteStore,
) -> None:
    unknown = _add_record(store, external_id="unknown")
    non_event = _add_record(store, external_id="non-event")
    _refine(
        store,
        unknown,
        _refinement(unknown.id, content_kind="unknown", refiner="qc:rejected"),
    )
    _refine(store, non_event, _refinement(non_event.id, content_kind="advertisement"))

    report = build_source_stats_report(store, as_of=AS_OF)
    source = _record_status(report, "alpha")

    assert report.totals.ingestion.records_with_refinement_total == 2
    assert report.totals.ingestion.pending_records_total == 0
    assert report.totals.ingestion.oldest_pending_captured_at is None
    assert source.ingestion.pending_records_total == 0
    assert report.totals.refinement.refinement_items_by_kind.unknown == 1
    assert report.totals.refinement.refinement_items_by_kind.advertisement == 1
    assert report.totals.refinement.event_items_total == 0
    assert report.weeks[-1].with_refinement == 2
    assert report.weeks[-1].pending == 0


def test_city_buckets_reconcile_known_unsupported_and_unassigned_events(
    store: SQLiteStore,
) -> None:
    first = _add_record(store, external_id="city-a")
    second = _add_record(store, source="beta", external_id="city-b")
    _refine(
        store,
        first,
        _refinement(first.id, item_index=0, city_id="lt/vilnius"),
        _refinement(first.id, item_index=1, city_id=" LT/Vilnius "),
        _refinement(first.id, item_index=2, city_id="lt/kaunas"),
    )
    _refine(
        store,
        second,
        _refinement(second.id, item_index=0, city_id="lt/vilnius"),
        _refinement(second.id, item_index=1, city_id=None),
    )

    report = build_source_stats_report(store, as_of=AS_OF)

    vilnius = report.cities[0]
    assert vilnius.city_id == "lt/vilnius"
    assert vilnius.event_items_total == 3
    assert vilnius.sources_with_event_items == 2
    assert report.unassigned_city_event_items_total == 1
    assert report.unsupported_city_event_items_total == 1
    assert (
        sum(city.event_items_total for city in report.cities)
        + report.unassigned_city_event_items_total
        + report.unsupported_city_event_items_total
        == report.totals.refinement.event_items_total
    )
    assert report.totals.refinement.event_items_total == 5


def test_duplicate_fetch_preserves_original_capture_time(store: SQLiteStore) -> None:
    original = _add_record(
        store,
        captured_at=datetime(2026, 9, 1, 8, tzinfo=timezone.utc),
        external_id="duplicate",
    )
    duplicate = _add_record(
        store,
        captured_at=datetime(2026, 10, 27, 10, tzinfo=timezone.utc),
        external_id="duplicate",
    )

    report = build_source_stats_report(store, as_of=AS_OF)
    source = _record_status(report, "alpha")

    assert duplicate.id == original.id
    assert report.totals.ingestion.records_total == 1
    assert source.ingestion.latest_captured_at == original.captured_at
    assert sum(week.records for week in source.weeks) == 0
    assert source.ingestion.pending_records_total == 1


def test_old_sources_remain_in_inventory_with_zero_recent_weeks(store: SQLiteStore) -> None:
    old = _add_record(
        store,
        source="old-source",
        captured_at=datetime(2024, 1, 2, 8, tzinfo=timezone.utc),
        external_id="old",
    )
    _add_record(store, captured_at=AS_OF, external_id="new")

    report = build_source_stats_report(store, weeks=4, as_of=AS_OF)
    old_status = _record_status(report, "old-source")

    assert [source.source for source in report.sources] == ["alpha", "old-source"]
    assert old_status.ingestion.records_total == 1
    assert old_status.ingestion.pending_records_total == 1
    assert old_status.ingestion.oldest_pending_captured_at == old.captured_at
    assert all(week.records == 0 for week in old_status.weeks)
    assert report.totals.ingestion.records_total == 2
    assert report.totals.ingestion.pending_records_total == 2
    assert report.totals.ingestion.oldest_pending_captured_at == old.captured_at


def test_week_boundaries_dst_partial_week_and_future_captures(store: SQLiteStore) -> None:
    _add_record(
        store,
        source="boundary",
        captured_at=datetime(2026, 10, 18, 21, 0, tzinfo=timezone.utc),
        external_id="dst-start",
    )
    _add_record(
        store,
        source="boundary",
        captured_at=datetime(2026, 10, 25, 21, 59, 59, 999999, tzinfo=timezone.utc),
        external_id="dst-end",
    )
    _add_record(
        store,
        source="boundary",
        captured_at=datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc),
        external_id="next-week",
    )
    _add_record(
        store,
        source="boundary",
        captured_at=datetime(2026, 10, 27, 11, 59, 59, 999999, tzinfo=timezone.utc),
        external_id="before-as-of",
    )
    _add_record(
        store,
        source="boundary",
        captured_at=AS_OF,
        external_id="at-as-of",
    )
    _add_record(
        store,
        source="boundary",
        captured_at=datetime(2026, 10, 27, 13, 0, tzinfo=timezone.utc),
        external_id="future",
    )

    report = build_source_stats_report(store, as_of=AS_OF)
    dst_week = report.weeks[-2]
    current_week = report.weeks[-1]
    source = _record_status(report, "boundary")

    assert dst_week.week_start == date(2026, 10, 19)
    assert dst_week.starts_at == datetime(2026, 10, 18, 21, 0, tzinfo=timezone.utc)
    assert dst_week.ends_at == datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc)
    assert dst_week.ends_at - dst_week.starts_at == timedelta(hours=169)
    assert dst_week.records == 2
    assert dst_week.is_partial is False

    assert current_week.week_start == date(2026, 10, 26)
    assert current_week.starts_at == datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc)
    assert current_week.ends_at == AS_OF
    assert current_week.is_partial is True
    assert current_week.records == 2

    assert source.weeks[-2].records == 2
    assert source.weeks[-1].records == 2


def test_exact_monday_boundary_allows_zero_width_current_week(store: SQLiteStore) -> None:
    as_of = datetime(2026, 10, 26, 0, 0, tzinfo=ZoneInfo("Europe/Vilnius"))
    previous = _add_record(
        store,
        captured_at=datetime(2026, 10, 20, 8, tzinfo=timezone.utc),
        external_id="previous-week",
    )
    _add_record(
        store,
        captured_at=as_of.astimezone(timezone.utc),
        external_id="at-boundary",
    )
    _refine(store, previous, _refinement(previous.id))

    report = build_source_stats_report(store, weeks=2, as_of=as_of)

    current = report.weeks[-1]
    assert current.week_start == date(2026, 10, 26)
    assert current.starts_at == current.ends_at == as_of.astimezone(timezone.utc)
    assert current.is_partial is True
    assert (current.records, current.with_refinement, current.pending) == (0, 0, 0)

    previous_week = report.weeks[-2]
    assert previous_week.week_start == date(2026, 10, 19)
    assert (previous_week.records, previous_week.with_refinement, previous_week.pending) == (
        1,
        1,
        0,
    )
    source = _record_status(report, "alpha")
    assert (source.weeks[-1].records, source.weeks[-1].pending) == (0, 0)
    assert (source.weeks[-2].records, source.weeks[-2].with_refinement) == (1, 1)
    assert report.totals.ingestion.records_total == 2
    assert report.totals.ingestion.records_with_refinement_total == 1
    assert report.totals.ingestion.pending_records_total == 1

    single_week = build_source_stats_report(store, weeks=1, as_of=as_of)
    assert single_week.weeks[0].starts_at == single_week.weeks[0].ends_at
    assert single_week.weeks[0].records == 0


def test_snapshot_accepts_empty_week_bounds_but_rejects_reversed_bounds(
    store: SQLiteStore,
) -> None:
    snapshot = store.load_source_status_snapshot(week_bounds=[(AS_OF, AS_OF)])
    assert snapshot.records.records_total == 0

    with pytest.raises(ValueError, match="must not be after"):
        store.load_source_status_snapshot(week_bounds=[(AS_OF, AS_OF - timedelta(seconds=1))])


def test_weeks_validation_and_timezone_aware_as_of(store: SQLiteStore) -> None:
    for invalid in (0, 53, -1, True):
        with pytest.raises(ValueError):
            build_source_stats_report(store, weeks=invalid, as_of=AS_OF)

    with pytest.raises(ValueError):
        build_source_stats_report(store, as_of=datetime(2026, 10, 27, 12, 0))

    localized = build_source_stats_report(
        store,
        weeks=1,
        as_of=datetime(2026, 10, 27, 14, 0, tzinfo=ZoneInfo("Europe/Vilnius")),
    )
    assert localized.as_of == datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    assert localized.weeks[0].week_start == date(2026, 10, 26)


def test_old_backlog_and_empty_backlog_age(store: SQLiteStore) -> None:
    empty = build_source_stats_report(store, as_of=AS_OF)
    assert empty.totals.ingestion.oldest_pending_captured_at is None

    old = _add_record(
        store,
        captured_at=datetime(2025, 1, 1, 8, tzinfo=timezone.utc),
        external_id="backlog",
    )
    report = build_source_stats_report(store, weeks=4, as_of=AS_OF)

    assert report.totals.ingestion.pending_records_total == 1
    assert report.totals.ingestion.oldest_pending_captured_at == old.captured_at
    assert sum(week.records for week in report.weeks) == 0
    assert sum(week.pending for week in report.weeks) == 0


def test_refining_an_old_record_updates_its_cohort_not_current_ingestion(
    store: SQLiteStore,
) -> None:
    old = _add_record(
        store,
        captured_at=datetime(2026, 10, 13, 8, tzinfo=timezone.utc),
        external_id="old-cohort",
    )
    before = build_source_stats_report(store, as_of=AS_OF)
    cohort_index = next(
        index for index, week in enumerate(before.weeks) if week.week_start == date(2026, 10, 12)
    )
    assert before.weeks[cohort_index].records == 1
    assert before.weeks[cohort_index].pending == 1
    assert before.weeks[-1].records == 0

    _refine(store, old, _refinement(old.id))

    after = build_source_stats_report(store, as_of=AS_OF)
    after_source = _record_status(after, "alpha")
    assert after.weeks[cohort_index].pending == 0
    assert after.weeks[cohort_index].with_refinement == 1
    assert after.weeks[-1].records == 0
    assert after.totals.ingestion.records_total == before.totals.ingestion.records_total
    assert after.totals.ingestion.pending_records_total == 0
    assert after_source.weeks[cohort_index].with_refinement == 1


def test_replacement_replaces_output_without_double_counting_input_records(
    store: SQLiteStore,
) -> None:
    record = _add_record(store, external_id="replaced")
    _refine(
        store,
        record,
        _refinement(record.id, item_index=0),
        _refinement(record.id, item_index=1, content_kind="non_event"),
        _refinement(record.id, item_index=2, content_kind="unknown"),
    )
    before = build_source_stats_report(store, as_of=AS_OF)
    assert before.totals.ingestion.records_with_refinement_total == 1
    assert before.totals.refinement.refinement_items_total == 3

    _refine(store, record, _refinement(record.id, item_index=0))
    after = build_source_stats_report(store, as_of=AS_OF)

    assert after.totals.ingestion.records_total == 1
    assert after.totals.ingestion.records_with_refinement_total == 1
    assert after.totals.ingestion.pending_records_total == 0
    assert after.totals.refinement.refinement_items_total == 1
    assert after.totals.refinement.event_items_total == 1
    assert after.totals.refinement.refinement_items_by_kind.non_event == 0


def test_record_and_item_totals_reconcile_separately(store: SQLiteStore) -> None:
    records: list[Record] = []
    for index in range(5):
        records.append(
            _add_record(
                store,
                source="alpha" if index % 2 == 0 else "beta",
                captured_at=datetime(2026, 10, 20 + index, 8, tzinfo=timezone.utc),
                external_id=f"reconcile-{index}",
            )
        )
    _refine(
        store,
        records[0],
        _refinement(records[0].id, item_index=0, city_id="lt/vilnius"),
        _refinement(records[0].id, item_index=1, content_kind="advertisement"),
    )
    _refine(
        store,
        records[1],
        _refinement(records[1].id, item_index=0, city_id="lt/kaunas"),
        _refinement(records[1].id, item_index=1, content_kind="unknown"),
    )
    _refine(
        store,
        records[2],
        _refinement(records[2].id, item_index=0, city_id=None),
    )

    report = build_source_stats_report(store, as_of=AS_OF)

    assert (
        report.totals.ingestion.records_total
        == report.totals.ingestion.records_with_refinement_total
        + report.totals.ingestion.pending_records_total
    )
    assert report.totals.refinement.refinement_items_total == (
        report.totals.refinement.refinement_items_by_kind.total
    )
    assert report.totals.refinement.event_items_total == (
        report.totals.refinement.refinement_items_by_kind.event
    )
    assert report.totals.refinement.event_items_total == (
        sum(city.event_items_total for city in report.cities)
        + report.unassigned_city_event_items_total
        + report.unsupported_city_event_items_total
    )
    for week in report.weeks:
        assert week.records == week.with_refinement + week.pending
    for source in report.sources:
        assert (
            source.ingestion.records_total
            == source.ingestion.records_with_refinement_total
            + source.ingestion.pending_records_total
        )
        for week in source.weeks:
            assert week.records == week.with_refinement + week.pending
    assert sum(sum(week.records for week in source.weeks) for source in report.sources) == sum(
        week.records for week in report.weeks
    )


def test_report_uses_one_consistent_sqlite_snapshot_during_concurrent_writes(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "wal.sqlite")
    store.init_schema()
    with store.engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one()
        connection.rollback()
    assert str(journal_mode).lower() == "wal"

    seed = _add_record(
        store,
        captured_at=AS_OF - timedelta(days=30),
        external_id="seed",
    )
    _refine(store, seed, _refinement(seed.id, city_id="lt/vilnius"))

    select_count = 0
    reader_connections: set[int] = set()
    writer_finished = False
    writing = False

    def capture(
        connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        nonlocal select_count, writer_finished, writing
        if writing or not statement.lstrip().upper().startswith("SELECT"):
            return
        select_count += 1
        reader_connections.add(id(connection))
        if select_count != 6 or writer_finished:
            return
        writer_finished = True
        writing = True
        try:
            late = _add_record(
                store,
                source="late",
                captured_at=AS_OF - timedelta(minutes=5),
                external_id="late",
            )
            _refine(store, late, _refinement(late.id, city_id="lt/vilnius"))
        finally:
            writing = False

    event.listen(store.engine, "before_cursor_execute", capture)
    try:
        report = build_source_stats_report(store, as_of=AS_OF)
    finally:
        event.remove(store.engine, "before_cursor_execute", capture)

    assert writer_finished is True
    assert select_count == 6
    assert len(reader_connections) == 1
    assert report.totals.ingestion.records_total == 1
    assert report.totals.refinement.event_items_total == 1
    assert report.cities[0].event_items_total == 1
    assert (
        sum(city.event_items_total for city in report.cities)
        + report.unassigned_city_event_items_total
        + report.unsupported_city_event_items_total
        == report.totals.refinement.event_items_total
    )

    later = build_source_stats_report(store, as_of=AS_OF)
    assert later.totals.ingestion.records_total == 2
    assert later.totals.refinement.event_items_total == 2
    assert later.cities[0].event_items_total == 2


def test_postgresql_snapshot_uses_one_repeatable_read_connection() -> None:
    class FakeResult:
        def __init__(self, row: object | None = None) -> None:
            self.row = row

        def one(self) -> object:
            return self.row

        def all(self) -> list[object]:
            return []

    class FakeConnection:
        def __init__(self) -> None:
            self.options: dict[str, object] | None = None
            self.statements: list[object] = []
            self.rolled_back = False
            self.closed = False

        def execution_options(self, **kwargs: object) -> FakeConnection:
            self.options = kwargs
            return self

        def execute(self, statement: object) -> FakeResult:
            self.statements.append(statement)
            if len(self.statements) == 1:
                return FakeResult(
                    SimpleNamespace(
                        records_total=0,
                        records_with_refinement_total=0,
                        oldest_pending_captured_at=None,
                        latest_captured_at=None,
                    )
                )
            return FakeResult()

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()
    engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        connect=lambda: connection,
    )
    store = object.__new__(DatabaseStore)
    store.engine = engine

    snapshot = store.load_source_status_snapshot(
        week_bounds=[
            (
                datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc),
                datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc),
            ),
            (
                datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc),
                AS_OF,
            ),
        ]
    )

    assert snapshot.records.records_total == 0
    assert connection.options == {
        "isolation_level": "REPEATABLE READ",
        "postgresql_readonly": True,
    }
    assert len(connection.statements) == 6
    assert connection.rolled_back is True
    assert connection.closed is True


def test_query_count_is_independent_of_source_and_city_count(store: SQLiteStore) -> None:
    _add_record(store, external_id="single")
    one_source_queries = _count_report_queries(store)

    many_sources = SQLiteStore(store.path.parent / "many.sqlite")
    many_sources.init_schema()
    for source_index in range(8):
        record = _add_record(
            many_sources,
            source=f"source-{source_index}",
            external_id=f"many-{source_index}",
        )
        _refine(
            many_sources,
            record,
            _refinement(record.id, item_index=0, city_id=f"city/{source_index}"),
            _refinement(record.id, item_index=1, city_id="lt/vilnius"),
        )
    many_source_queries = _count_report_queries(many_sources)

    assert one_source_queries == many_source_queries == 6


def test_postgresql_query_construction(store: SQLiteStore) -> None:
    bounds = [
        (
            datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc),
        ),
        (
            datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc),
            AS_OF,
        ),
    ]

    queries = (
        _record_totals_query(),
        _source_record_totals_query(),
        _source_week_records_query(bounds),
        _refinement_totals_query(),
        _source_refinement_query(),
        _city_event_query(),
    )

    for query in queries:
        compiled = query.compile(dialect=postgresql.dialect())
        assert compiled is not None
        assert compiled.string


def _count_report_queries(store: SQLiteStore) -> int:
    statements: list[str] = []

    def capture(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(store.engine, "before_cursor_execute", capture)
    try:
        build_source_stats_report(store, as_of=AS_OF)
    finally:
        event.remove(store.engine, "before_cursor_execute", capture)
    return len(statements)
