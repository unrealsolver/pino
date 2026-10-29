from __future__ import annotations

from collections import Counter
from collections.abc import Generator, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast as type_cast
from zoneinfo import ZoneInfo

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    and_,
    bindparam,
    case,
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
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from pino_llm import LLMUsage

from pino_core.models import (
    SOURCE_SYNC_FAILURE_STAGES,
    ChatMessage,
    LLMUsageEvent,
    MemoryEntry,
    Record,
    Refinement,
    SourceSyncFailureStage,
    SourceSyncOutcome,
    SourceSyncRun,
    utc_now,
)
from pino_core.schedules import (
    compile_query_weekly_pattern,
    compile_weekly_pattern,
    expand_schedule,
)
from pino_core.stats import (
    REFINEMENT_CONTENT_KINDS,
    CityEventAggregate,
    RecordTotalsAggregate,
    RefinementTotalsAggregate,
    SourceRecordAggregate,
    SourceRefinementAggregate,
    SourceStatusSnapshot,
    WeekRecordCount,
)

_MAX_RELEVANT_SCAN = 5000
_RELEVANT_FETCH_SIZE = 200

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
    Column("published_at", DateTime(timezone=True)),
    Column("images", JSON, nullable=False, server_default="[]"),
    Column("captured_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("provenance", JSON, nullable=False),
    UniqueConstraint("fingerprint", name="uq_records_fingerprint"),
    Index("ix_records_published_at", "published_at"),
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
    Column("city_id", String),
    Column("category_scores", JSON, nullable=False),
    Column("embedding", JSON),
    Column("refiner", String, nullable=False),
    Column("refined_at", DateTime(timezone=True), nullable=False),
    Column("debug", JSON, nullable=False),
    UniqueConstraint("record_id", "item_index", name="uq_refinements_record_item"),
    Index("ix_refinements_city_id", "city_id"),
)

source_cursors_table = Table(
    "source_cursors",
    metadata,
    Column("source", String, primary_key=True),
    Column("cursor", String, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

source_sync_runs_table = Table(
    "source_sync_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("source", String, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("outcome", String),
    Column("fetched_count", Integer, nullable=False, server_default="0"),
    Column("inserted_count", Integer, nullable=False, server_default="0"),
    Column("duplicate_count", Integer, nullable=False, server_default="0"),
    Column("failure_stage", String),
    CheckConstraint(
        "(completed_at IS NULL AND outcome IS NULL) OR "
        "(completed_at IS NOT NULL AND outcome IS NOT NULL "
        "AND outcome IN ('success', 'failure') AND completed_at >= started_at)",
        name="ck_source_sync_runs_completion",
    ),
    CheckConstraint(
        "fetched_count >= 0 AND inserted_count >= 0 AND duplicate_count >= 0 "
        "AND inserted_count + duplicate_count <= fetched_count",
        name="ck_source_sync_runs_counts",
    ),
    CheckConstraint(
        "failure_stage IS NULL OR (outcome IS NOT NULL AND outcome = 'failure')",
        name="ck_source_sync_runs_failure_stage",
    ),
    Index("ix_source_sync_runs_source_started_at", "source", "started_at", "id"),
    Index(
        "ix_source_sync_runs_source_outcome_completed_at",
        "source",
        "outcome",
        "completed_at",
        "id",
    ),
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


class SourceSyncRunNotFoundError(LookupError):
    """Raised when a source sync attempt id does not exist."""


class SourceSyncRunAlreadyCompletedError(RuntimeError):
    """Raised when a terminal source sync attempt is completed again."""


class DatabaseStore:
    def __init__(self, database_url: str) -> None:
        url = normalize_database_url(database_url)
        if url.get_backend_name() not in {"sqlite", "postgresql"}:
            raise ValueError(f"Unsupported storage database: {url.get_backend_name()}")
        if url.get_backend_name() == "sqlite" and url.database not in {None, "", ":memory:"}:
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        self.database_url = url
        self.engine = create_engine(url, future=True, pool_pre_ping=True)

    def init_schema(self) -> None:
        from pino_core.db import upgrade_database

        upgrade_database(
            self.database_url.render_as_string(hide_password=False),
            engine=self.engine,
        )

    def add_record(self, record: Record) -> InsertResult:
        record = record.with_fingerprint()
        with Session(self.engine) as session:
            existing = session.execute(
                select(records_table).where(records_table.c.fingerprint == record.fingerprint),
            ).first()
            if existing is not None:
                existing_record = Record.model_validate(dict(existing._mapping))
                if existing_record.published_at is None and record.published_at is not None:
                    session.execute(
                        update(records_table)
                        .where(records_table.c.id == existing_record.id)
                        .values(published_at=record.published_at)
                    )
                    session.commit()
                    existing_record = existing_record.model_copy(
                        update={"published_at": record.published_at}
                    )
                return InsertResult(
                    record=existing_record,
                    inserted=False,
                )
            session.execute(insert(records_table).values(**record.model_dump(mode="python")))
            session.commit()
            return InsertResult(record=record, inserted=True)

    def set_record_images(self, record: Record) -> None:
        with Session(self.engine) as session:
            session.execute(
                update(records_table)
                .where(records_table.c.id == record.id)
                .values(images=record.model_dump(mode="json")["images"])
            )
            session.commit()

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

    def start_source_sync_attempt(
        self,
        source: str,
        *,
        started_at: datetime | None = None,
    ) -> SourceSyncRun:
        """Persist a new unfinished attempt before any source fetch happens."""
        attempt = SourceSyncRun(
            source=source,
            started_at=_require_aware_utc(
                started_at if started_at is not None else utc_now(),
                field="started_at",
            ),
        )
        self._insert_model(source_sync_runs_table, attempt)
        return attempt

    def complete_source_sync_success(
        self,
        run_id: str,
        *,
        fetched_count: int,
        inserted_count: int,
        duplicate_count: int,
        completed_at: datetime | None = None,
    ) -> SourceSyncRun:
        """Complete a started attempt as a successful terminal run.

        Zero-result and duplicate-only attempts are successful. The counts are
        the truthful partial totals observed when the attempt finished.
        """
        return self._complete_source_sync_run(
            run_id,
            outcome="success",
            fetched_count=fetched_count,
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            failure_stage=None,
            completed_at=completed_at,
        )

    def complete_source_sync_failure(
        self,
        run_id: str,
        *,
        fetched_count: int,
        inserted_count: int,
        duplicate_count: int,
        failure_stage: str | None = None,
        completed_at: datetime | None = None,
    ) -> SourceSyncRun:
        """Complete a started attempt as a failed terminal run.

        ``failure_stage`` is an optional safe stage code from
        ``SOURCE_SYNC_FAILURE_STAGES``. Raw exception text must never be passed.
        """
        return self._complete_source_sync_run(
            run_id,
            outcome="failure",
            fetched_count=fetched_count,
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            failure_stage=_validated_failure_stage(failure_stage),
            completed_at=completed_at,
        )

    def _complete_source_sync_run(
        self,
        run_id: str,
        *,
        outcome: SourceSyncOutcome,
        fetched_count: int,
        inserted_count: int,
        duplicate_count: int,
        failure_stage: SourceSyncFailureStage | None,
        completed_at: datetime | None,
    ) -> SourceSyncRun:
        fetched = _validated_sync_count(fetched_count, field="fetched_count")
        inserted = _validated_sync_count(inserted_count, field="inserted_count")
        duplicate = _validated_sync_count(duplicate_count, field="duplicate_count")
        if inserted + duplicate > fetched:
            raise ValueError("inserted_count + duplicate_count must not exceed fetched_count")
        values = {
            "completed_at": _require_aware_utc(
                completed_at if completed_at is not None else utc_now(),
                field="completed_at",
            ),
            "outcome": outcome,
            "fetched_count": fetched,
            "inserted_count": inserted,
            "duplicate_count": duplicate,
            "failure_stage": failure_stage,
        }
        with Session(self.engine) as session:
            # The completion predicate makes terminal writes atomic: an already
            # completed row can never be overwritten by a later completion.
            result = session.execute(
                update(source_sync_runs_table)
                .where(
                    source_sync_runs_table.c.id == run_id,
                    source_sync_runs_table.c.completed_at.is_(None),
                )
                .values(**values),
            )
            if result.rowcount != 1:
                session.rollback()
                exists = session.execute(
                    select(source_sync_runs_table.c.id).where(
                        source_sync_runs_table.c.id == run_id
                    ),
                ).scalar_one_or_none()
                if exists is None:
                    raise SourceSyncRunNotFoundError(f"source sync attempt not found: {run_id}")
                raise SourceSyncRunAlreadyCompletedError(
                    f"source sync attempt is already completed: {run_id}"
                )
            row = session.execute(
                select(source_sync_runs_table).where(source_sync_runs_table.c.id == run_id),
            ).one()
            attempt = SourceSyncRun.model_validate(dict(row._mapping))
            session.commit()
            return attempt

    def latest_source_sync_attempts(self) -> tuple[SourceSyncRun, ...]:
        """Return the latest attempt per attempted source.

        Includes sources that have attempts but no stored records, and sources
        whose latest attempt is unfinished.
        """
        return self._latest_source_sync_runs(successful_only=False)

    def latest_source_sync_successes(self) -> tuple[SourceSyncRun, ...]:
        """Return the latest successful terminal completion per source.

        This is independent of the latest attempt: a later failure or unfinished
        attempt does not erase the previous successful completion.
        """
        return self._latest_source_sync_runs(successful_only=True)

    def _latest_source_sync_runs(self, *, successful_only: bool) -> tuple[SourceSyncRun, ...]:
        with Session(self.engine) as session:
            rows = session.execute(
                _latest_source_sync_runs_query(successful_only=successful_only),
            ).all()
        return tuple(SourceSyncRun.model_validate(dict(row._mapping)) for row in rows)

    def list_records(self, limit: int = 50) -> list[Record]:
        rows = self._select_latest(records_table, records_table.c.captured_at, limit)
        return [Record.model_validate(dict(row)) for row in rows]

    def get_record(self, record_id: str) -> Record | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(records_table).where(records_table.c.id == record_id),
            ).first()
            return Record.model_validate(dict(row._mapping)) if row is not None else None

    def set_record_media(self, record: Record) -> None:
        with Session(self.engine) as session:
            session.execute(
                update(records_table)
                .where(records_table.c.id == record.id)
                .values(images=record.model_dump(mode="json")["images"], payload=record.payload)
            )
            session.commit()

    def list_media_backfill_batch(
        self, source: str, *, after_id: str = "", limit: int = 100
    ) -> list[Record]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(records_table)
                .where(records_table.c.source == source, records_table.c.id > after_id)
                .order_by(records_table.c.id)
                .limit(limit)
            )
            return [Record.model_validate(dict(row._mapping)) for row in rows]

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

    def summarize_source_publications(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        timezone_name: str,
    ) -> tuple[dict[tuple[str, date], int], dict[str, int]]:
        if window_start.tzinfo is None or window_end.tzinfo is None:
            raise ValueError("publication statistics window must be timezone-aware")
        timezone_info = ZoneInfo(timezone_name)
        with Session(self.engine) as session:
            published_rows = session.execute(
                select(records_table.c.source, records_table.c.published_at).where(
                    records_table.c.published_at >= window_start,
                    records_table.c.published_at < window_end,
                )
            )
            counts: Counter[tuple[str, date]] = Counter()
            for source, published_at in published_rows:
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
                local_date = published_at.astimezone(timezone_info).date()
                week_start = local_date - timedelta(days=local_date.weekday())
                counts[(source, week_start)] += 1

            unknown_rows = session.execute(
                select(records_table.c.source, func.count())
                .where(records_table.c.published_at.is_(None))
                .group_by(records_table.c.source)
            )
            unknown = {source: int(count) for source, count in unknown_rows}
        return dict(counts), unknown

    def load_source_status_snapshot(
        self,
        *,
        week_bounds: Sequence[tuple[datetime, datetime]],
    ) -> SourceStatusSnapshot:
        """Load grouped source statistics without materializing raw rows.

        Record and refinement aggregates are queried independently, so a record
        with several refinements is counted once for coverage while each
        refinement row still counts as one output item. The query count is fixed
        and does not grow with the number of sources or cities.
        """
        if not week_bounds:
            raise ValueError("at least one week bound is required")
        for week_start, week_end in week_bounds:
            if (
                week_start.tzinfo is None
                or week_start.utcoffset() is None
                or week_end.tzinfo is None
                or week_end.utcoffset() is None
            ):
                raise ValueError("week bounds must be timezone-aware")
            if week_start > week_end:
                raise ValueError("week start must not be after week end")

        with _snapshot_connection(self.engine) as connection:
            record_row = connection.execute(_record_totals_query()).one()
            refinement_rows = connection.execute(_refinement_totals_query()).all()
            source_rows = connection.execute(_source_record_totals_query()).all()
            week_rows = connection.execute(_source_week_records_query(week_bounds)).all()
            source_refinement_rows = connection.execute(_source_refinement_query()).all()
            city_rows = connection.execute(_city_event_query()).all()

        return SourceStatusSnapshot(
            records=RecordTotalsAggregate(
                records_total=int(record_row.records_total or 0),
                records_with_refinement_total=int(record_row.records_with_refinement_total or 0),
                pending_records_total=(
                    int(record_row.records_total or 0)
                    - int(record_row.records_with_refinement_total or 0)
                ),
                oldest_pending_captured_at=_utc_or_none(record_row.oldest_pending_captured_at),
                latest_captured_at=_utc_or_none(record_row.latest_captured_at),
            ),
            refinements=_fold_refinement_rows(refinement_rows),
            sources=_source_record_aggregates(source_rows, week_rows),
            source_refinements=_source_refinement_aggregates(source_refinement_rows),
            city_events=tuple(
                CityEventAggregate(
                    city_id=row.city_id,
                    items=int(row.items or 0),
                    sources=frozenset({row.source} if row.source is not None else set()),
                )
                for row in city_rows
            ),
        )

    def list_relevant_refinements(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        limit: int = 20,
        scan_limit: int = _MAX_RELEVANT_SCAN,
    ) -> list[tuple[Record, Refinement]]:
        if limit <= 0:
            return []
        rows: list[tuple[Record, Refinement]] = []
        with closing(
            self._iter_relevant_candidates(
                window_start=window_start,
                window_end=window_end,
                scan_limit=max(limit, min(scan_limit, _MAX_RELEVANT_SCAN)),
            )
        ) as candidates:
            for record, refinement in candidates:
                if not _refinement_matches_schedule(
                    refinement,
                    window_start=window_start,
                    window_end=window_end,
                ):
                    continue
                rows.append((record, refinement))
                if len(rows) >= limit:
                    break
        return rows

    def _iter_relevant_candidates(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        city_id: str | None = None,
        scan_limit: int,
    ) -> Generator[tuple[Record, Refinement], None, None]:
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
            if city_id is not None:
                query = query.where(refinements_table.c.city_id == city_id)
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
                    refinements_table.c.id.asc(),
                )
                .limit(scan_limit)
                .execution_options(yield_per=min(_RELEVANT_FETCH_SIZE, scan_limit))
            )
            for row in result:
                yield _record_with_refinement_from_row(row)

    def query_events(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        categories: list[str] | None = None,
        min_score: float = 0.0,
        text_query: str = "",
        city_id: str | None = None,
        limit: int = 200,
        scan_limit: int = _MAX_RELEVANT_SCAN,
    ) -> list[EventQueryResult]:
        categories = [category for category in categories or [] if category]
        limit = max(1, min(limit, 500))
        scan_limit = max(limit, min(scan_limit, _MAX_RELEVANT_SCAN))
        min_score = max(0.0, min(float(min_score), 1.0))
        query = text_query.strip().casefold()
        results: list[EventQueryResult] = []
        with closing(
            self._iter_relevant_candidates(
                window_start=window_start,
                window_end=window_end,
                city_id=city_id,
                scan_limit=scan_limit,
            )
        ) as rows:
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
                if not _refinement_matches_schedule(
                    refinement,
                    window_start=window_start,
                    window_end=window_end,
                ):
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


class SQLiteStore(DatabaseStore):
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        super().__init__(f"sqlite:///{self.path}")


def _latest_source_sync_runs_query(*, successful_only: bool):
    """Rank attempts per source without one query per source.

    Latest attempts use ``(started_at, id)``; successful terminal runs use
    ``(completed_at, id)``. The id tie-break keeps equal timestamps stable.
    """
    if successful_only:
        order_by = [
            source_sync_runs_table.c.completed_at.desc(),
            source_sync_runs_table.c.id.desc(),
        ]
    else:
        order_by = [
            source_sync_runs_table.c.started_at.desc(),
            source_sync_runs_table.c.id.desc(),
        ]
    ranked = select(
        source_sync_runs_table,
        func.row_number()
        .over(
            partition_by=source_sync_runs_table.c.source,
            order_by=order_by,
        )
        .label("run_rank"),
    )
    if successful_only:
        ranked = ranked.where(
            source_sync_runs_table.c.outcome == "success",
            source_sync_runs_table.c.completed_at.is_not(None),
        )
    ranked_runs = ranked.subquery("ranked_source_sync_runs")
    return (
        select(*(ranked_runs.c[column.name] for column in source_sync_runs_table.columns))
        .where(ranked_runs.c.run_rank == 1)
        .order_by(ranked_runs.c.source)
    )


def _require_aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _validated_sync_count(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _validated_failure_stage(value: str | None) -> SourceSyncFailureStage | None:
    if value is None:
        return None
    if value not in SOURCE_SYNC_FAILURE_STAGES:
        raise ValueError("failure_stage must be one of: " + ", ".join(SOURCE_SYNC_FAILURE_STAGES))
    return type_cast(SourceSyncFailureStage, value)


@contextmanager
def _snapshot_connection(engine: Engine) -> Iterator[Connection]:
    """Yield one local connection with a consistent, read-only snapshot.

    SQLite's legacy transaction mode does not start a database transaction for a
    plain SELECT, so an explicit ``BEGIN`` is required to keep every aggregate
    query on the same read snapshot. PostgreSQL uses a local REPEATABLE READ,
    read-only transaction for the same reason. Neither setting changes the
    engine, schema, or unrelated queries.
    """
    connection = engine.connect()
    try:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN")
        elif engine.dialect.name == "postgresql":
            connection = connection.execution_options(
                isolation_level="REPEATABLE READ",
                postgresql_readonly=True,
            )
        else:
            raise ValueError(f"Unsupported storage database: {engine.dialect.name}")
        try:
            yield connection
        finally:
            connection.rollback()
    finally:
        connection.close()


def _refined_record_ids_subquery():
    """Distinct refined record ids, so joins never multiply raw records."""
    return select(refinements_table.c.record_id).distinct().subquery("refined_records")


def _record_totals_query():
    refined = _refined_record_ids_subquery()
    return select(
        func.count(records_table.c.id).label("records_total"),
        func.count(refined.c.record_id).label("records_with_refinement_total"),
        func.min(
            case(
                (refined.c.record_id.is_(None), records_table.c.captured_at),
                else_=None,
            )
        ).label("oldest_pending_captured_at"),
        func.max(records_table.c.captured_at).label("latest_captured_at"),
    ).select_from(records_table.outerjoin(refined, records_table.c.id == refined.c.record_id))


def _source_record_totals_query():
    refined = _refined_record_ids_subquery()
    return (
        select(
            records_table.c.source.label("source"),
            func.count(records_table.c.id).label("records_total"),
            func.count(refined.c.record_id).label("records_with_refinement_total"),
            func.min(
                case(
                    (refined.c.record_id.is_(None), records_table.c.captured_at),
                    else_=None,
                )
            ).label("oldest_pending_captured_at"),
            func.max(records_table.c.captured_at).label("latest_captured_at"),
        )
        .select_from(records_table.outerjoin(refined, records_table.c.id == refined.c.record_id))
        .group_by(records_table.c.source)
        .order_by(records_table.c.source)
    )


def _source_week_records_query(week_bounds: Sequence[tuple[datetime, datetime]]):
    refined = _refined_record_ids_subquery()
    week_index = case(
        *[
            (
                and_(
                    records_table.c.captured_at >= week_start,
                    records_table.c.captured_at < week_end,
                ),
                index,
            )
            for index, (week_start, week_end) in enumerate(week_bounds)
        ],
        else_=None,
    )
    return (
        select(
            records_table.c.source.label("source"),
            week_index.label("week_index"),
            func.count(records_table.c.id).label("records"),
            func.count(refined.c.record_id).label("with_refinement"),
        )
        .select_from(records_table.outerjoin(refined, records_table.c.id == refined.c.record_id))
        .where(
            records_table.c.captured_at >= week_bounds[0][0],
            records_table.c.captured_at < week_bounds[-1][1],
        )
        .group_by(records_table.c.source, week_index)
        .order_by(records_table.c.source, week_index)
    )


def _refinement_totals_query():
    return select(
        refinements_table.c.content_kind.label("content_kind"),
        func.count().label("items"),
        func.max(refinements_table.c.refined_at).label("last_refined_at"),
    ).group_by(refinements_table.c.content_kind)


def _source_refinement_query():
    return (
        select(
            records_table.c.source.label("source"),
            refinements_table.c.content_kind.label("content_kind"),
            func.count().label("items"),
            func.max(refinements_table.c.refined_at).label("last_refined_at"),
        )
        .select_from(
            refinements_table.join(
                records_table,
                records_table.c.id == refinements_table.c.record_id,
            )
        )
        .group_by(records_table.c.source, refinements_table.c.content_kind)
        .order_by(records_table.c.source, refinements_table.c.content_kind)
    )


def _city_event_query():
    return (
        select(
            refinements_table.c.city_id.label("city_id"),
            records_table.c.source.label("source"),
            func.count().label("items"),
        )
        .select_from(
            refinements_table.outerjoin(
                records_table,
                records_table.c.id == refinements_table.c.record_id,
            )
        )
        .where(refinements_table.c.content_kind == "event")
        .group_by(refinements_table.c.city_id, records_table.c.source)
        .order_by(refinements_table.c.city_id, records_table.c.source)
    )


def _fold_refinement_rows(rows: Sequence[Any]) -> RefinementTotalsAggregate:
    items_by_kind = {kind: 0 for kind in REFINEMENT_CONTENT_KINDS}
    last_refined_at: datetime | None = None
    for row in rows:
        if row.content_kind in items_by_kind:
            items_by_kind[row.content_kind] += int(row.items or 0)
        latest = _utc_or_none(row.last_refined_at)
        if latest is not None and (last_refined_at is None or latest > last_refined_at):
            last_refined_at = latest
    return RefinementTotalsAggregate(
        items_by_kind=items_by_kind,
        last_refined_at=last_refined_at,
    )


def _source_record_aggregates(
    source_rows: Sequence[Any],
    week_rows: Sequence[Any],
) -> tuple[SourceRecordAggregate, ...]:
    weeks_by_source: dict[str, list[WeekRecordCount]] = {}
    for row in week_rows:
        if row.week_index is None:
            continue
        records = int(row.records or 0)
        with_refinement = int(row.with_refinement or 0)
        weeks_by_source.setdefault(row.source, []).append(
            WeekRecordCount(
                index=int(row.week_index),
                records=records,
                pending=records - with_refinement,
            )
        )

    aggregates: list[SourceRecordAggregate] = []
    for row in source_rows:
        records_total = int(row.records_total or 0)
        records_with_refinement_total = int(row.records_with_refinement_total or 0)
        aggregates.append(
            SourceRecordAggregate(
                source=row.source,
                records_total=records_total,
                records_with_refinement_total=records_with_refinement_total,
                pending_records_total=records_total - records_with_refinement_total,
                oldest_pending_captured_at=_utc_or_none(row.oldest_pending_captured_at),
                latest_captured_at=_utc_or_none(row.latest_captured_at),
                weeks=tuple(weeks_by_source.get(row.source, ())),
            )
        )
    return tuple(aggregates)


def _source_refinement_aggregates(
    rows: Sequence[Any],
) -> tuple[SourceRefinementAggregate, ...]:
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        grouped.setdefault(row.source, []).append(row)
    aggregates: list[SourceRefinementAggregate] = []
    for source in sorted(grouped):
        refinement = _fold_refinement_rows(grouped[source])
        aggregates.append(
            SourceRefinementAggregate(
                source=source,
                items_by_kind=refinement.items_by_kind,
                last_refined_at=refinement.last_refined_at,
            )
        )
    return tuple(aggregates)


def _utc_or_none(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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


def _refinement_matches_schedule(
    refinement: Refinement,
    *,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    if refinement.schedule is None:
        return True
    return bool(
        expand_schedule(
            refinement.schedule,
            window_start=window_start,
            window_end=window_end,
            key_prefix=refinement.id,
        )
    )


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
