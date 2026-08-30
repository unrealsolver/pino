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
    bindparam,
    cast,
    create_engine,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from pino_llm import LLMUsage

from pino_core.models import ChatMessage, LLMUsageEvent, MemoryEntry, Record, Refinement, utc_now
from pino_core.schedules import compile_query_weekly_pattern, compile_weekly_pattern

metadata = MetaData()

# PostgreSQL-only derived search data. Keep it out of portable metadata so
# SQLite schema creation remains unchanged.
_postgresql_metadata = MetaData()

refinement_schedule_index_table = Table(
    "refinement_schedule_index",
    _postgresql_metadata,
    Column("refinement_id", String, primary_key=True),
    Column("timezone", String, nullable=False),
    Column("weekly_pattern", postgresql.INT4MULTIRANGE(), nullable=False),
)

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
    Column("schedule", JSON),
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

llm_usage_events_table = Table(
    "llm_usage_events",
    metadata,
    Column("id", String, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("provider", String, nullable=False),
    Column("model", String, nullable=False),
    Column("operation", String, nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("cached_input_tokens", Integer, nullable=False),
    Column("duration_ms", Integer, nullable=False),
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


@dataclass(frozen=True)
class EventQueryResult:
    record: Record
    refinement: Refinement
    score: float


@dataclass(frozen=True)
class LLMUsageSummary:
    calls: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    duration_ms: int

    @property
    def uncached_input_tokens(self) -> int:
        return max(0, self.input_tokens - self.cached_input_tokens)

    @property
    def cache_hit_ratio(self) -> float:
        if self.input_tokens <= 0:
            return 0.0
        return self.cached_input_tokens / self.input_tokens

    @property
    def average_duration_ms(self) -> int:
        if self.calls <= 0:
            return 0
        return round(self.duration_ms / self.calls)


class DatabaseStore:
    def __init__(self, database_url: str) -> None:
        url = normalize_database_url(database_url)
        if url.get_backend_name() not in {"sqlite", "postgresql"}:
            raise ValueError(f"Unsupported storage database: {url.get_backend_name()}")
        if url.get_backend_name() == "sqlite" and url.database not in {None, "", ":memory:"}:
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        self.database_url = url
        self.engine = create_engine(url, future=True)

    def init_schema(self) -> None:
        metadata.create_all(self.engine)
        if self.engine.dialect.name == "sqlite":
            self._migrate_legacy_sqlite_records_table()

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

    def get_record(self, record_id: str) -> Record | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(records_table).where(records_table.c.id == record_id),
            ).first()
            return Record.model_validate(dict(row._mapping)) if row is not None else None

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
            query = (
                select(records_table, refinements_table)
                .join(refinements_table, records_table.c.id == refinements_table.c.record_id)
                .where(
                    and_(
                        refinements_table.c.content_kind == "event",
                        refinements_table.c.relevant_from.is_not(None),
                        or_(
                            and_(
                                refinements_table.c.relevant_to.is_(None),
                                refinements_table.c.relevant_from >= window_start,
                            ),
                            and_(
                                refinements_table.c.relevant_to.is_not(None),
                                refinements_table.c.relevant_to >= window_start,
                            ),
                        ),
                        refinements_table.c.relevant_from <= window_end,
                    ),
                )
            )
            if self.engine.dialect.name == "postgresql":
                timezones = list(
                    session.execute(
                        select(refinement_schedule_index_table.c.timezone).distinct()
                    ).scalars()
                )
                query = query.outerjoin(
                    refinement_schedule_index_table,
                    refinement_schedule_index_table.c.refinement_id == refinements_table.c.id,
                ).where(
                    _postgres_schedule_candidate_filter(
                        timezones,
                        window_start=window_start,
                        window_end=window_end,
                    )
                )
            result = session.execute(
                query.order_by(
                    refinements_table.c.relevant_from.asc(),
                    records_table.c.captured_at.desc(),
                ).limit(limit)
            )
            return [_record_with_refinement_from_row(row) for row in result]

    def query_events(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        categories: list[str] | None = None,
        min_score: float = 0.0,
        text_query: str = "",
        limit: int = 200,
        scan_limit: int = 2000,
    ) -> list[EventQueryResult]:
        categories = [category for category in categories or [] if category]
        limit = max(1, min(limit, 500))
        scan_limit = max(limit, min(scan_limit, 5000))
        min_score = max(0.0, min(float(min_score), 1.0))
        query = text_query.strip().casefold()
        rows = self.list_relevant_refinements(
            window_start=window_start,
            window_end=window_end,
            limit=scan_limit,
        )
        results: list[EventQueryResult] = []
        for record, refinement in rows:
            score = _matching_category_score(
                refinement,
                categories=categories,
                min_score=min_score,
            )
            if score is None:
                continue
            if query and query not in _event_search_text(record, refinement):
                continue
            results.append(EventQueryResult(record=record, refinement=refinement, score=score))
            if len(results) >= limit:
                break
        return results

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
                if self.engine.dialect.name == "postgresql" and refinement.schedule is not None:
                    _insert_postgres_schedule_index(session, refinement)
            session.commit()

    def list_refinements(self, record_id: str) -> list[Refinement]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(refinements_table)
                .where(refinements_table.c.record_id == record_id)
                .order_by(refinements_table.c.item_index),
            )
            return [Refinement.model_validate(dict(row._mapping)) for row in rows]

    def get_refinement(self, refinement_id: str) -> Refinement | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(refinements_table).where(refinements_table.c.id == refinement_id),
            ).first()
            return Refinement.model_validate(dict(row._mapping)) if row is not None else None

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

    def add_llm_usage_event(self, usage: LLMUsage) -> None:
        event = LLMUsageEvent(
            provider=usage.provider,
            model=usage.model,
            operation=usage.operation,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            duration_ms=usage.duration_ms,
        )
        self._insert_model(llm_usage_events_table, event)

    def list_llm_usage_events(
        self,
        *,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[LLMUsageEvent]:
        limit = max(1, min(limit, 500))
        with Session(self.engine) as session:
            query = select(llm_usage_events_table)
            if since is not None:
                query = query.where(llm_usage_events_table.c.created_at >= since)
            result = session.execute(
                query.order_by(llm_usage_events_table.c.created_at.desc()).limit(limit),
            )
            return [LLMUsageEvent.model_validate(dict(row._mapping)) for row in result]

    def summarize_llm_usage(
        self,
        *,
        since: datetime | None = None,
        group_by: str | None = None,
    ) -> dict[str, LLMUsageSummary]:
        if group_by not in {None, "model", "operation", "provider"}:
            raise ValueError("group_by must be one of: model, operation, provider")

        with Session(self.engine) as session:
            columns = [
                func.count().label("calls"),
                func.coalesce(func.sum(llm_usage_events_table.c.input_tokens), 0).label(
                    "input_tokens"
                ),
                func.coalesce(func.sum(llm_usage_events_table.c.output_tokens), 0).label(
                    "output_tokens"
                ),
                func.coalesce(func.sum(llm_usage_events_table.c.cached_input_tokens), 0).label(
                    "cached_input_tokens"
                ),
                func.coalesce(func.sum(llm_usage_events_table.c.duration_ms), 0).label(
                    "duration_ms"
                ),
            ]
            key_column = getattr(llm_usage_events_table.c, group_by) if group_by else None
            if key_column is not None:
                columns.insert(0, key_column.label("usage_key"))
            query = select(*columns)
            if since is not None:
                query = query.where(llm_usage_events_table.c.created_at >= since)
            if key_column is not None:
                query = query.group_by(key_column).order_by(key_column)

            rows = session.execute(query)
            summaries: dict[str, LLMUsageSummary] = {}
            for row in rows:
                mapping = row._mapping
                key = str(mapping["usage_key"]) if key_column is not None else "total"
                summaries[key] = LLMUsageSummary(
                    calls=int(mapping["calls"] or 0),
                    input_tokens=int(mapping["input_tokens"] or 0),
                    output_tokens=int(mapping["output_tokens"] or 0),
                    cached_input_tokens=int(mapping["cached_input_tokens"] or 0),
                    duration_ms=int(mapping["duration_ms"] or 0),
                )
            if not summaries and key_column is None:
                summaries["total"] = LLMUsageSummary(
                    calls=0,
                    input_tokens=0,
                    output_tokens=0,
                    cached_input_tokens=0,
                    duration_ms=0,
                )
            return summaries

    def _insert_model(self, table: Table, model: Any) -> None:
        with Session(self.engine) as session:
            session.execute(insert(table).values(**model.model_dump(mode="python")))
            session.commit()

    def _select_latest(self, table: Table, order_column: Any, limit: int) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            result = session.execute(select(table).order_by(order_column.desc()).limit(limit))
            return [dict(row._mapping) for row in result]

    def _migrate_legacy_sqlite_records_table(self) -> None:
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


class SQLiteStore(DatabaseStore):
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        super().__init__(f"sqlite:///{self.path}")


def _record_with_refinement_from_row(row: Any) -> tuple[Record, Refinement]:
    mapping = row._mapping
    record = Record.model_validate(
        {column.name: mapping[column] for column in records_table.columns},
    )
    refinement = Refinement.model_validate(
        {column.name: mapping[column] for column in refinements_table.columns},
    )
    return record, refinement


def normalize_database_url(database_url: str):
    url = make_url(database_url)
    if url.drivername == "postgresql":
        return url.set(drivername="postgresql+psycopg")
    return url


def _insert_postgres_schedule_index(session: Session, refinement: Refinement) -> None:
    if refinement.schedule is None:
        return
    pattern = compile_weekly_pattern(refinement.schedule)
    session.execute(
        insert(refinement_schedule_index_table).values(
            refinement_id=bindparam("schedule_refinement_id"),
            timezone=bindparam("schedule_timezone"),
            weekly_pattern=cast(
                bindparam("schedule_weekly_pattern"),
                postgresql.INT4MULTIRANGE(),
            ),
        ),
        {
            "schedule_refinement_id": refinement.id,
            "schedule_timezone": pattern.timezone,
            "schedule_weekly_pattern": pattern.as_postgresql_multirange(),
        },
    )


def _postgres_schedule_candidate_filter(
    timezones: list[str],
    *,
    window_start: datetime,
    window_end: datetime,
) -> ColumnElement[bool]:
    matches: list[ColumnElement[bool]] = []
    for index, timezone_name in enumerate(timezones):
        query_pattern = compile_query_weekly_pattern(
            window_start,
            window_end,
            timezone_name,
        )
        matches.append(
            and_(
                refinement_schedule_index_table.c.timezone
                == bindparam(f"schedule_query_timezone_{index}", timezone_name),
                refinement_schedule_index_table.c.weekly_pattern.op("&&")(
                    cast(
                        bindparam(
                            f"schedule_query_pattern_{index}",
                            query_pattern.as_postgresql_multirange(),
                        ),
                        postgresql.INT4MULTIRANGE(),
                    )
                ),
            )
        )
    return or_(refinement_schedule_index_table.c.refinement_id.is_(None), *matches)


def _matching_category_score(
    refinement: Refinement,
    *,
    categories: list[str],
    min_score: float,
) -> float | None:
    scores = refinement.category_scores
    if categories:
        selected_scores = [scores.get(category, 0.0) for category in categories]
        best_score = max(selected_scores, default=0.0)
        if best_score <= 0.0 or best_score < min_score:
            return None
        return best_score
    best_score = max(scores.values(), default=0.0)
    if min_score > 0.0 and best_score < min_score:
        return None
    return best_score


def _event_search_text(record: Record, refinement: Refinement) -> str:
    return "\n".join(
        part
        for part in (
            record.title,
            record.text,
            refinement.summary,
            refinement.location,
            record.url,
        )
        if part
    ).casefold()
