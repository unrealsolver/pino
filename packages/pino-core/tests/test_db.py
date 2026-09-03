from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from sqlalchemy import MetaData, create_engine, inspect, text

from pino_core import db
from pino_core.db import alembic_config, upgrade_database
from pino_core.storage import metadata


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
    monkeypatch.setattr(
        db.command, "upgrade", lambda config, revision: command_calls.append(config)
    )

    upgrade_database("postgresql://pino@example.test/pino", "head")

    assert calls == ["postgresql://pino@example.test/pino"]
    assert len(command_calls) == 1
    assert command_calls[0].attributes["connection"] is not None


def test_alembic_ini_does_not_point_direct_commands_at_sqlite() -> None:
    assert "sqlalchemy.url =\n" in Path("alembic.ini").read_text()


def test_upgrade_bootstraps_current_sqlite_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "pino.sqlite"
    database_url = f"sqlite:///{database_path}"

    upgrade_database(database_url)
    upgrade_database(database_url)

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {*metadata.tables, "alembic_version"}
    for table_name, table in metadata.tables.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        assert actual_columns == set(table.columns.keys())
    with engine.begin() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert revision == "0001"
    assert "refinement_schedule_index" not in inspector.get_table_names()


def test_upgrade_preserves_retained_memory_and_usage_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "pino.sqlite"
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(database_url, future=True)
    retained_metadata = MetaData()
    active_memory = metadata.tables["active_memory"].to_metadata(retained_metadata)
    llm_usage_events = metadata.tables["llm_usage_events"].to_metadata(retained_metadata)
    retained_metadata.create_all(engine)
    created_at = datetime(2026, 8, 31, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            active_memory.insert().values(
                id="memory-1",
                content="Keep me",
                tags=[],
                created_at=created_at,
                updated_at=created_at,
                payload={},
            )
        )
        connection.execute(
            llm_usage_events.insert().values(
                id="usage-1",
                created_at=created_at,
                provider="test",
                model="test",
                operation="test",
                input_tokens=1,
                output_tokens=1,
                cached_input_tokens=0,
                duration_ms=1,
            )
        )

    upgrade_database(database_url)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT content FROM active_memory")).scalar_one() == (
            "Keep me"
        )
        assert connection.execute(text("SELECT provider FROM llm_usage_events")).scalar_one() == (
            "test"
        )


def test_postgresql_baseline_contains_schedule_index(capsys) -> None:
    config = alembic_config("postgresql://pino@example.test/pino")

    command.upgrade(config, "head", sql=True)

    sql = capsys.readouterr().out.lower()
    assert "create table if not exists active_memory" in sql
    assert "create table if not exists llm_usage_events" in sql
    assert "create table refinement_schedule_index" in sql
    assert "weekly_pattern int4multirange" in sql
    assert "using gist" in sql
    assert "add column published_at" in sql
    assert "payload ->> 'posted_at_utc'" in sql
    assert "create index ix_records_published_at" in sql


def test_publication_migration_backfills_sqlite_payload(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'pino.sqlite'}"
    upgrade_database(database_url, "0000")
    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO records (
                    id, kind, source, fingerprint, text, captured_at, payload, provenance
                ) VALUES (
                    'record-1', 'telegram_message', 'afisha', 'fingerprint', 'Post',
                    '2026-08-18 12:00:00',
                    '{"posted_at_utc":"2026-08-17T09:30:00+00:00"}', '{}'
                )
                """
            )
        )

    upgrade_database(database_url)

    with engine.begin() as connection:
        published_at = connection.execute(
            text("SELECT published_at FROM records WHERE id = 'record-1'")
        ).scalar_one()
    assert published_at == "2026-08-17T09:30:00+00:00"
