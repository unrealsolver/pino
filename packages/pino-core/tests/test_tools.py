from datetime import datetime, timezone
from pathlib import Path

from pino_core.models import Evaluation, Record
from pino_core.storage import SQLiteStore
from pino_core.tools import WebPage, build_tools, describe_tools


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
    assert "[unevaluated]" in unfiltered
    assert "Raw unevaluated text" in unfiltered
    assert "Unevaluated event" not in filtered


def test_records_list_labels_evaluation_status(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    evaluated = store.add_record(Record(kind="event", source="test", title="Evaluated", text="A"))
    store.add_record(Record(kind="event", source="test", title="Unevaluated", text="B"))
    store.add_evaluation(Evaluation(record_id=evaluated.record.id, score=0.8, goal_matches=["metal_music"]))

    output = build_tools(store, sources=[])["records.list"].run({"limit": 10})

    assert "Evaluated (test) [score 0.80 metal_music]" in output
    assert "Unevaluated (test) [unevaluated]" in output


def test_web_open_returns_readable_page_text(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")

    def fetcher(url: str) -> WebPage:
        return WebPage(
            url=url,
            status_code=200,
            content_type="text/html; charset=utf-8",
            text="""
<html>
  <head>
    <title>Noise Night</title>
    <meta name="description" content="Experimental concert in Vilnius">
    <script>secretTracker()</script>
  </head>
  <body>
    <h1>Noise Night</h1>
    <p>Doors at 19:00. Tickets at the venue.</p>
  </body>
</html>
""",
        )

    output = build_tools(store, sources=[], web_fetcher=fetcher)["web.open"].run(
        {"url": "https://example.com/event", "max_chars": 1000},
    )

    assert "URL: https://example.com/event" in output
    assert "Status: 200" in output
    assert "Content-Type: text/html" in output
    assert "Title: Noise Night" in output
    assert "Description: Experimental concert in Vilnius" in output
    assert "Doors at 19:00. Tickets at the venue." in output
    assert "secretTracker" not in output


def test_web_open_rejects_non_public_urls(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    tool = build_tools(store, sources=[])["web.open"]

    assert "only http and https" in tool.run({"url": "file:///etc/passwd"})
    assert "local hostnames" in tool.run({"url": "http://localhost/event"})
    assert "private, loopback" in tool.run({"url": "http://127.0.0.1/event"})


def test_web_open_truncates_text(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")

    def fetcher(url: str) -> WebPage:
        return WebPage(
            url=url,
            status_code=200,
            content_type="text/plain",
            text="A" * 800,
        )

    output = build_tools(store, sources=[], web_fetcher=fetcher)["web.open"].run(
        {"url": "https://example.com/event", "max_chars": 500},
    )

    assert "[truncated to 500 characters]" in output


def test_tool_descriptions_include_records_relevant_as_preferred_path(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")

    descriptions = describe_tools(build_tools(store, sources=[]))

    assert "records.relevant" in descriptions
    assert "Preferred for event recommendations" in descriptions
    assert "records.list" in descriptions
    assert "inspection/debug only" in descriptions
    assert "web.open" in descriptions
    assert "Open one public http(s) URL" in descriptions
