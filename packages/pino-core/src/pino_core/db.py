from __future__ import annotations

from importlib.resources import files

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

from pino_core.storage import DatabaseStore, normalize_database_url


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(files("pino_core").joinpath("migrations")))
    config.set_main_option("sqlalchemy.url", str(normalize_database_url(database_url)))
    config.attributes["database_url"] = database_url
    return config


def upgrade_database(
    database_url: str,
    revision: str = "head",
    *,
    engine: Engine | None = None,
) -> None:
    command.upgrade(_engine_config(database_url, engine=engine), revision)


def current_database_revision(database_url: str) -> None:
    command.current(_engine_config(database_url), verbose=True)


def require_current_schema(engine: Engine) -> None:
    """Check schema version without performing DDL (production API startup)."""
    script = ScriptDirectory.from_config(
        alembic_config(engine.url.render_as_string(hide_password=False))
    )
    with engine.connect() as connection:
        actual = set(MigrationContext.configure(connection).get_current_heads())
    if actual != set(script.get_heads()):
        raise RuntimeError(
            "Database schema is not current; run pino db upgrade before starting the API"
        )


def show_migration_history(database_url: str) -> None:
    command.history(alembic_config(database_url), verbose=True)


def _engine_config(database_url: str, *, engine: Engine | None = None) -> Config:
    config = alembic_config(database_url)
    config.attributes["connection"] = (
        engine if engine is not None else DatabaseStore(database_url).engine
    )
    return config
