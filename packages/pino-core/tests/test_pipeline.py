from datetime import datetime, timezone
from pathlib import Path

from pino_core import CheckPipeline, DigestService, Evaluation, Record, SQLiteStore
from pino_core.sources import StaticYamlSource


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
    assert len(store.list_records()) == 1


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
    assert "Test record" in digest.body


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
            relevant_from=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            relevant_to=datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
        ),
    )
    upcoming = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Upcoming event",
            text="Upcoming event text",
            relevant_from=datetime(2026, 5, 22, 15, 0, tzinfo=timezone.utc),
            relevant_to=datetime(2026, 5, 22, 17, 0, tzinfo=timezone.utc),
            payload={"location": "Loftas"},
        ),
    )
    store.add_evaluation(Evaluation(record_id=old.record.id, score=1.0, summary="Old summary"))
    store.add_evaluation(
        Evaluation(
            record_id=upcoming.record.id,
            score=0.9,
            goal_matches=["electronic_music"],
            summary="Upcoming summary",
        ),
    )

    digest = DigestService(store).create_digest(window_start=window_start, window_days=7)

    assert "Upcoming event" in digest.body
    assert "Old event" not in digest.body
    assert "score 0.90 electronic_music" in digest.body
    assert "2026-05-22 18:00-20:00" in digest.body
    assert "@ Loftas" in digest.body
