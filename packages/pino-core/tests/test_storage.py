from pathlib import Path

from pino_core import MemoryEntry, SQLiteStore


def test_active_memory_round_trip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()

    store.add_memory(MemoryEntry(content="Boss prefers concise digests.", tags=["preference"]))

    memories = store.list_memory()
    assert len(memories) == 1
    assert memories[0].content == "Boss prefers concise digests."
    assert memories[0].tags == ["preference"]

