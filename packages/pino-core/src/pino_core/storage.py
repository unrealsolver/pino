from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    create_engine,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.orm import Session

from pino_core.models import ChatMessage, MemoryEntry, Record, Refinement, utc_now

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
    Column("captured_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("provenance", JSON, nullable=False),
    UniqueConstraint("fingerprint", name="uq_records_fingerprint"),
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

refinements_table = Table(
    "refinements",
    metadata,
    Column("id", String, primary_key=True),
    Column("record_id", String, nullable=False),
    Column("item_index", Integer, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("taxonomy_version", Integer, nullable=False),
    Column("content_kind", String, nullable=False),
    Column("summary", Text),
    Column("relevant_from", DateTime(timezone=True)),
    Column("relevant_to", DateTime(timezone=True)),
    Column("location", String),
    Column("category_scores", JSON, nullable=False),
    Column("embedding", JSON),
    Column("refiner", String, nullable=False),
    Column("refined_at", DateTime(timezone=True), nullable=False),
    Column("debug", JSON, nullable=False),
    UniqueConstraint("record_id", "item_index", name="uq_refinements_record_item"),
)

source_cursors_table = Table(
    "source_cursors",
    metadata,
    Column("source", String, primary_key=True),
    Column("cursor", String, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class InsertResult:
    record: Record
    inserted: bool


@dataclass(frozen=True)
class RecordRefinementStatus:
    record: Record
    refinements: list[Refinement]

    @property
    def is_refined(self) -> bool:
        return bool(self.refinements)


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
                return InsertResult(
                    record=Record.model_validate(dict(existing._mapping)), inserted=False
                )
            session.execute(insert(records_table).values(**record.model_dump(mode="python")))
            session.commit()
            return InsertResult(record=record, inserted=True)

    def get_source_cursor(self, source: str) -> str | None:
        with Session(self.engine) as session:
            return session.execute(
                select(source_cursors_table.c.cursor).where(
                    source_cursors_table.c.source == source
                ),
            ).scalar_one_or_none()

    def set_source_cursor(self, source: str, cursor: str) -> None:
        with Session(self.engine) as session:
            existing = session.execute(
                select(source_cursors_table.c.source).where(
                    source_cursors_table.c.source == source
                ),
            ).scalar_one_or_none()
            values = {"cursor": cursor, "updated_at": utc_now()}
            if existing is None:
                session.execute(insert(source_cursors_table).values(source=source, **values))
            else:
                session.execute(
                    update(source_cursors_table)
                    .where(source_cursors_table.c.source == source)
                    .values(**values),
                )
            session.commit()

    def list_records(self, limit: int = 50) -> list[Record]:
        rows = self._select_latest(records_table, records_table.c.captured_at, limit)
        return [Record.model_validate(dict(row)) for row in rows]

    def list_unrefined_records(self, limit: int = 20) -> list[Record]:
        with Session(self.engine) as session:
            result = session.execute(
                select(records_table)
                .outerjoin(
                    refinements_table,
                    records_table.c.id == refinements_table.c.record_id,
                )
                .where(refinements_table.c.record_id.is_(None))
                .order_by(records_table.c.captured_at.desc())
                .limit(limit),
            )
            return [Record.model_validate(dict(row._mapping)) for row in result]

    def list_records_with_refinement_status(self, limit: int = 50) -> list[RecordRefinementStatus]:
        return [
            RecordRefinementStatus(record=record, refinements=self.list_refinements(record.id))
            for record in self.list_records(limit=limit)
        ]

    def count_unrefined_records(self, *, record_ids: list[str] | None = None) -> int:
        with Session(self.engine) as session:
            query = (
                select(func.count())
                .select_from(
                    records_table.outerjoin(
                        refinements_table,
                        records_table.c.id == refinements_table.c.record_id,
                    ),
                )
                .where(refinements_table.c.record_id.is_(None))
            )
            if record_ids is not None:
                if not record_ids:
                    return 0
                query = query.where(records_table.c.id.in_(record_ids))
            return int(session.execute(query).scalar_one())

    def list_relevant_refinements(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        limit: int = 20,
    ) -> list[tuple[Record, Refinement]]:
        with Session(self.engine) as session:
            result = session.execute(
                select(records_table, refinements_table)
                .join(refinements_table, records_table.c.id == refinements_table.c.record_id)
                .where(
                    and_(
                        refinements_table.c.content_kind == "event",
                        refinements_table.c.relevant_from.is_not(None),
                        or_(
                            refinements_table.c.relevant_to.is_(None),
                            refinements_table.c.relevant_to >= window_start,
                        ),
                        refinements_table.c.relevant_from <= window_end,
                    ),
                )
                .order_by(
                    refinements_table.c.relevant_from.asc(),
                    records_table.c.captured_at.desc(),
                )
                .limit(limit),
            )
            return [_record_with_refinement_from_row(row) for row in result]

    def replace_refinements(self, record_id: str, refinements: list[Refinement]) -> None:
        with Session(self.engine) as session:
            session.execute(
                delete(refinements_table).where(refinements_table.c.record_id == record_id)
            )
            for refinement in refinements:
                if refinement.record_id != record_id:
                    raise ValueError("refinement record_id does not match replacement record")
                session.execute(
                    insert(refinements_table).values(**refinement.model_dump(mode="python"))
                )
            session.commit()

    def list_refinements(self, record_id: str) -> list[Refinement]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(refinements_table)
                .where(refinements_table.c.record_id == record_id)
                .order_by(refinements_table.c.item_index),
            )
            return [Refinement.model_validate(dict(row._mapping)) for row in rows]

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


def _record_with_refinement_from_row(row: Any) -> tuple[Record, Refinement]:
    mapping = row._mapping
    record = Record.model_validate(
        {column.name: mapping[column] for column in records_table.columns},
    )
    refinement = Refinement.model_validate(
        {column.name: mapping[column] for column in refinements_table.columns},
    )
    return record, refinement
