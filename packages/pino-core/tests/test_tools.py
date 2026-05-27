from datetime import datetime, timezone
from pathlib import Path

from pino_core.models import Evaluation, Record
from pino_core.storage import SQLiteStore
from pino_core.tools import build_tools, describe_tools


def test_records_relevant_returns_evaluated_recommendation_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "pino_core.tools.utc_now",
        lambda: datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc),
    )
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
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
            title="Upcoming synth night",
            text="Raw upcoming text",
            url="https://example.test/event",
            relevant_from=datetime(2026, 5, 22, 15, 0, tzinfo=timezone.utc),
            relevant_to=datetime(2026, 5, 22, 17, 0, tzinfo=timezone.utc),
            payload={"location": "Loftas"},
        ),
    )
    store.add_evaluation(Evaluation(record_id=old.record.id, score=1.0, goal_matches=["electronic_music"]))
    store.add_evaluation(
        Evaluation(
            record_id=upcoming.record.id,
            score=0.9,
            goal_matches=["electronic_music"],
            summary="Evaluated upcoming summary",
        ),
    )

    output = build_tools(store, sources=[])["records.relevant"].run(
        {"limit": 10, "days": 7, "min_score": 0.3, "goals": ["electronic_music"]},
    )

    assert "Upcoming synth night" in output
    assert "Old event" not in output
    assert "score 0.90 electronic_music" in output
    assert "2026-05-22 18:00-20:00" in output
    assert "@ Loftas" in output
    assert "[url: https://example.test/event]" in output
    assert "Evaluated upcoming summary" in output
    assert "Raw upcoming text" not in output


def test_records_relevant_includes_unevaluated_records_only_without_filters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "pino_core.tools.utc_now",
        lambda: datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc),
    )
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_record(
        Record(
            kind="event",
            source="test",
            title="Unevaluated event",
            text="Raw unevaluated text",
            relevant_from=datetime(2026, 5, 22, 15, 0, tzinfo=timezone.utc),
            relevant_to=datetime(2026, 5, 22, 17, 0, tzinfo=timezone.utc),
        ),
    )
    tool = build_tools(store, sources=[])["records.relevant"]

    unfiltered = tool.run({"limit": 10, "days": 7})
    filtered = tool.run({"limit": 10, "days": 7, "min_score": 0.1})

    assert "Unevaluated event" in unfiltered
    assert "Raw unevaluated text" in unfiltered
    assert "Unevaluated event" not in filtered


def test_tool_descriptions_include_records_relevant_as_preferred_path(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")

    descriptions = describe_tools(build_tools(store, sources=[]))

    assert "records.relevant" in descriptions
    assert "Preferred for event recommendations" in descriptions
    assert "records.list" in descriptions
    assert "inspection/debug only" in descriptions
