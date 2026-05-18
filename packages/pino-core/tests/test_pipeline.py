from pathlib import Path

from pino_core import CheckPipeline, DigestService, SQLiteStore
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


def test_digest_service_creates_artifact(tmp_path: Path) -> None:
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

    artifact = DigestService(store).create_digest()

    assert artifact.kind == "digest"
    assert "Test record" in artifact.body
