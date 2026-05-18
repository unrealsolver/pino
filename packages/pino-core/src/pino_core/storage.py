from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
)
from sqlalchemy.orm import Session

from pino_core.models import Artifact, ChatMessage, MemoryEntry, Record

metadata = MetaData()

records_table = Table(
    "records",
    metadata,
    Column("id", String, primary_key=True),
    Column("kind", String, nullable=False),
    Column("source", String, nullable=False),
    Column("title", String),
    Column("text", Text, nullable=False),
    Column("url", String),
    Column("observed_at", DateTime(timezone=True)),
    Column("captured_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("provenance", JSON, nullable=False),
)

artifacts_table = Table(
    "artifacts",
    metadata,
    Column("id", String, primary_key=True),
    Column("kind", String, nullable=False),
    Column("title", String, nullable=False),
    Column("body", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("record_ids", JSON, nullable=False),
    Column("payload", JSON, nullable=False),
)

active_memory_table = Table(
    "active_memory",
    metadata,
    Column("id", String, primary_key=True),
    Column("content", Text, nullable=False),
    Column("tags", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
)

chat_messages_table = Table(
    "chat_messages",
    metadata,
    Column("id", String, primary_key=True),
    Column("role", String, nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
)


class SQLiteStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.path}", future=True)

    def init_schema(self) -> None:
        metadata.create_all(self.engine)

    def add_record(self, record: Record) -> None:
        self._insert_model(records_table, record)

    def list_records(self, limit: int = 50) -> list[Record]:
        rows = self._select_latest(records_table, records_table.c.captured_at, limit)
        return [Record.model_validate(dict(row)) for row in rows]

    def add_artifact(self, artifact: Artifact) -> None:
        self._insert_model(artifacts_table, artifact)

    def list_artifacts(self, limit: int = 20) -> list[Artifact]:
        rows = self._select_latest(artifacts_table, artifacts_table.c.created_at, limit)
        return [Artifact.model_validate(dict(row)) for row in rows]

    def add_memory(self, memory: MemoryEntry) -> None:
        self._insert_model(active_memory_table, memory)

    def list_memory(self, limit: int = 50) -> list[MemoryEntry]:
        rows = self._select_latest(active_memory_table, active_memory_table.c.created_at, limit)
        return [MemoryEntry.model_validate(dict(row)) for row in rows]

    def add_chat_message(self, message: ChatMessage) -> None:
        self._insert_model(chat_messages_table, message)

    def list_chat_messages(self, limit: int = 50) -> list[ChatMessage]:
        rows = self._select_latest(chat_messages_table, chat_messages_table.c.created_at, limit)
        return [ChatMessage.model_validate(dict(row)) for row in rows]

    def clear_chat_messages(self) -> int:
        with Session(self.engine) as session:
            result = session.execute(delete(chat_messages_table))
            session.commit()
            return result.rowcount or 0

    def _insert_model(self, table: Table, model: Any) -> None:
        with Session(self.engine) as session:
            session.execute(insert(table).values(**model.model_dump(mode="python")))
            session.commit()

    def _select_latest(self, table: Table, order_column: Any, limit: int) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            result = session.execute(select(table).order_by(order_column.desc()).limit(limit))
            return [dict(row._mapping) for row in result]
