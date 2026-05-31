from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import Evaluation, Record, utc_now
from pino_core.sources import CursorSourceAdapter, SourceAdapter
from pino_core.storage import SQLiteStore


DEFAULT_DIGEST_WINDOW_DAYS = 14


@dataclass(frozen=True)
class CheckResult:
    fetched: int
    inserted: int
    duplicates: int
    records: list[Record]
    pending_evaluation_total: int = 0
    pending_evaluation_new: int = 0


@dataclass(frozen=True)
class DigestResult:
    title: str
    body: str


class CheckPipeline:
    def __init__(self, store: SQLiteStore, sources: list[SourceAdapter]) -> None:
        self.store = store
        self.sources = sources

    def run(self) -> CheckResult:
        self.store.init_schema()
        records: list[Record] = []
        fetched_count = 0
        inserted_count = 0
        duplicate_count = 0
        inserted_ids: list[str] = []
        for source in self.sources:
            next_cursor = None
            if isinstance(source, CursorSourceAdapter):
                fetch_result = source.fetch_since(self.store.get_source_cursor(source.name))
                fetched = fetch_result.records
                next_cursor = fetch_result.cursor
            else:
                fetched = source.fetch()
            fetched_count += len(fetched)
            for record in fetched:
                result = self.store.add_record(record)
                if result.inserted:
                    inserted_count += 1
                    inserted_ids.append(result.record.id)
                    records.append(result.record)
                else:
                    duplicate_count += 1
            if next_cursor is not None:
                self.store.set_source_cursor(source.name, next_cursor)
        pending_evaluation_total = self.store.count_unevaluated_records()
        pending_evaluation_new = self.store.count_unevaluated_records(record_ids=inserted_ids)
        return CheckResult(
            fetched=fetched_count,
            inserted=inserted_count,
            duplicates=duplicate_count,
            records=records,
            pending_evaluation_total=pending_evaluation_total,
            pending_evaluation_new=pending_evaluation_new,
        )


class DigestService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def create_digest(
        self,
        limit: int = 20,
        *,
        window_start: datetime | None = None,
        window_days: int = DEFAULT_DIGEST_WINDOW_DAYS,
    ) -> DigestResult:
        self.store.init_schema()
        if window_days < 1:
            raise ValueError("window_days must be at least 1")
        window_start = window_start or utc_now()
        window_end = window_start + timedelta(days=window_days)
        records = self.store.list_relevant_records_with_evaluations(
            window_start=window_start,
            window_end=window_end,
            limit=limit,
        )

        if not records:
            body = f"No relevant records found for the next {window_days} day(s)."
        else:
            lines = []
            for record, evaluation in records:
                label = record.title or record.kind
                source = f" ({record.source})" if record.source else ""
                evaluation_text = _format_evaluation(evaluation)
                relevance_text = _format_relevance_window(record)
                location_text = _format_location(record)
                summary = evaluation.summary if evaluation and evaluation.summary else record.text
                lines.append(
                    f"- {label}{source}{evaluation_text}{relevance_text}{location_text}: {summary}",
                )
            body = "\n".join(lines)

        return DigestResult(title="Latest digest", body=body)


def _format_evaluation(evaluation: Evaluation | None) -> str:
    if evaluation is None:
        return ""
    matches = f" {'/'.join(evaluation.goal_matches)}" if evaluation.goal_matches else ""
    return f" [score {evaluation.score:.2f}{matches}]"


def _format_relevance_window(record: Record) -> str:
    start = _local_datetime(record.relevant_from)
    end = _local_datetime(record.relevant_to)
    if start is None and end is None:
        return ""
    if start is not None and end is not None:
        if start == end:
            return f" [{start:%Y-%m-%d %H:%M}]"
        if start.date() == end.date():
            return f" [{start:%Y-%m-%d %H:%M}-{end:%H:%M}]"
        return f" [{start:%Y-%m-%d %H:%M} - {end:%Y-%m-%d %H:%M}]"
    if start is not None:
        return f" [from {start:%Y-%m-%d %H:%M}]"
    return f" [until {end:%Y-%m-%d %H:%M}]"


def _format_location(record: Record) -> str:
    location = record.payload.get("location")
    if not isinstance(location, str) or not location.strip():
        return ""
    return f" @ {location.strip()}"


def _local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(ZoneInfo(DEFAULT_SOURCE_TIMEZONE))
