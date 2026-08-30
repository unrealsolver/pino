from __future__ import annotations

from importlib.resources import files

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from pino_core.storage import DatabaseStore
from pino_core.storage import normalize_database_url


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


def show_migration_history(database_url: str) -> None:
    command.history(alembic_config(database_url), verbose=True)


def _engine_config(database_url: str, *, engine: Engine | None = None) -> Config:
    config = alembic_config(database_url)
    config.attributes["connection"] = (
        engine if engine is not None else DatabaseStore(database_url).engine
    )
    return config
