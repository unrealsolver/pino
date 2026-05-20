from datetime import datetime, timezone
from pathlib import Path

from pino_core import ChatMessage, Evaluation, MemoryEntry, Record, SQLiteStore


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


def test_record_relevance_window_round_trip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    relevant_from = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    relevant_to = datetime(2026, 5, 23, 14, 0, tzinfo=timezone.utc)

    store.add_record(
        Record(
            kind="event",
            source="test",
            title="A",
            text="A",
            relevant_from=relevant_from,
            relevant_to=relevant_to,
        ),
    )

    record = store.list_records()[0]
    assert record.relevant_from == relevant_from
    assert record.relevant_to == relevant_to


def test_evaluation_round_trip_and_unevaluated_records(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="A", text="A"))

    assert [record.id for record in store.list_unevaluated_records()] == [inserted.record.id]

    store.add_evaluation(
        Evaluation(
            record_id=inserted.record.id,
            score=0.75,
            goal_matches=["metal_music"],
            reasons=["Looks relevant."],
        ),
    )

    assert store.list_unevaluated_records() == []
    evaluation = store.get_evaluation(inserted.record.id)
    assert evaluation is not None
    assert evaluation.score == 0.75


def test_list_relevant_records_with_evaluations_filters_by_overlap(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    window_start = datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)

    past = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Past",
            text="Past event",
            relevant_from=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            relevant_to=datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
        ),
    )
    current = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Current",
            text="Current event",
            relevant_from=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
            relevant_to=datetime(2026, 5, 21, 13, 0, tzinfo=timezone.utc),
        ),
    )
    future = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Future",
            text="Future event",
            relevant_from=datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
            relevant_to=datetime(2026, 5, 22, 13, 0, tzinfo=timezone.utc),
        ),
    )
    undated = store.add_record(Record(kind="note", source="test", title="Undated", text="Note"))
    store.add_evaluation(Evaluation(record_id=past.record.id, score=1.0))
    store.add_evaluation(Evaluation(record_id=current.record.id, score=0.8))
    store.add_evaluation(Evaluation(record_id=future.record.id, score=0.9))

    rows = store.list_relevant_records_with_evaluations(
        window_start=window_start,
        window_end=window_end,
    )

    assert [record.id for record, _evaluation in rows] == [
        future.record.id,
        current.record.id,
        undated.record.id,
    ]
