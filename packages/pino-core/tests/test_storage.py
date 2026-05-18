from pathlib import Path

from pino_core import ChatMessage, MemoryEntry, Record, SQLiteStore


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
