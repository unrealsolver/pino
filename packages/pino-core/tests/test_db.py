from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from pino_core import db
from pino_core.db import alembic_config, upgrade_database


def test_alembic_config_points_at_packaged_migrations(tmp_path: Path) -> None:
    config = alembic_config(f"sqlite:///{tmp_path / 'pino.sqlite'}")

    assert config.get_main_option("script_location").endswith("pino_core/migrations")
    assert config.attributes["database_url"].startswith("sqlite:///")


def test_upgrade_uses_database_store_engine(monkeypatch) -> None:
    calls: list[str] = []
    command_calls: list[object] = []

    class FakeStore:
        def __init__(self, database_url: str) -> None:
            calls.append(database_url)
            self.engine = object()

    monkeypatch.setattr(db, "DatabaseStore", FakeStore)
    monkeypatch.setattr(db.command, "upgrade", lambda config, revision: command_calls.append(config))

    upgrade_database("postgresql://pino@example.test/pino", "head")

    assert calls == ["postgresql://pino@example.test/pino"]
    assert len(command_calls) == 1
    assert command_calls[0].attributes["connection"] is not None


def test_alembic_ini_does_not_point_direct_commands_at_sqlite() -> None:
    assert "sqlalchemy.url =\n" in Path("alembic.ini").read_text()


def test_upgrade_adds_schedule_to_legacy_refinements_table(tmp_path: Path) -> None:
    database_path = tmp_path / "pino.sqlite"
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(database_url, future=True)
    legacy_metadata = MetaData()
    Table(
        "refinements",
        legacy_metadata,
        Column("id", String, primary_key=True),
        Column("record_id", String, nullable=False),
        Column("item_index", Integer, nullable=False),
    )
    legacy_metadata.create_all(engine)

    upgrade_database(database_url)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("refinements")}
    assert "schedule" in columns
    assert set(inspector.get_table_names()) == {
        "active_memory",
        "alembic_version",
        "chat_messages",
        "llm_usage_events",
        "records",
        "refinements",
        "source_cursors",
    }


def test_upgrade_repairs_database_stamped_before_schedule_column(tmp_path: Path) -> None:
    database_path = tmp_path / "pino.sqlite"
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(database_url, future=True)
    legacy_metadata = MetaData()
    Table(
        "refinements",
        legacy_metadata,
        Column("id", String, primary_key=True),
        Column("record_id", String, nullable=False),
        Column("item_index", Integer, nullable=False),
    )
    Table(
        "alembic_version",
        legacy_metadata,
        Column("version_num", String, primary_key=True),
    )
    legacy_metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "20260611_0154"},
        )

    upgrade_database(database_url)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("refinements")}
    with engine.begin() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert "schedule" in columns
    assert revision == "20260830_0323"


def test_upgrade_adds_llm_usage_events_table(tmp_path: Path) -> None:
    database_path = tmp_path / "pino.sqlite"
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(database_url, future=True)
    legacy_metadata = MetaData()
    Table(
        "alembic_version",
        legacy_metadata,
        Column("version_num", String, primary_key=True),
    )
    legacy_metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "20260611_0241"},
        )

    upgrade_database(database_url)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("llm_usage_events")}
    with engine.begin() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert {
        "id",
        "created_at",
        "provider",
        "model",
        "operation",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "duration_ms",
    } <= columns
    assert revision == "20260830_0323"


def test_upgrade_bootstraps_empty_sqlite_without_schedule_index(tmp_path: Path) -> None:
    database_path = tmp_path / "pino.sqlite"
    database_url = f"sqlite:///{database_path}"

    upgrade_database(database_url)

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)
    with engine.begin() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert set(inspector.get_table_names()) == {
        "active_memory",
        "alembic_version",
        "chat_messages",
        "llm_usage_events",
        "records",
        "refinements",
        "source_cursors",
    }
    assert "schedule" in {
        column["name"] for column in inspector.get_columns("refinements")
    }
    assert "fingerprint" in {column["name"] for column in inspector.get_columns("records")}
    assert revision == "20260830_0323"


def test_schedule_search_index_migration_backfills_legacy_schedule() -> None:
    migration = import_module(
        "pino_core.migrations.versions.20260830_0323_add_schedule_search_index"
    )
    inserted: list[dict[str, object]] = []

    class Bind:
        def execute(self, _statement: object, parameters: dict[str, object] | None = None):
            if parameters is not None:
                inserted.append(parameters)
                return None
            rows = [
                {
                    "id": "refinement",
                    "schedule": {
                        "timezone": "Europe/Vilnius",
                        "kind": "recurrence",
                        "rules": [
                            {"days": ["TU"], "start": "18:00", "end": "19:30"}
                        ],
                    },
                    "relevant_from": datetime(2026, 6, 1, tzinfo=timezone.utc),
                    "relevant_to": datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc),
                }
            ]
            return SimpleNamespace(mappings=lambda: rows)

    migration._backfill(Bind())

    assert inserted == [
        {
            "refinement_id": "refinement",
            "timezone": "Europe/Vilnius",
            "weekly_pattern": "{[2520,2611)}",
        }
    ]
