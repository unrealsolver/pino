from __future__ import annotations

from pathlib import Path
from typing import Any
from dataclasses import dataclass

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    insert,
    select,
)
from sqlalchemy.orm import Session

from pino_core.models import Artifact, ChatMessage, Evaluation, MemoryEntry, Record

metadata = MetaData()

records_table = Table(
    "records",
    metadata,
    Column("id", String, primary_key=True),
    Column("kind", String, nullable=False),
    Column("source", String, nullable=False),
    Column("external_id", String),
    Column("fingerprint", String, nullable=False),
    Column("title", String),
    Column("text", Text, nullable=False),
    Column("url", String),
    Column("relevant_from", DateTime(timezone=True)),
    Column("relevant_to", DateTime(timezone=True)),
    Column("captured_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("provenance", JSON, nullable=False),
    UniqueConstraint("fingerprint", name="uq_records_fingerprint"),
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

evaluations_table = Table(
    "evaluations",
    metadata,
    Column("id", String, primary_key=True),
    Column("record_id", String, nullable=False),
    Column("score", Float, nullable=False),
    Column("goal_matches", JSON, nullable=False),
    Column("language", String),
    Column("summary", Text),
    Column("reasons", JSON, nullable=False),
    Column("risks", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
    UniqueConstraint("record_id", name="uq_evaluations_record_id"),
)


@dataclass(frozen=True)
class InsertResult:
    record: Record
    inserted: bool


class SQLiteStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.path}", future=True)

    def init_schema(self) -> None:
        metadata.create_all(self.engine)
        self._migrate_records_table()

    def add_record(self, record: Record) -> InsertResult:
        record = record.with_fingerprint()
        with Session(self.engine) as session:
            existing = session.execute(
                select(records_table).where(records_table.c.fingerprint == record.fingerprint),
            ).first()
            if existing is not None:
                return InsertResult(record=Record.model_validate(dict(existing._mapping)), inserted=False)
            session.execute(insert(records_table).values(**record.model_dump(mode="python")))
            session.commit()
            return InsertResult(record=record, inserted=True)

    def list_records(self, limit: int = 50) -> list[Record]:
        rows = self._select_latest(records_table, records_table.c.captured_at, limit)
        return [Record.model_validate(dict(row)) for row in rows]

    def list_unevaluated_records(self, limit: int = 20) -> list[Record]:
        with Session(self.engine) as session:
            result = session.execute(
                select(records_table)
                .outerjoin(
                    evaluations_table,
                    records_table.c.id == evaluations_table.c.record_id,
                )
                .where(evaluations_table.c.record_id.is_(None))
                .order_by(records_table.c.captured_at.desc())
                .limit(limit),
            )
            return [Record.model_validate(dict(row._mapping)) for row in result]

    def list_records_with_evaluations(self, limit: int = 20) -> list[tuple[Record, Evaluation | None]]:
        with Session(self.engine) as session:
            result = session.execute(
                select(records_table, evaluations_table)
                .outerjoin(
                    evaluations_table,
                    records_table.c.id == evaluations_table.c.record_id,
                )
                .order_by(evaluations_table.c.score.desc().nulls_last(), records_table.c.captured_at.desc())
                .limit(limit),
            )
            items: list[tuple[Record, Evaluation | None]] = []
            for row in result:
                mapping = row._mapping
                record = Record.model_validate(
                    {column.name: mapping[column] for column in records_table.columns},
                )
                evaluation_id = mapping[evaluations_table.c.id]
                evaluation = None
                if evaluation_id is not None:
                    evaluation = Evaluation.model_validate(
                        {column.name: mapping[column] for column in evaluations_table.columns},
                    )
                items.append((record, evaluation))
            return items

    def add_evaluation(self, evaluation: Evaluation) -> None:
        with Session(self.engine) as session:
            existing = session.execute(
                select(evaluations_table.c.id).where(
                    evaluations_table.c.record_id == evaluation.record_id,
                ),
            ).first()
            if existing is not None:
                return
            session.execute(insert(evaluations_table).values(**evaluation.model_dump(mode="python")))
            session.commit()

    def get_evaluation(self, record_id: str) -> Evaluation | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(evaluations_table).where(evaluations_table.c.record_id == record_id),
            ).first()
            if row is None:
                return None
            return Evaluation.model_validate(dict(row._mapping))

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

    def _migrate_records_table(self) -> None:
        with self.engine.begin() as connection:
            rows = connection.exec_driver_sql("PRAGMA table_info(records)").mappings().all()
            columns = {row["name"] for row in rows}
            if "external_id" not in columns:
                connection.exec_driver_sql("ALTER TABLE records ADD COLUMN external_id VARCHAR")
            if "fingerprint" not in columns:
                connection.exec_driver_sql("ALTER TABLE records ADD COLUMN fingerprint VARCHAR")
            if "relevant_from" not in columns:
                connection.exec_driver_sql("ALTER TABLE records ADD COLUMN relevant_from DATETIME")
            if "relevant_to" not in columns:
                connection.exec_driver_sql("ALTER TABLE records ADD COLUMN relevant_to DATETIME")

            existing = connection.execute(select(records_table)).mappings().all()
            seen: set[str] = set()
            for row in existing:
                record = Record.model_validate(dict(row)).with_fingerprint()
                fingerprint = record.fingerprint or ""
                if fingerprint in seen:
                    fingerprint = f"legacy-duplicate:{record.id}"
                seen.add(fingerprint)
                connection.exec_driver_sql(
                    "UPDATE records SET fingerprint = ?, external_id = ? WHERE id = ?",
                    (fingerprint, record.external_id, record.id),
                )

            index_rows = connection.exec_driver_sql("PRAGMA index_list(records)").mappings().all()
            index_names = {row["name"] for row in index_rows}
            if "uq_records_fingerprint" not in index_names:
                connection.exec_driver_sql(
                    "CREATE UNIQUE INDEX uq_records_fingerprint ON records(fingerprint)",
                )
