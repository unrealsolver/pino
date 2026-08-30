from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from pino_llm import LLMUsage

from pino_core import ChatMessage, DatabaseStore, MemoryEntry, Record, Refinement, SQLiteStore


def test_database_store_normalizes_postgresql_url_to_psycopg(monkeypatch) -> None:
    created: list[tuple[object, bool]] = []

    def fake_create_engine(url: object, *, future: bool) -> SimpleNamespace:
        created.append((url, future))
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    monkeypatch.setattr("pino_core.storage.create_engine", fake_create_engine)

    store = DatabaseStore("postgresql://pino:secret@example.test/pino")

    assert store.database_url.drivername == "postgresql+psycopg"
    assert created == [(store.database_url, True)]


def test_database_store_skips_sqlite_legacy_migration_for_postgresql(
    monkeypatch,
) -> None:
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    create_calls: list[object] = []
    migration_calls: list[bool] = []
    monkeypatch.setattr(
        "pino_core.storage.create_engine",
        lambda url, *, future: engine,
    )
    monkeypatch.setattr(
        "pino_core.storage.metadata.create_all",
        lambda actual_engine: create_calls.append(actual_engine),
    )
    store = DatabaseStore("postgresql://pino@example.test/pino")
    monkeypatch.setattr(
        store,
        "_migrate_legacy_sqlite_records_table",
        lambda: migration_calls.append(True),
    )

    store.init_schema()

    assert create_calls == [engine]
    assert migration_calls == []


def test_active_memory_round_trip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()

    store.add_memory(MemoryEntry(content="Boss prefers concise digests.", tags=["preference"]))

    memories = store.list_memory()
    assert len(memories) == 1
    assert memories[0].content == "Boss prefers concise digests."
    assert memories[0].tags == ["preference"]


def test_clear_chat_messages(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_chat_message(ChatMessage(role="user", content="hello"))
    store.add_chat_message(ChatMessage(role="assistant", content="hi"))

    deleted = store.clear_chat_messages()

    assert deleted == 2
    assert store.list_chat_messages() == []


def test_llm_usage_events_round_trip_and_summary(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()

    store.add_llm_usage_event(
        LLMUsage(
            provider="minimax",
            model="MiniMax-M3",
            operation="refinement.extract",
            input_tokens=1000,
            output_tokens=120,
            cached_input_tokens=700,
            duration_ms=1500,
        )
    )
    store.add_llm_usage_event(
        LLMUsage(
            provider="minimax",
            model="MiniMax-M3",
            operation="chat",
            input_tokens=300,
            output_tokens=80,
            cached_input_tokens=30,
            duration_ms=500,
        )
    )

    rows = store.list_llm_usage_events()
    assert [row.operation for row in rows] == ["chat", "refinement.extract"]
    assert rows[0].input_tokens == 300

    total = store.summarize_llm_usage()["total"]
    assert total.calls == 2
    assert total.input_tokens == 1300
    assert total.cached_input_tokens == 730
    assert total.uncached_input_tokens == 570
    assert total.output_tokens == 200
    assert total.duration_ms == 2000
    assert total.average_duration_ms == 1000

    by_operation = store.summarize_llm_usage(group_by="operation")
    assert by_operation["chat"].calls == 1
    assert by_operation["refinement.extract"].cached_input_tokens == 700


def test_add_record_skips_duplicate_fingerprint(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    record = Record(kind="note", source="test", title="Same", text="Same text")

    first = store.add_record(record)
    second = store.add_record(record.model_copy(update={"id": "different-id"}))

    assert first.inserted is True
    assert second.inserted is False
    assert len(store.list_records()) == 1


def test_refinement_round_trip_and_unrefined_records(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="A", text="A"))
    relevant_from = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    relevant_to = datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc)
    schedule = {
        "timezone": "Europe/Vilnius",
        "kind": "recurrence",
        "rules": [{"days": ["TU"], "start": "19:00", "end": None}],
        "exceptions": [],
    }

    assert [record.id for record in store.list_unrefined_records()] == [inserted.record.id]

    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind="event",
                summary="A refined",
                relevant_from=relevant_from,
                relevant_to=relevant_to,
                schedule=schedule,
                location="Loftas",
                category_scores={"metal_music": 0.75},
                refiner="test",
            ),
        ],
    )

    assert store.list_unrefined_records() == []
    refinement = store.list_refinements(inserted.record.id)[0]
    assert refinement.summary == "A refined"
    assert refinement.relevant_from == datetime(2026, 5, 22, 21, 0, tzinfo=timezone.utc)
    assert refinement.relevant_to == datetime(
        2026, 5, 23, 20, 59, 59, 999999, tzinfo=timezone.utc
    )
    assert refinement.schedule == {
        "version": 1,
        "timezone": "Europe/Vilnius",
        "kind": "recurrence",
        "frequency": "weekly",
        "from": "2026-05-23",
        "until": "2026-05-23",
        "rules": [{"weekdays": ["tuesday"], "start": "19:00", "end": None}],
    }
    assert refinement.category_scores == {"metal_music": 0.75}
    assert store.get_record(inserted.record.id) == inserted.record
    assert store.get_record("missing") is None
    assert store.get_refinement(refinement.id) == refinement
    assert store.get_refinement("missing") is None


def test_refinement_datetimes_are_normalized_to_utc(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="A", text="A"))
    local_timezone = ZoneInfo("Europe/Vilnius")

    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 6, 10, 10, 0, tzinfo=local_timezone),
                relevant_to=datetime(2026, 6, 10, 12, 0, tzinfo=local_timezone),
                refiner="test",
            ),
        ],
    )

    refinement = store.list_refinements(inserted.record.id)[0]
    assert refinement.relevant_from == datetime(2026, 6, 10, 7, 0, tzinfo=timezone.utc)
    assert refinement.relevant_to == datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)


def test_refinement_status_is_derived_from_left_join(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    refined = store.add_record(Record(kind="event", source="test", title="Refined", text="A"))
    unrefined = store.add_record(Record(kind="event", source="test", title="Unrefined", text="B"))
    store.replace_refinements(
        refined.record.id,
        [Refinement(record_id=refined.record.id, content_kind="event", refiner="test")],
    )

    rows = store.list_records_with_refinement_status()

    by_id = {row.record.id: row for row in rows}
    assert by_id[refined.record.id].is_refined is True
    assert len(by_id[refined.record.id].refinements) == 1
    assert by_id[unrefined.record.id].is_refined is False
    assert by_id[unrefined.record.id].refinements == []
    assert store.count_unrefined_records() == 1
    assert store.count_unrefined_records(record_ids=[refined.record.id, unrefined.record.id]) == 1
    assert store.count_unrefined_records(record_ids=[refined.record.id]) == 0
    assert store.count_unrefined_records(record_ids=[]) == 0


def test_list_relevant_refinements_filters_by_overlap_and_kind(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    window_start = datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)

    past = store.add_record(Record(kind="event", source="test", title="Past", text="Past event"))
    current = store.add_record(
        Record(kind="event", source="test", title="Current", text="Current event")
    )
    future = store.add_record(
        Record(kind="event", source="test", title="Future", text="Future event")
    )
    past_point = store.add_record(
        Record(kind="event", source="test", title="Past point", text="Past point event")
    )
    future_point = store.add_record(
        Record(kind="event", source="test", title="Future point", text="Future point event")
    )
    ad = store.add_record(Record(kind="note", source="test", title="Ad", text="Advertisement"))
    undated = store.add_record(Record(kind="note", source="test", title="Undated", text="Note"))
    store.replace_refinements(
        past.record.id,
        [
            Refinement(
                record_id=past.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        current.record.id,
        [
            Refinement(
                record_id=current.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 5, 21, 13, 0, tzinfo=timezone.utc),
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        future.record.id,
        [
            Refinement(
                record_id=future.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 5, 22, 13, 0, tzinfo=timezone.utc),
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        past_point.record.id,
        [
            Refinement(
                record_id=past_point.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 3, 13, 17, 0, tzinfo=timezone.utc),
                relevant_to=None,
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        future_point.record.id,
        [
            Refinement(
                record_id=future_point.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 5, 23, 17, 0, tzinfo=timezone.utc),
                relevant_to=None,
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        ad.record.id,
        [
            Refinement(
                record_id=ad.record.id,
                content_kind="advertisement",
                relevant_from=datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        undated.record.id,
        [Refinement(record_id=undated.record.id, content_kind="event", refiner="test")],
    )

    rows = store.list_relevant_refinements(window_start=window_start, window_end=window_end)

    assert [record.id for record, _refinement in rows] == [
        current.record.id,
        future.record.id,
        future_point.record.id,
    ]


def test_query_events_filters_by_category_score_and_text(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    matching = store.add_record(
        Record(kind="event", source="test", title="Synth workshop", text="Hands-on synth jam")
    )
    wrong_category = store.add_record(
        Record(kind="event", source="test", title="Metal show", text="Concert")
    )
    weak_score = store.add_record(
        Record(kind="event", source="test", title="Synth lecture", text="Lecture")
    )
    store.replace_refinements(
        matching.record.id,
        [
            Refinement(
                record_id=matching.record.id,
                content_kind="event",
                summary="Open synth jam",
                relevant_from=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
                category_scores={"electronic_music": 0.9, "workshop": 0.4},
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        wrong_category.record.id,
        [
            Refinement(
                record_id=wrong_category.record.id,
                content_kind="event",
                summary="Metal concert",
                relevant_from=datetime(2026, 5, 23, 13, 0, tzinfo=timezone.utc),
                category_scores={"metal_music": 0.9},
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        weak_score.record.id,
        [
            Refinement(
                record_id=weak_score.record.id,
                content_kind="event",
                summary="Synth talk",
                relevant_from=datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc),
                category_scores={"electronic_music": 0.2},
                refiner="test",
            ),
        ],
    )

    rows = store.query_events(
        window_start=datetime(2026, 5, 23, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 5, 24, 0, 0, tzinfo=timezone.utc),
        categories=["electronic_music"],
        min_score=0.8,
        text_query="jam",
    )

    assert [(row.record.id, row.score) for row in rows] == [(matching.record.id, 0.9)]


def test_source_cursor_round_trip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()

    assert store.get_source_cursor("telegram") is None

    store.set_source_cursor("telegram", "42")
    assert store.get_source_cursor("telegram") == "42"

    store.set_source_cursor("telegram", "43")
    assert store.get_source_cursor("telegram") == "43"
