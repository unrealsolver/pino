from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from pino_core.config import PinoConfig, RefinementConfig, StorageConfig, TaxonomyCategoryConfig
from pino_core.models import Record, Refinement
from pino_core.storage import SQLiteStore
from pino_web.app import create_app
from pino_web.deps import get_event_repository, get_event_service
from pino_web.repositories.events import EventRepository
from pino_web.routes.events import list_events
from pino_web.services.events import (
    EventFilters,
    EventQueryError,
    EventService,
    MAX_QUERY_DAYS,
    _resolve_window,
    _to_event_items,
    _validate_categories,
)


def test_app_registers_event_route_and_configured_store(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    app = create_app(config=_config(tmp_path), store=store)

    assert app.state.store is store
    assert any(route.path == "/api/events" for route in app.routes)


def test_events_endpoint_translates_service_query_error(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    service = EventService(config=_config(tmp_path), repository=EventRepository(store))
    with pytest.raises(HTTPException) as exc_info:
        list_events(service=service, category=["unknown"])

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "unknown category: unknown"


def test_event_dependency_providers_construct_service(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    repository = get_event_repository(store)
    service = get_event_service(_config(tmp_path), repository)

    assert isinstance(repository, EventRepository)
    assert repository.store is store
    assert isinstance(service, EventService)
    assert service.repository is repository


def test_event_filters_group_route_to_service_inputs() -> None:
    date_from = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)
    filters = EventFilters(
        date_from=date_from,
        categories=["social"],
        min_score=0.5,
        query="jam",
        limit=25,
    )

    assert filters.date_from is date_from
    assert filters.date_to is None
    assert filters.categories == ["social"]
    assert filters.min_score == 0.5
    assert filters.query == "jam"
    assert filters.limit == 25


def test_event_item_serializes_refinement_with_utc_time(tmp_path: Path) -> None:
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

    item = _to_event_items(
        result[0],
        timezone.utc,
        window_start=datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc),
    )[0]

    assert item.refinement_id == result[0].refinement.id
    assert item.occurrence_id.startswith(result[0].refinement.id)
    assert item.title == "Open synth jam"
    assert item.text == "A participatory synth event."
    assert item.matching_score == 0.8
    assert item.starts_at == datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
    assert item.relevant_from == datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)


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

    items = _to_event_items(
        result[0],
        timezone.utc,
        window_start=window_start,
        window_end=window_end,
    )

    assert len(items) == 32
    assert items[0].starts_at == window_start
    assert items[0].ends_at == datetime(2026, 6, 8, 0, 0, tzinfo=timezone.utc)
    assert items[-1].starts_at == datetime(2026, 7, 8, 0, 0, tzinfo=timezone.utc)
    assert items[-1].ends_at == window_end
    assert items[0].relevant_from == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert items[0].relevant_to == datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)


def test_unscheduled_multiday_projection_outputs_utc_for_local_days(tmp_path: Path) -> None:
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
    local_timezone = ZoneInfo("Europe/Vilnius")
    window_start = datetime(2026, 6, 7, 0, 0, tzinfo=local_timezone)
    window_end = datetime(2026, 6, 9, 0, 0, tzinfo=local_timezone)
    result = store.query_events(
        window_start=window_start.astimezone(timezone.utc),
        window_end=window_end.astimezone(timezone.utc),
    )

    items = _to_event_items(
        result[0],
        local_timezone,
        window_start=window_start.astimezone(timezone.utc),
        window_end=window_end.astimezone(timezone.utc),
    )

    assert len(items) == 3
    assert items[0].starts_at == datetime(2026, 6, 6, 21, 0, tzinfo=timezone.utc)
    assert items[0].ends_at == datetime(2026, 6, 7, 21, 0, tzinfo=timezone.utc)
    assert items[1].starts_at == datetime(2026, 6, 7, 21, 0, tzinfo=timezone.utc)
    assert items[1].ends_at == datetime(2026, 6, 8, 21, 0, tzinfo=timezone.utc)
    assert items[2].starts_at == datetime(2026, 6, 8, 21, 0, tzinfo=timezone.utc)
    assert items[2].ends_at == datetime(2026, 6, 8, 21, 0, tzinfo=timezone.utc)


def test_event_items_expand_explicit_occurrence_schedule(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="event", source="test", title="Museum exhibition", text="Open daily.")
    )
    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 6, 30, 21, 0, tzinfo=timezone.utc),
                schedule={
                    "version": 1,
                    "timezone": "Europe/Vilnius",
                    "kind": "occurrences",
                    "occurrences": [
                        {"start": "2026-06-07T10:00", "end": "2026-06-07T18:00"},
                        {"start": "2026-06-08T10:00", "end": "2026-06-08T21:00"},
                    ],
                },
                refiner="test",
            ),
        ],
    )
    window_start = datetime(2026, 6, 7, 0, 0, tzinfo=ZoneInfo("Europe/Vilnius"))
    window_end = datetime(2026, 6, 8, 23, 59, tzinfo=ZoneInfo("Europe/Vilnius"))
    result = store.query_events(
        window_start=window_start.astimezone(timezone.utc),
        window_end=window_end.astimezone(timezone.utc),
    )

    items = _to_event_items(
        result[0],
        ZoneInfo("Europe/Vilnius"),
        window_start=window_start,
        window_end=window_end,
    )

    assert [item.starts_at for item in items] == [
        datetime(2026, 6, 7, 7, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 8, 7, 0, tzinfo=timezone.utc),
    ]
    assert [item.ends_at for item in items] == [
        datetime(2026, 6, 7, 15, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 8, 18, 0, tzinfo=timezone.utc),
    ]


def test_event_items_expand_weekly_recurrence_schedule(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="event", source="test", title="Tuesday meetup", text="Each Tuesday.")
    )
    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind="event",
                relevant_from=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
                relevant_to=datetime(2026, 6, 30, 21, 0, tzinfo=timezone.utc),
                schedule={
                    "version": 1,
                    "timezone": "Europe/Vilnius",
                    "kind": "recurrence",
                    "frequency": "weekly",
                    "from": "2026-06-01",
                    "until": "2026-06-30",
                    "rules": [
                        {"weekdays": ["tuesday"], "start": "19:00", "end": None}
                    ],
                },
                refiner="test",
            ),
        ],
    )
    window_start = datetime(2026, 6, 7, 0, 0, tzinfo=ZoneInfo("Europe/Vilnius"))
    window_end = datetime(2026, 6, 15, 23, 59, tzinfo=ZoneInfo("Europe/Vilnius"))
    result = store.query_events(
        window_start=window_start.astimezone(timezone.utc),
        window_end=window_end.astimezone(timezone.utc),
    )

    items = _to_event_items(
        result[0],
        ZoneInfo("Europe/Vilnius"),
        window_start=window_start,
        window_end=window_end,
    )

    assert len(items) == 1
    assert items[0].starts_at == datetime(2026, 6, 9, 16, 0, tzinfo=timezone.utc)
    assert items[0].ends_at is None


def test_scheduled_event_without_window_match_does_not_fallback_to_envelope(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="event", source="test", title="Tuesday meetup", text="Each Tuesday.")
    )
    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind="event",
                schedule={
                    "version": 1,
                    "timezone": "Europe/Vilnius",
                    "kind": "recurrence",
                    "frequency": "weekly",
                    "from": "2026-06-01",
                    "until": "2026-06-30",
                    "rules": [
                        {"weekdays": ["tuesday"], "start": "19:00", "end": None}
                    ],
                },
                refiner="test",
            ),
        ],
    )
    window_start = datetime(2026, 6, 10, 0, 0, tzinfo=ZoneInfo("Europe/Vilnius"))
    window_end = datetime(2026, 6, 10, 23, 59, tzinfo=ZoneInfo("Europe/Vilnius"))
    result = store.query_events(
        window_start=window_start.astimezone(timezone.utc),
        window_end=window_end.astimezone(timezone.utc),
    )

    assert result == []


def test_events_endpoint_rejects_unknown_category(tmp_path: Path) -> None:
    known = [category.name for category in _config(tmp_path).refinement.categories]
    with pytest.raises(EventQueryError) as exc_info:
        _validate_categories(["unknown"], known)

    assert known == ["electronic_music", "metal_music"]
    assert str(exc_info.value) == "unknown category: unknown"


def test_event_repository_delegates_to_store_query_events() -> None:
    calls: list[dict[str, object]] = []

    class Store:
        def query_events(self, **kwargs: object) -> list[str]:
            calls.append(kwargs)
            return ["event"]

    window_start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 6, 2, 0, 0, tzinfo=timezone.utc)

    result = EventRepository(Store()).query_events(
        window_start=window_start,
        window_end=window_end,
        categories=["electronic_music"],
        min_score=0.4,
        text_query="jam",
        limit=25,
    )

    assert result == ["event"]
    assert calls == [
        {
            "window_start": window_start,
            "window_end": window_end,
            "categories": ["electronic_music"],
            "min_score": 0.4,
            "text_query": "jam",
            "limit": 25,
        }
    ]


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
