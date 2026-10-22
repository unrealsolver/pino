from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pino_core import cities as cities_module
from pino_core.cities import City
from pino_core.config import PinoConfig
from pino_core.models import Record, Refinement
from pino_core.storage import SQLiteStore
from pino_web.app import create_app
from pino_web.repositories.events import EventRepository
from pino_web.services.events import EventFilters, EventService

WINDOW = {
    "date_from": "2026-06-10T00:00:00Z",
    "date_to": "2026-06-10T23:59:59Z",
}


def test_unscoped_events_keep_all_records_and_add_city_metadata(tmp_path: Path) -> None:
    store = _store(tmp_path)
    vilnius = _event(store, "lt/vilnius", "Vilnius", "2026-06-10T10:00:00Z")
    _event(store, "fixture/other", "Other", "2026-06-10T11:00:00Z")
    _event(store, None, "Unassigned", "2026-06-10T12:00:00Z")

    with TestClient(create_app(config=PinoConfig(), store=store)) as client:
        response = client.get("/api/events", params=WINDOW)

    assert response.status_code == 200
    payload = response.json()
    assert payload["timezone"] == "Europe/Vilnius"
    assert {event["title"] for event in payload["events"]} == {
        "Vilnius",
        "Other",
        "Unassigned",
    }
    assert next(
        event["city_id"] for event in payload["events"] if event["refinement_id"] == vilnius
    ) == "lt/vilnius"
    assert {event["city_id"] for event in payload["events"]} == {
        "lt/vilnius",
        "fixture/other",
        None,
    }


def test_selected_city_filters_before_projection_and_excludes_unassigned(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    vilnius = _event(store, "lt/vilnius", "Vilnius", "2026-06-10T10:00:00Z")
    _event(store, "fixture/other", "Other", "2026-06-10T11:00:00Z")
    _event(store, None, "Unassigned", "2026-06-10T12:00:00Z")

    with TestClient(create_app(config=PinoConfig(), store=store)) as client:
        response = client.get("/api/events", params={**WINDOW, "city": "  LT/Vilnius  "})

    assert response.status_code == 200
    events = response.json()["events"]
    assert [event["refinement_id"] for event in events] == [vilnius]
    assert events[0]["city_id"] == "lt/vilnius"
    assert response.json()["timezone"] == "Europe/Vilnius"


def test_city_metadata_endpoint_returns_public_entries(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with TestClient(create_app(config=PinoConfig(), store=store)) as client:
        response = client.get("/api/cities")

    assert response.status_code == 200
    assert response.json() == {
        "cities": [
            {
                "id": "lt/vilnius",
                "country_code": "lt",
                "slug": "vilnius",
                "name": "Vilnius",
                "timezone": "Europe/Vilnius",
            }
        ]
    }


def test_city_timezone_resolves_naive_bounds_and_projection_without_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cities_module,
        "CITY_REGISTRY",
        {
            **cities_module.CITY_REGISTRY,
            "fixture/ny": City(
                id="fixture/ny",
                country_code="zz",
                slug="ny",
                name="New York",
                timezone="America/New_York",
            ),
        },
    )
    store = _store(tmp_path)
    _event(
        store,
        "fixture/ny",
        "Early New York",
        "2026-06-10T01:00:00Z",
        "2026-06-10T02:00:00Z",
    )
    multiday = _event(
        store,
        "fixture/ny",
        "New York day",
        "2026-06-10T04:00:00Z",
        "2026-06-11T03:59:00Z",
    )
    _event(store, "lt/vilnius", "Vilnius", "2026-06-10T10:00:00Z")

    app = create_app(config=PinoConfig(), store=store)
    with TestClient(app) as client:
        city_response = client.get(
            "/api/events",
            params={
                "city": "fixture/ny",
                "date_from": "2026-06-10T00:00:00",
                "date_to": "2026-06-10T23:59:59",
            },
        )
        explicit_response = client.get(
            "/api/events",
            params={
                "city": "fixture/ny",
                "date_from": "2026-06-09T21:00:00-04:00",
                "date_to": "2026-06-09T22:00:00-04:00",
            },
        )
        unscoped_response = client.get("/api/events", params=WINDOW)

    assert city_response.status_code == 200
    city_payload = city_response.json()
    assert city_payload["timezone"] == "America/New_York"
    assert [event["refinement_id"] for event in city_payload["events"]] == [multiday]
    assert _parse(city_payload["events"][0]["starts_at"]) == datetime(
        2026, 6, 10, 4, 0, tzinfo=timezone.utc
    )
    assert _parse(city_payload["events"][0]["ends_at"]) == datetime(
        2026, 6, 11, 3, 59, tzinfo=timezone.utc
    )

    assert explicit_response.status_code == 200
    explicit_payload = explicit_response.json()
    assert explicit_payload["timezone"] == "America/New_York"
    assert [event["title"] for event in explicit_payload["events"]] == ["Early New York"]
    assert _parse(explicit_payload["events"][0]["starts_at"]) == datetime(
        2026, 6, 10, 1, 0, tzinfo=timezone.utc
    )

    assert unscoped_response.status_code == 200
    unscoped_payload = unscoped_response.json()
    assert unscoped_payload["timezone"] == "Europe/Vilnius"
    assert {event["city_id"] for event in unscoped_payload["events"]} == {
        "fixture/ny",
        "lt/vilnius",
    }


def test_injected_unscoped_timezone_is_reflected_in_response_metadata(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _event(store, "lt/vilnius", "Vilnius", "2026-06-10T10:00:00Z")
    service = EventService(
        config=PinoConfig(),
        repository=EventRepository(store),
        local_timezone=ZoneInfo("America/New_York"),
    )

    response = service.list_events(
        filters=EventFilters(
            date_from=datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc),
            date_to=datetime(2026, 6, 10, 23, 59, tzinfo=timezone.utc),
        )
    )

    assert response.timezone == "America/New_York"


def test_city_timezone_does_not_leak_between_service_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cities_module,
        "CITY_REGISTRY",
        {
            **cities_module.CITY_REGISTRY,
            "fixture/ny": City(
                id="fixture/ny",
                country_code="zz",
                slug="ny",
                name="New York",
                timezone="America/New_York",
            ),
        },
    )
    store = _store(tmp_path)
    _event(store, "fixture/ny", "New York", "2026-06-10T10:00:00Z")
    _event(store, "lt/vilnius", "Vilnius", "2026-06-10T11:00:00Z")
    service = EventService(config=PinoConfig(), repository=EventRepository(store))
    window = EventFilters(
        date_from=datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc),
        date_to=datetime(2026, 6, 10, 23, 59, tzinfo=timezone.utc),
    )

    scoped = service.list_events(
        filters=EventFilters(
            date_from=window.date_from,
            date_to=window.date_to,
            city="fixture/ny",
        )
    )
    unscoped = service.list_events(filters=window)

    assert scoped.timezone == "America/New_York"
    assert [event.city_id for event in scoped.events] == ["fixture/ny"]
    assert unscoped.timezone == "Europe/Vilnius"
    assert {event.city_id for event in unscoped.events} == {"fixture/ny", "lt/vilnius"}


def test_selected_city_missing_bounds_use_local_default_day_at_utc_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cities_module,
        "CITY_REGISTRY",
        {
            **cities_module.CITY_REGISTRY,
            "fixture/ny": City(
                id="fixture/ny",
                country_code="zz",
                slug="ny",
                name="New York",
                timezone="America/New_York",
            ),
        },
    )

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 6, 11, 2, 30, tzinfo=timezone.utc)
            return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)

    monkeypatch.setattr("pino_web.services.events.datetime", FixedDateTime)
    assert (
        datetime(2026, 6, 11, 2, 30, tzinfo=timezone.utc)
        .astimezone(ZoneInfo("America/New_York"))
        .date()
        .isoformat()
        == "2026-06-10"
    )
    store = _store(tmp_path)
    _event(store, "fixture/ny", "Before local midnight", "2026-06-10T02:00:00Z")
    _event(store, "fixture/ny", "Local day", "2026-06-10T04:30:00Z")
    service = EventService(config=PinoConfig(), repository=EventRepository(store))

    response = service.list_events(filters=EventFilters(city="fixture/ny"))

    assert response.timezone == "America/New_York"
    assert [event.title for event in response.events] == ["Local day"]
    assert response.events[0].starts_at == datetime(2026, 6, 10, 4, 30, tzinfo=timezone.utc)


def test_schedule_timezone_keeps_occurrence_instant_when_city_timezone_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cities_module,
        "CITY_REGISTRY",
        {
            **cities_module.CITY_REGISTRY,
            "fixture/ny": City(
                id="fixture/ny",
                country_code="zz",
                slug="ny",
                name="New York",
                timezone="America/New_York",
            ),
        },
    )
    store = _store(tmp_path)
    inserted = store.add_record(
        Record(kind="event", source="test", title="Vilnius schedule", text="Vilnius schedule")
    )
    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind="event",
                summary="Vilnius schedule",
                city_id="fixture/ny",
                schedule={
                    "version": 1,
                    "timezone": "Europe/Vilnius",
                    "kind": "occurrences",
                    "occurrences": [
                        {"start": "2026-06-10T19:00", "end": "2026-06-10T21:00"}
                    ],
                },
                refiner="test",
            )
        ],
    )
    service = EventService(config=PinoConfig(), repository=EventRepository(store))

    response = service.list_events(
        filters=EventFilters(
            date_from=datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc),
            date_to=datetime(2026, 6, 11, 0, 0, tzinfo=timezone.utc),
            city="fixture/ny",
        )
    )

    assert response.timezone == "America/New_York"
    assert [(event.title, event.starts_at, event.ends_at) for event in response.events] == [
        (
            "Vilnius schedule",
            datetime(2026, 6, 10, 16, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 10, 18, 0, tzinfo=timezone.utc),
        )
    ]


def _store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    return store


def _event(
    store: SQLiteStore,
    city_id: str | None,
    title: str,
    relevant_from: str,
    relevant_to: str | None = None,
) -> str:
    inserted = store.add_record(
        Record(kind="event", source="test", title=title, text=f"{title} text")
    )
    store.replace_refinements(
        inserted.record.id,
        [
            Refinement(
                record_id=inserted.record.id,
                content_kind="event",
                summary=title,
                relevant_from=_parse(relevant_from),
                relevant_to=_parse(relevant_to),
                city_id=city_id,
                refiner="test",
            )
        ],
    )
    return store.list_refinements(inserted.record.id)[0].id


def _parse(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
