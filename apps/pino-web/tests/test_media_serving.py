from fastapi.testclient import TestClient

from pino_core.config import MediaConfig, PinoConfig
from pino_core.storage import SQLiteStore
from pino_web.app import create_app


def test_api_projects_configured_image_urls_without_changing_stored_paths():
    from datetime import datetime, timezone
    from pino_core.models import Record, RecordImage, Refinement
    from pino_core.storage import EventQueryResult
    from pino_web.services.events import _to_event_items

    path = "a" * 64 + ".webp"
    record = Record(
        kind="event",
        source="test",
        text="cover",
        images=[RecordImage(path=path, source_url="https://origin.test/image")],
    )
    start = datetime(2026, 9, 9, tzinfo=timezone.utc)
    refinement = Refinement(
        record_id=record.id, content_kind="event", relevant_from=start, refiner="test"
    )
    item = _to_event_items(
        EventQueryResult(record=record, refinement=refinement, score=1),
        timezone.utc,
        window_start=start,
        window_end=start,
        media_public_url="https://cdn.example.com/covers/",
    )[0]
    assert item.images == [f"https://cdn.example.com/covers/{path}"]
    assert record.images[0].path == path


def test_development_media_is_opt_in_and_immutable(tmp_path):
    directory = tmp_path / "media"
    directory.mkdir()
    name = "a" * 64 + ".webp"
    (directory / name).write_bytes(b"test image")
    config = PinoConfig(media=MediaConfig(directory=directory, public_url="/media"))
    store = SQLiteStore(tmp_path / "test.sqlite")
    with TestClient(create_app(config=config, store=store)) as client:
        assert client.get(f"/media/{name}").status_code == 404
    with TestClient(create_app(config=config, store=store, serve_media=True)) as client:
        for _ in range(65):
            response = client.get(f"/media/{name}")
            assert response.status_code == 200
        assert response.content == b"test image"
        assert response.headers["content-type"] == "image/webp"
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert client.get("/media/%2e%2e/test.sqlite").status_code == 404


def test_custom_media_mount(tmp_path):
    config = PinoConfig(
        media=MediaConfig(directory=tmp_path / "media", public_url="https://cdn.example.com/covers")
    )
    store = SQLiteStore(tmp_path / "test.sqlite")
    app = create_app(config=config, store=store, serve_media=True)
    assert any(getattr(route, "path", None) == "/covers" for route in app.routes)
