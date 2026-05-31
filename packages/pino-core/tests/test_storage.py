from datetime import datetime, timezone
from pathlib import Path

from pino_core import ChatMessage, MemoryEntry, Record, Refinement, SQLiteStore


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
                location="Loftas",
                category_scores={"metal_music": 0.75},
                refiner="test",
            ),
        ],
    )

    assert store.list_unrefined_records() == []
    refinement = store.list_refinements(inserted.record.id)[0]
    assert refinement.summary == "A refined"
    assert refinement.relevant_from == relevant_from
    assert refinement.relevant_to == relevant_to
    assert refinement.category_scores == {"metal_music": 0.75}


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
    ]


def test_source_cursor_round_trip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()

    assert store.get_source_cursor("telegram") is None

    store.set_source_cursor("telegram", "42")
    assert store.get_source_cursor("telegram") == "42"

    store.set_source_cursor("telegram", "43")
    assert store.get_source_cursor("telegram") == "43"
