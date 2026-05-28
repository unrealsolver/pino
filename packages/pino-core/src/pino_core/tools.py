from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import Evaluation, MemoryEntry, Record, utc_now
from pino_core.pipeline import CheckPipeline, DigestService
from pino_core.sources import SourceAdapter
from pino_core.storage import RecordEvaluationStatus, SQLiteStore


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[[dict[str, Any]], str]


def build_tools(store: SQLiteStore, sources: list[SourceAdapter]) -> dict[str, Tool]:
    def memory_add(arguments: dict[str, Any]) -> str:
        content = str(arguments.get("content", "")).strip()
        if not content:
            return "memory.add failed: content is required."
        tags = arguments.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        memory = MemoryEntry(content=content, tags=[str(tag) for tag in tags])
        store.add_memory(memory)
        return f"Added active memory: {memory.content}"

    def memory_list(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 20))
        memories = store.list_memory(limit=limit)
        if not memories:
            return "No active memory entries."
        return "\n".join(f"- {memory.content}" for memory in memories)

    def records_list(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 10))
        rows = store.list_records_with_evaluation_status(limit=limit)
        if not rows:
            return "No records captured yet."
        return "\n".join(_format_record_with_status(row) for row in rows)

    def records_relevant(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 20))
        window_days = int(arguments.get("days", arguments.get("window_days", 14)))
        min_score = float(arguments.get("min_score", 0.0))
        goals = _coerce_goals(arguments.get("goals", []))
        window_start = utc_now()
        records = store.list_relevant_records_with_evaluations(
            window_start=window_start,
            window_end=window_start + timedelta(days=window_days),
            limit=max(limit * 3, limit),
        )
        filtered = [
            (record, evaluation)
            for record, evaluation in records
            if _matches_relevant_filters(evaluation, min_score=min_score, goals=goals)
        ][:limit]
        if not filtered:
            return f"No relevant records found for the next {window_days} day(s)."
        return "\n".join(
            _format_relevant_record(record, evaluation) for record, evaluation in filtered
        )

    def digest_create(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 20))
        window_days = int(arguments.get("days", arguments.get("window_days", 14)))
        return DigestService(store).create_digest(limit=limit, window_days=window_days).body

    def sources_check(arguments: dict[str, Any]) -> str:
        result = CheckPipeline(store=store, sources=sources).run()
        return (
            f"Fetched {result.fetched}; inserted {result.inserted}; "
            f"duplicates {result.duplicates}. "
            f"Evaluation pending: {result.pending_evaluation_total} total, "
            f"{result.pending_evaluation_new} new."
        )

    tools = [
        Tool("memory.add", "Add an active memory entry. Arguments JSON example: {\"content\": \"text\", \"tags\": [\"tag\"]}.", memory_add),
        Tool("memory.list", "List active memory entries. Arguments JSON example: {\"limit\": 20}.", memory_list),
        Tool(
            "records.relevant",
            "Preferred for event recommendations and upcoming/current plans. Returns relevance-windowed records with evaluation score, goal matches, local time, location, URL, and summary. Arguments JSON example: {\"limit\": 20, \"days\": 14, \"min_score\": 0.3, \"goals\": [\"metal_music\"]}.",
            records_relevant,
        ),
        Tool("records.list", "Raw recent records for inspection/debug only. Arguments JSON example: {\"limit\": 50}.", records_list),
        Tool(
            "digest.create",
            "Create a digest from relevant current/upcoming records. Arguments JSON example: {\"limit\": 20, \"days\": 14}.",
            digest_create,
        ),
        Tool("sources.check", "Fetch configured sources and store records. Arguments JSON example: {}.", sources_check),
    ]
    return {tool.name: tool for tool in tools}


def describe_tools(tools: dict[str, Tool]) -> str:
    return "\n".join(f"- {tool.name}: {tool.description}" for tool in tools.values())


def _coerce_goals(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _matches_relevant_filters(
    evaluation: Evaluation | None,
    *,
    min_score: float,
    goals: list[str],
) -> bool:
    if evaluation is None:
        return min_score <= 0 and not goals
    if evaluation.score < min_score:
        return False
    if goals and not set(goals).intersection(evaluation.goal_matches):
        return False
    return True


def _format_relevant_record(record: Record, evaluation: Evaluation | None) -> str:
    label = record.title or record.kind
    source = f" ({record.source})" if record.source else ""
    evaluation_text = _format_relevant_evaluation(evaluation)
    relevance_text = _format_relevance_window(record)
    location_text = _format_location(record)
    url_text = f" [url: {record.url}]" if record.url else ""
    summary = evaluation.summary if evaluation and evaluation.summary else record.text
    return f"- {label}{source}{evaluation_text}{relevance_text}{location_text}{url_text}: {summary}"


def _format_relevant_evaluation(evaluation: Evaluation | None) -> str:
    if evaluation is None:
        return " [unevaluated]"
    matches = f" {'/'.join(evaluation.goal_matches)}" if evaluation.goal_matches else ""
    return f" [score {evaluation.score:.2f}{matches}]"


def _format_record_with_status(row: RecordEvaluationStatus) -> str:
    record = row.record
    label = record.title or record.kind
    source = f" ({record.source})" if record.source else ""
    evaluation_text = _format_relevant_evaluation(row.evaluation)
    return f"- {label}{source}{evaluation_text}: {record.text}"


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
