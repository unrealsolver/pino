from datetime import datetime, timezone
from pathlib import Path

from pino_core import CheckPipeline, DigestService, Record, Refinement, SQLiteStore
from pino_core.sources import CursorFetchResult, StaticYamlSource


def test_check_pipeline_stores_static_source_records(tmp_path: Path) -> None:
    source_path = tmp_path / "source.yaml"
    source_path.write_text(
        """
records:
  - kind: note
    source: test
    title: Test record
    text: Useful thing
""",
        encoding="utf-8",
    )
    store = SQLiteStore(tmp_path / "pino.sqlite")

    result = CheckPipeline(store, [StaticYamlSource(source_path)]).run()

    assert result.fetched == 1
    assert result.inserted == 1
    assert result.duplicates == 0
    assert result.pending_refinement_total == 1
    assert result.pending_refinement_new == 1
    assert store.list_records()[0].title == "Test record"


def test_check_pipeline_reports_duplicate_records(tmp_path: Path) -> None:
    source_path = tmp_path / "source.yaml"
    source_path.write_text(
        """
records:
  - kind: note
    source: test
    title: Test record
    text: Useful thing
""",
        encoding="utf-8",
    )
    store = SQLiteStore(tmp_path / "pino.sqlite")

    first = CheckPipeline(store, [StaticYamlSource(source_path)]).run()
    second = CheckPipeline(store, [StaticYamlSource(source_path)]).run()

    assert first.inserted == 1
    assert second.fetched == 1
    assert second.inserted == 0
    assert second.duplicates == 1
    assert second.pending_refinement_total == 1
    assert second.pending_refinement_new == 0
    assert len(store.list_records()) == 1


def test_check_pipeline_persists_source_cursor_between_runs(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    source = CursorSource()

    first = CheckPipeline(store, [source]).run()
    second = CheckPipeline(store, [source]).run()

    assert first.inserted == 1
    assert second.inserted == 1
    assert source.cursors == [None, "1"]
    assert store.get_source_cursor(source.name) == "2"


def test_digest_service_creates_digest_result(tmp_path: Path) -> None:
    source_path = tmp_path / "source.yaml"
    source_path.write_text(
        """
records:
  - kind: note
    source: test
    title: Test record
    text: Useful thing
""",
        encoding="utf-8",
    )
    store = SQLiteStore(tmp_path / "pino.sqlite")
    CheckPipeline(store, [StaticYamlSource(source_path)]).run()

    digest = DigestService(store).create_digest()

    assert digest.title == "Latest digest"
    assert digest.body == "No relevant records found for the next 14 day(s)."


def test_digest_service_uses_relevance_window(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    window_start = datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc)
    old = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Old event",
            text="Old event text",
        ),
    )
    upcoming = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Upcoming event",
            text="Upcoming event text",
        ),
    )
    store.replace_refinements(
        old.record.id,
        [
            Refinement(
                record_id=old.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
                summary="Old summary",
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        upcoming.record.id,
        [
            Refinement(
                record_id=upcoming.record.id,
                content_kind="event",
                summary="Upcoming summary",
                relevant_from=datetime(2026, 5, 22, 15, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 5, 22, 17, 0, tzinfo=timezone.utc),
                location="Loftas",
                category_scores={"electronic_music": 0.9},
                refiner="test",
            ),
        ],
    )

    digest = DigestService(store).create_digest(window_start=window_start, window_days=7)

    assert "Upcoming event" in digest.body
    assert "Old event" not in digest.body
    assert "electronic_music=0.90" in digest.body
    assert "2026-05-22 18:00-20:00" in digest.body
    assert "@ Loftas" in digest.body


class CursorSource:
    name = "cursor-source"

    def __init__(self) -> None:
        self.cursors: list[str | None] = []

    def fetch_since(self, cursor: str | None) -> CursorFetchResult:
        self.cursors.append(cursor)
        next_cursor = str(len(self.cursors))
        return CursorFetchResult(
            records=[
                Record(
                    kind="note",
                    source=self.name,
                    external_id=next_cursor,
                    text=f"Record {next_cursor}",
                ),
            ],
            cursor=next_cursor,
        )
