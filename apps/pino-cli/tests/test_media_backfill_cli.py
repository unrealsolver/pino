from io import StringIO

import pytest
from rich.console import Console

from pino_cli import main
from pino_core.config import PinoConfig, SourceConfig
from pino_core.models import Record, RecordImage
from pino_core.storage import SQLiteStore


@pytest.mark.parametrize("authenticated", [False, True])
def test_explicit_backfill_batches_without_fetch_or_cursor_changes(
    tmp_path, monkeypatch, authenticated
):
    config = PinoConfig(
        sources=[SourceConfig(name="test", type="static_yaml", path=tmp_path / "unused.yaml")]
    )
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.init_schema()
    for index in range(101):
        store.add_record(
            Record(id=f"{index:04}", kind="event", source="test", text=f"item {index}")
        )
    store.set_source_cursor("test", "123")
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, width=200, force_terminal=False))
    monkeypatch.setattr(main, "get_config", lambda _: config)
    monkeypatch.setattr(main, "get_store", lambda _: store)
    image = RecordImage(path="a" * 64 + ".webp", source_url="https://example.com/image")

    def enrich(record):
        return record.model_copy(update={"images": [image]})

    monkeypatch.setattr(main.MediaStore, "enrich", lambda self, record, **kwargs: enrich(record))
    batches = []

    class Source:
        def fetch(self):
            raise AssertionError("backfill must not fetch new records")

    class AuthenticatedSource(Source):
        def enrich_media(self, records, media):
            batches.append(len(records))
            return [enrich(record) for record in records]

    monkeypatch.setattr(
        main, "build_sources", lambda _: [AuthenticatedSource() if authenticated else Source()]
    )

    main.sources_backfill_media(source_name="test", config_path=None)
    assert "101 scanned, 101 updated" in output.getvalue()
    assert store.get_source_cursor("test") == "123"
    assert len(store.list_records(limit=200)) == 101
    assert store.count_unrefined_records() == 101
    assert all(record.images == [image] for record in store.list_records(limit=200))
    if authenticated:
        assert batches == [100, 1]
    main.sources_backfill_media(source_name="test", config_path=None)
    assert "101 scanned, 0 updated" in output.getvalue()
