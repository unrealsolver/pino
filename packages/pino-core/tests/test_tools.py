from datetime import datetime, timezone
from pathlib import Path

from pino_core.models import Record, Refinement
from pino_core.storage import SQLiteStore
from pino_core.tools import WebPage, build_tools, describe_tools


def test_records_relevant_returns_refined_recommendation_fields(
    tmp_path: Path, monkeypatch
) -> None:
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
        ),
    )
    upcoming = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Upcoming synth night",
            text="Raw upcoming text",
            url="https://example.test/event",
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
                category_scores={"electronic_music": 1.0},
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
                summary="Refined upcoming summary",
                relevant_from=datetime(2026, 5, 22, 15, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 5, 22, 17, 0, tzinfo=timezone.utc),
                location="Loftas",
                category_scores={"electronic_music": 0.9},
                refiner="test",
            ),
        ],
    )

    output = build_tools(store, sources=[])["records.relevant"].run(
        {"limit": 10, "days": 7, "min_score": 0.3, "categories": ["electronic_music"]},
    )

    assert "Upcoming synth night" in output
    assert "Old event" not in output
    assert "electronic_music=0.90" in output
    assert "2026-05-22 18:00-20:00" in output
    assert "@ Loftas" in output
    assert "[url: https://example.test/event]" in output
    assert "Refined upcoming summary" in output
    assert "Raw upcoming text" not in output


def test_records_relevant_filters_after_scanning_beyond_return_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "pino_core.tools.utc_now",
        lambda: datetime(2026, 5, 21, 0, 0, tzinfo=timezone.utc),
    )
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    for day in range(1, 5):
        record = store.add_record(
            Record(
                kind="event",
                source="test",
                title=f"Generic event {day}",
                text="Generic upcoming event",
            ),
        )
        store.replace_refinements(
            record.record.id,
            [
                Refinement(
                    record_id=record.record.id,
                    content_kind="event",
                    relevant_from=datetime(2026, 5, 21 + day, 12, 0, tzinfo=timezone.utc),
                    category_scores={"workshop": 0.8},
                    refiner="test",
                ),
            ],
        )
    matching = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Later synth meetup",
            text="Synth meetup text",
        ),
    )
    store.replace_refinements(
        matching.record.id,
        [
            Refinement(
                record_id=matching.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc),
                category_scores={"electronic_music": 0.7},
                refiner="test",
            ),
        ],
    )

    output = build_tools(store, sources=[])["records.relevant"].run(
        {"limit": 1, "days": 14, "min_score": 0.3, "categories": ["electronic_music"]},
    )

    assert "Later synth meetup" in output
    assert "Generic event" not in output


def test_records_relevant_accepts_single_day_local_date_range(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "pino_core.tools.utc_now",
        lambda: datetime(2026, 6, 4, 21, 0, tzinfo=timezone.utc),
    )
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    friday = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Macau short films",
            text="Screening and Q&A",
        ),
    )
    saturday = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Saturday high score",
            text="High-score event on the wrong day",
        ),
    )
    store.replace_refinements(
        friday.record.id,
        [
            Refinement(
                record_id=friday.record.id,
                content_kind="event",
                summary="Screening of five short films from Macau followed by Q&A.",
                relevant_from=datetime(2026, 6, 5, 16, 30, tzinfo=timezone.utc),
                location="Meno Avilys, Vilnius",
                category_scores={"social": 0.7, "theatre": 0.3},
                refiner="test",
            ),
        ],
    )
    store.replace_refinements(
        saturday.record.id,
        [
            Refinement(
                record_id=saturday.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc),
                category_scores={"social": 1.0},
                refiner="test",
            ),
        ],
    )

    output = build_tools(store, sources=[])["records.relevant"].run(
        {"limit": 20, "date_from": "2026-06-05", "date_to": "2026-06-05", "min_score": 0.1},
    )

    assert "Relevant records for 2026-06-05 (Europe/Vilnius):" in output
    assert "Macau short films" in output
    assert "2026-06-05 19:30" in output
    assert "@ Meno Avilys, Vilnius" in output
    assert "Saturday high score" not in output


def test_records_relevant_excludes_unrefined_records(
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
            title="Unrefined event",
            text="Raw unrefined text",
        ),
    )
    tool = build_tools(store, sources=[])["records.relevant"]

    unfiltered = tool.run({"limit": 10, "days": 7})

    assert "Unrefined event" not in unfiltered


def test_records_list_labels_refinement_status(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    refined = store.add_record(Record(kind="event", source="test", title="Refined", text="A"))
    store.add_record(Record(kind="event", source="test", title="Unrefined", text="B"))
    store.replace_refinements(
        refined.record.id,
        [Refinement(record_id=refined.record.id, content_kind="event", refiner="test")],
    )

    output = build_tools(store, sources=[])["records.list"].run({"limit": 10})

    assert "Refined (test) [refined:1]" in output
    assert "Unrefined (test) [unrefined]" in output


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
