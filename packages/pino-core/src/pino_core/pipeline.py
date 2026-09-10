from __future__ import annotations

from dataclasses import dataclass
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.config import MediaConfig
from pino_core.media import MediaStore
from pino_core.models import Record, Refinement, utc_now
from pino_core.sources import CursorSourceAdapter, SourceAdapter, MediaSourceAdapter
from pino_core.storage import DatabaseStore


DEFAULT_DIGEST_WINDOW_DAYS = 14


@dataclass(frozen=True)
class SourceCheckResult:
    name: str
    fetched: int
    inserted: int
    duplicates: int
    kind: Literal["web", "tg"] = "web"
    cursor_updated: bool = False
    cursor_status: Literal["unsupported", "none", "unchanged", "updated"] = "unsupported"
    error: str | None = None


@dataclass(frozen=True)
class CheckResult:
    fetched: int
    inserted: int
    duplicates: int
    records: list[Record]
    pending_refinement_total: int = 0
    pending_refinement_new: int = 0
    sources: list[SourceCheckResult] | None = None


@dataclass(frozen=True)
class CheckProgress:
    name: str
    kind: Literal["web", "tg"]
    status: Literal["fetching", "storing", "finished"]
    result: SourceCheckResult | None = None


@dataclass(frozen=True)
class DigestResult:
    title: str
    body: str


class CheckPipeline:
    def __init__(
        self,
        store: DatabaseStore,
        sources: list[SourceAdapter],
        *,
        media: MediaConfig | None = None,
    ) -> None:
        self.store = store
        self.sources = sources
        self.media = MediaStore(media) if media is not None else None

    def run(self, *, on_progress: Callable[[CheckProgress], None] | None = None) -> CheckResult:
        self.store.init_schema()
        records: list[Record] = []
        fetched_count = 0
        inserted_count = 0
        duplicate_count = 0
        inserted_ids: list[str] = []
        source_results: list[SourceCheckResult] = []
        for source in self.sources:
            if on_progress is not None:
                on_progress(CheckProgress(source.name, _source_kind(source), "fetching"))
            next_cursor = None
            is_cursor_source = isinstance(source, CursorSourceAdapter)
            previous_cursor = None
            if is_cursor_source:
                previous_cursor = self.store.get_source_cursor(source.name)
            try:
                if is_cursor_source:
                    fetch_result = source.fetch_since(previous_cursor)
                    fetched = fetch_result.records
                    next_cursor = fetch_result.cursor
                else:
                    fetched = source.fetch()
            except Exception as exc:
                source_results.append(
                    SourceCheckResult(
                        name=source.name,
                        fetched=0,
                        inserted=0,
                        duplicates=0,
                        kind=_source_kind(source),
                        cursor_status=(
                            "unsupported"
                            if not is_cursor_source
                            else "unchanged"
                            if previous_cursor is not None
                            else "none"
                        ),
                        error=f"{type(exc).__name__}: {exc}",
                    ),
                )
                if on_progress is not None:
                    on_progress(
                        CheckProgress(
                            source.name, _source_kind(source), "finished", source_results[-1]
                        )
                    )
                continue
            if on_progress is not None:
                on_progress(CheckProgress(source.name, _source_kind(source), "storing"))
            source_inserted = 0
            source_duplicates = 0
            fetched_count += len(fetched)
            media_candidates: list[Record] = []
            for record in fetched:
                result = self.store.add_record(record)
                stored_record = result.record
                media_candidates.append(stored_record)
                if self.media is not None and not isinstance(source, MediaSourceAdapter):
                    stored_record = self.media.enrich(stored_record, payload=record.payload)
                    if stored_record.images != result.record.images:
                        self.store.set_record_images(stored_record)
                if result.inserted:
                    inserted_count += 1
                    source_inserted += 1
                    inserted_ids.append(result.record.id)
                    records.append(stored_record)
                else:
                    duplicate_count += 1
                    source_duplicates += 1
            if next_cursor is not None:
                self.store.set_source_cursor(source.name, next_cursor)
            if self.media is not None and isinstance(source, MediaSourceAdapter):
                try:
                    enriched = source.enrich_media(media_candidates, self.media)
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Media retrieval failed for %s: %s", source.name, exc
                    )
                    enriched = []
                for item in enriched:
                    self.store.set_record_media(item)
                changed = {item.id: item for item in enriched}
                records = [changed.get(item.id, item) for item in records]
            cursor_status: Literal["unsupported", "none", "unchanged", "updated"]
            if not is_cursor_source:
                cursor_status = "unsupported"
            elif next_cursor is not None:
                cursor_status = "updated"
            elif previous_cursor is not None:
                cursor_status = "unchanged"
            else:
                cursor_status = "none"
            source_results.append(
                SourceCheckResult(
                    name=source.name,
                    fetched=len(fetched),
                    inserted=source_inserted,
                    duplicates=source_duplicates,
                    kind=_source_kind(source),
                    cursor_updated=next_cursor is not None,
                    cursor_status=cursor_status,
                ),
            )
            if on_progress is not None:
                on_progress(
                    CheckProgress(source.name, _source_kind(source), "finished", source_results[-1])
                )
        pending_refinement_total = self.store.count_unrefined_records()
        pending_refinement_new = self.store.count_unrefined_records(record_ids=inserted_ids)
        return CheckResult(
            fetched=fetched_count,
            inserted=inserted_count,
            duplicates=duplicate_count,
            records=records,
            pending_refinement_total=pending_refinement_total,
            pending_refinement_new=pending_refinement_new,
            sources=source_results,
        )


def _source_kind(source: SourceAdapter) -> Literal["web", "tg"]:
    return "tg" if getattr(source, "source_kind", None) == "tg" else "web"


class DigestService:
    def __init__(self, store: DatabaseStore) -> None:
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
        records = self.store.list_relevant_refinements(
            window_start=window_start,
            window_end=window_end,
            limit=limit,
        )

        if not records:
            body = f"No relevant records found for the next {window_days} day(s)."
        else:
            lines = []
            for record, refinement in records:
                label = record.title or record.kind
                source = f" ({record.source})" if record.source else ""
                category_text = _format_category_scores(refinement)
                relevance_text = _format_relevance_window(refinement)
                location_text = _format_location(refinement)
                summary = refinement.summary or record.text
                lines.append(
                    f"- {label}{source}{category_text}{relevance_text}{location_text}: {summary}",
                )
            body = "\n".join(lines)

        return DigestResult(title="Latest digest", body=body)


def _format_category_scores(refinement: Refinement) -> str:
    if not refinement.category_scores:
        return ""
    scores = ", ".join(
        f"{name}={score:.2f}"
        for name, score in sorted(
            refinement.category_scores.items(), key=lambda item: item[1], reverse=True
        )
        if score > 0
    )
    return f" [{scores}]" if scores else ""


def _format_relevance_window(refinement: Refinement) -> str:
    start = _local_datetime(refinement.relevant_from)
    end = _local_datetime(refinement.relevant_to)
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


def _format_location(refinement: Refinement) -> str:
    if not refinement.location or not refinement.location.strip():
        return ""
    return f" @ {refinement.location.strip()}"


def _local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(ZoneInfo(DEFAULT_SOURCE_TIMEZONE))
