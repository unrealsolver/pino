from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Engine, engine_from_config, pool
from sqlalchemy.engine import Connection

from pino_core.config import load_config
from pino_core.storage import metadata, normalize_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def run_migrations_offline() -> None:
    database_url = _database_url()
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configured_connection = config.attributes.get("connection")
    if configured_connection is not None:
        _run_migrations_with_configured_connection(configured_connection)
        return

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


def _run_migrations_with_configured_connection(connection_or_engine: object) -> None:
    if isinstance(connection_or_engine, Connection):
        _configure_and_run(connection_or_engine)
        return
    if isinstance(connection_or_engine, Engine):
        with connection_or_engine.connect() as connection:
            _configure_and_run(connection)
        return
    raise TypeError("Alembic connection attribute must be a SQLAlchemy Connection or Engine")


def _configure_and_run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


def _database_url() -> str:
    configured = config.attributes.get("database_url")
    if isinstance(configured, str) and configured:
        return str(normalize_database_url(configured))
    x_args = context.get_x_argument(as_dictionary=True)
    x_url = x_args.get("database_url")
    if x_url:
        return str(normalize_database_url(x_url))
    return str(normalize_database_url(load_config().storage.database_url()))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
