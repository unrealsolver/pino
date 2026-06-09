from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from pino_core.config import PinoConfig, RefinementConfig, StorageConfig, TaxonomyCategoryConfig
from pino_core.models import Record, Refinement
from pino_core.storage import SQLiteStore
from pino_web.app import MAX_QUERY_DAYS, _resolve_window, _to_event_item, _validate_categories, create_app


def test_app_registers_event_route_and_configured_store(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    app = create_app(config=_config(tmp_path), store=store)

    assert app.state.store is store
    assert any(route.path == "/api/events" for route in app.routes)


def test_event_item_serializes_refinement_with_local_time(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Synth workshop",
            text="A participatory synth event.",
        ),
    )
    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind="event",
                summary="Open synth jam",
                relevant_from=datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 6, 10, 17, 0, tzinfo=timezone.utc),
                category_scores={"electronic_music": 0.8, "workshop": 0.5},
                refiner="test",
            ),
        ],
    )
    result = store.query_events(
        window_start=datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc),
        categories=["electronic_music"],
        min_score=0.7,
    )

    item = _to_event_item(result[0], timezone.utc)

    assert item.title == "Synth workshop"
    assert item.summary == "Open synth jam"
    assert item.matching_score == 0.8
    assert item.starts_at == datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
    assert item.original_starts_at == datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)


def test_event_item_clips_multiday_event_to_query_window(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="event", source="test", title="Long exhibition", text="Runs for months.")
    )
    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc),
                refiner="test",
            ),
        ],
    )
    window_start = datetime(2026, 6, 7, 21, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 7, 8, 21, 0, tzinfo=timezone.utc)
    result = store.query_events(window_start=window_start, window_end=window_end)

    item = _to_event_item(
        result[0],
        timezone.utc,
        window_start=window_start,
        window_end=window_end,
    )

    assert item.starts_at == window_start
    assert item.ends_at == window_end
    assert item.original_starts_at == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert item.original_ends_at == datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)


def test_events_endpoint_rejects_unknown_category(tmp_path: Path) -> None:
    known = [category.name for category in _config(tmp_path).refinement.categories]
    with pytest.raises(HTTPException) as exc_info:
        _validate_categories(["unknown"], known)

    assert known == ["electronic_music", "metal_music"]
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "unknown category: unknown"


def test_missing_end_date_uses_bounded_future_window() -> None:
    start = datetime(2026, 6, 7, 0, 0, tzinfo=ZoneInfo("Europe/Vilnius"))

    window_start, window_end = _resolve_window(start, None, ZoneInfo("Europe/Vilnius"))

    assert window_start == start
    assert window_end == start.replace(year=2027, month=6, day=12)
    assert (window_end - window_start).days == MAX_QUERY_DAYS


def _config(tmp_path: Path) -> PinoConfig:
    return PinoConfig(
        storage=StorageConfig(local={"type": "sqlite", "path": tmp_path / "pino.sqlite"}),
        refinement=RefinementConfig(
            categories=[
                TaxonomyCategoryConfig(name="electronic_music", description="Electronic music."),
                TaxonomyCategoryConfig(name="metal_music", description="Metal music."),
            ],
        ),
    )
