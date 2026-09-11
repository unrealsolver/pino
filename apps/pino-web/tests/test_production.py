import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pino_core.config import PinoConfig
from pino_core.storage import SQLiteStore
from pino_web.app import create_app
from pino_web.middleware import RateLimitMiddleware
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError


@pytest.mark.parametrize("path", ["/api/slow", "/api/health", "/api"])
def test_api_deadline_returns_safe_504(tmp_path, monkeypatch, path):
    import asyncio

    from pino_web import app as app_module

    assert app_module.API_TIMEOUT_SECONDS == 10
    monkeypatch.setattr(app_module, "API_TIMEOUT_SECONDS", 0.01)
    app = create_app(config=PinoConfig(), store=SQLiteStore(tmp_path / "db.sqlite"))
    # Replace health so its readiness exemption cannot accidentally exempt the deadline.
    app.router.routes[:] = [route for route in app.router.routes if route.path != path]

    @app.get(path)
    async def slow():
        await asyncio.sleep(0.05)
        return {"late": True}

    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 504
        assert response.json() == {"detail": "Request timed out"}
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert client.get("/api/events").status_code == 200


def test_non_api_routes_are_not_timed_out(tmp_path, monkeypatch):
    import asyncio

    monkeypatch.setattr("pino_web.app.API_TIMEOUT_SECONDS", 0.001)
    app = create_app(config=PinoConfig(), store=SQLiteStore(tmp_path / "db.sqlite"))

    @app.get("/outside")
    async def outside():
        await asyncio.sleep(0.01)
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/outside").json() == {"ok": True}


def test_deadline_sends_response_before_blocked_sync_handler_finishes(tmp_path, monkeypatch):
    import asyncio
    from threading import Event

    release = Event()
    finished = Event()
    monkeypatch.setattr("pino_web.app.API_TIMEOUT_SECONDS", 0.05)
    app = create_app(config=PinoConfig(), store=SQLiteStore(tmp_path / "db.sqlite"))

    @app.get("/api/blocked")
    def blocked():
        release.wait(timeout=2)
        finished.set()
        return {"late": True}

    messages = []

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.start":
            assert message["status"] == 504
            assert not finished.is_set()
            release.set()

    async def receive():
        await asyncio.sleep(3)
        return {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/blocked",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "client": ("127.0.0.1", 1234),
        "server": ("localhost", 80),
    }
    try:
        asyncio.run(app(scope, receive, send))
    finally:
        release.set()
    assert any(message["type"] == "http.response.body" for message in messages)


@pytest.mark.parametrize(
    "params,status",
    [
        ({"limit": "501"}, 422),
        ({"limit": "-1"}, 422),
        ({"q": "x" * 201}, 422),
        ({"min_score": "nan"}, 422),
        ({"category": ["x"] * 65}, 422),
        ({"date_from": "not-a-date"}, 422),
        ({"date_from": "9999-12-31T00:00:00Z"}, 400),
        ({"date_from": "0001-01-01T00:00:00Z", "date_to": "0001-01-02T00:00:00Z"}, 400),
        ({"date_from": "2026-01-02T00:00:00Z", "date_to": "2026-01-01T00:00:00Z"}, 400),
        ({"date_from": "2026-01-01T00:00:00Z", "date_to": "2027-01-06T00:00:01Z"}, 400),
    ],
)
def test_invalid_queries_never_reach_database(tmp_path, monkeypatch, params, status):
    store = SQLiteStore(tmp_path / "db.sqlite")
    app = create_app(config=PinoConfig(), store=store)
    monkeypatch.setattr(store, "query_events", lambda **kwargs: pytest.fail("invalid query hit DB"))
    with TestClient(app) as client:
        response = client.get("/api/events", params=params)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_events_database_failure_is_safe_and_recovery_works(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "db.sqlite")
    app = create_app(config=PinoConfig(), store=store)
    with TestClient(app) as client:
        with monkeypatch.context() as patch:

            def fail_query(**kwargs):
                raise OperationalError("secret SQL", {}, Exception("secret credentials"))

            patch.setattr(store, "query_events", fail_query)
            response = client.get("/api/events")
            assert response.status_code == 503
            assert response.json() == {"detail": "Database unavailable"}
            assert response.headers["cache-control"] == "no-store"
        assert client.get("/api/events").status_code == 200


def test_http_limiter_counts_invalid_requests_and_ignores_spoofed_forwarding(tmp_path):
    app = create_app(config=PinoConfig(), store=SQLiteStore(tmp_path / "db.sqlite"))
    with TestClient(app) as client:
        for i in range(60):
            assert (
                client.get(
                    "/api/events?limit=0",
                    headers={
                        "X-Forwarded-For": f"192.0.2.{i}",
                    },
                ).status_code
                == 422
            )
        response = client.get("/api/events")
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/api/health").status_code == 200


def test_production_startup_never_migrates(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "db.sqlite")
    with pytest.raises(RuntimeError, match="pino db upgrade"):
        create_app(config=PinoConfig(), store=store, migrate=False)
    assert inspect(store.engine).get_table_names() == []
    store.init_schema()
    monkeypatch.setattr(store, "init_schema", lambda: pytest.fail("production must not migrate"))
    with TestClient(create_app(config=PinoConfig(), store=store, migrate=False)) as client:
        assert client.get("/api/health").json() == {"status": "ok"}

        def fail_connect():
            raise OperationalError("secret connection details", {}, Exception("offline"))

        monkeypatch.setattr(store.engine, "connect", fail_connect)
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
        assert response.headers["cache-control"] == "no-store"


def test_limiter_expires_and_bounds_clients_and_exempts_health(monkeypatch):
    import asyncio

    from starlette.requests import Request
    from starlette.responses import Response

    clock = [0.0]
    monkeypatch.setattr("pino_web.middleware.monotonic", lambda: clock[0])
    limiter = RateLimitMiddleware(FastAPI(), limit=1, window_seconds=60, max_clients=2)

    async def respond(request):
        return Response(status_code=200)

    def call(host, path="/api/events"):
        request = Request({"type": "http", "path": path, "client": (host, 1), "headers": []})
        return asyncio.run(limiter.dispatch(request, respond))

    assert call("one").status_code == 200
    rejected = call("one")
    assert rejected.status_code == 429
    assert rejected.headers["retry-after"] == "60"
    assert call("one", "/api/health").status_code == 200
    call("two")
    call("three")
    assert len(limiter._requests) == 2
    clock[0] = 61
    assert call("four").status_code == 200
    assert list(limiter._requests) == ["four"]
