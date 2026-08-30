from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pino_llm import LLMClient, LLMMessage

from pino_core.config import RefinementConfig
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import Record, Refinement
from pino_core.schedules import normalize_schedule
from pino_core.storage import DatabaseStore


@dataclass(frozen=True)
class RefinementRunResult:
    requested: int
    refined: int
    items: int
    skipped: int


@dataclass(frozen=True)
class RefinementDebugResult:
    record: Record
    messages: list[LLMMessage]
    raw_response: str
    reasoning: str | None
    parsed_response: dict[str, Any]
    refinements: list[Refinement]
    error: str | None = None


@dataclass(frozen=True)
class RefinementProgress:
    status: Literal["selected", "refining", "refined", "skipped"]
    total: int
    index: int | None = None
    record: Record | None = None
    refinements: list[Refinement] | None = None
    reason: str | None = None


class RefinementResponseError(RuntimeError):
    """Raised when the model does not return usable refinement items."""


class RefinementService:
    """Extract reusable normalized items from captured records."""

    def __init__(
        self,
        store: DatabaseStore,
        client: LLMClient,
        config: RefinementConfig,
    ) -> None:
        self.store = store
        self.client = client
        self.config = config
        self._static_system_prompt = render_refinement_system_prompt(config)

    def refine_pending(
        self,
        limit: int | None = None,
        *,
        on_progress: Callable[[RefinementProgress], None] | None = None,
    ) -> RefinementRunResult:
        self.store.init_schema()
        records = self.store.list_unrefined_records(limit=limit or self.config.batch_size)
        total = len(records)
        _emit_progress(on_progress, RefinementProgress(status="selected", total=total))
        refined = 0
        item_count = 0
        skipped = 0

        for index, record in enumerate(records, start=1):
            _emit_progress(
                on_progress,
                RefinementProgress(status="refining", total=total, index=index, record=record),
            )
            if self.store.list_refinements(record.id):
                skipped += 1
                _emit_progress(
                    on_progress,
                    RefinementProgress(
                        status="skipped",
                        total=total,
                        index=index,
                        record=record,
                        reason="already refined",
                    ),
                )
                continue
            try:
                refinements = self.refine_record(record)
            except RefinementResponseError:
                skipped += 1
                _emit_progress(
                    on_progress,
                    RefinementProgress(
                        status="skipped",
                        total=total,
                        index=index,
                        record=record,
                        reason="unusable model response",
                    ),
                )
                continue
            self.store.replace_refinements(record.id, refinements)
            refined += 1
            item_count += len(refinements)
            _emit_progress(
                on_progress,
                RefinementProgress(
                    status="refined",
                    total=total,
                    index=index,
                    record=record,
                    refinements=refinements,
                ),
            )

        return RefinementRunResult(
            requested=total, refined=refined, items=item_count, skipped=skipped
        )

    def refine_record(self, record: Record) -> list[Refinement]:
        raw_response = self.client.complete(
            self._record_messages(record),
            operation="refinement.extract",
        )
        data = _parse_json_object(raw_response)
        raw_items = data.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise RefinementResponseError("refinement response is missing items")
        raw_items = _coalesce_recurring_items(raw_items)
        refinements = [
            self._build_refinement(record, item_index, raw_item)
            for item_index, raw_item in enumerate(raw_items)
            if isinstance(raw_item, dict)
        ]
        if not refinements:
            raise RefinementResponseError("refinement response has no usable items")
        return refinements

    def debug_refine_record(self, record: Record) -> RefinementDebugResult:
        messages = self._record_messages(record)
        raw_response = self.client.complete(messages, operation="refinement.extract")
        data = _parse_json_object(raw_response)
        raw_items = data.get("items")
        refinements: list[Refinement] = []
        error: str | None = None
        if not isinstance(raw_items, list) or not raw_items:
            error = "refinement response is missing items"
        else:
            raw_items = _coalesce_recurring_items(raw_items)
            refinements = [
                self._build_refinement(record, item_index, raw_item)
                for item_index, raw_item in enumerate(raw_items)
                if isinstance(raw_item, dict)
            ]
            if not refinements:
                error = "refinement response has no usable items"
        return RefinementDebugResult(
            record=record,
            messages=messages,
            raw_response=raw_response,
            reasoning=_client_reasoning(self.client),
            parsed_response=data,
            refinements=refinements,
            error=error,
        )

    def _build_refinement(
        self,
        record: Record,
        item_index: int,
        raw_item: dict[str, Any],
    ) -> Refinement:
        return Refinement(
            record_id=record.id,
            item_index=item_index,
            schema_version=self.config.schema_version,
            taxonomy_version=self.config.taxonomy_version,
            content_kind=_content_kind(raw_item.get("content_kind")),
            summary=_optional_string(raw_item.get("summary")),
            relevant_from=_optional_datetime(raw_item.get("relevant_from")),
            relevant_to=_optional_datetime(raw_item.get("relevant_to")),
            schedule=_optional_schedule(raw_item.get("schedule")),
            location=_optional_string(raw_item.get("location")),
            category_scores=_category_scores(raw_item.get("category_scores"), self.config),
            refiner=f"llm:{self.config.model}",
            debug={"raw": raw_item},
        )

    def _system_prompt(self) -> str:
        return self._static_system_prompt

    def _record_prompt(self, record: Record) -> str:
        record_payload = {
            "publication_date": _publication_date(record),
            "kind": record.kind,
            "source": record.source,
            "title": record.title,
            "text": record.text,
            "url": record.url,
        }
        semantic_payload = _semantic_record_payload(record.payload)
        if semantic_payload:
            record_payload["payload"] = semantic_payload
        return json.dumps(_drop_empty_values(record_payload), ensure_ascii=False, indent=2)

    def _record_messages(self, record: Record) -> list[LLMMessage]:
        return [
            LLMMessage(role="system", content=self._system_prompt()),
            LLMMessage(role="user", content=self._record_prompt(record)),
        ]


def render_refinement_system_prompt(config: RefinementConfig) -> str:
    categories = "\n".join(
        f"- {category.name}: {category.description}" for category in config.categories
    )
    return (
        "You refine captured source records into reusable normalized items.\n"
        "Do not personalize output for one user's goals. Evaluate multilingual text.\n"
        "Return strict JSON only. No markdown, no prose outside JSON.\n"
        "Prefer one item with a recurrence schedule for repeated instances of the same event.\n"
        "Only return multiple items when the source describes genuinely different events.\n"
        "Use ISO 8601 timestamps with timezone offsets outside schedule. Use null when unknown.\n"
        "When publication_date is present, use it to resolve today, tomorrow, weekdays, and omitted years.\n"
        "Do not calculate, verify, or correct weekdays from date lists; preserve source dates, weekdays, and recurrence claims as written.\n"
        "relevant_from is the earliest known start or active searchable datetime for the normalized item.\n"
        "relevant_to is the latest known end or active searchable datetime for the normalized item.\n"
        "Use schedule kind occurrences for one or more explicit finite dates and recurrence for a stated weekly pattern.\n"
        "Use only the fields for the selected schedule kind; do not mix occurrences and recurrence fields.\n"
        "For scheduled items, set relevant_from and relevant_to to null; Pino derives the searchable envelope from schedule.\n"
        "Schedule occurrence datetimes and recurrence times are local to the schedule timezone and do not include UTC offsets.\n"
        "Use schedule null only when no schedule or recurrence can be inferred.\n"
        "Use only configured category keys with positive evidence and scores from 0 to 1; omit zero-score categories.\n\n"
        "Categories:\n"
        f"{categories}\n\n"
        "Response JSON object shape:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "content_kind": "event|advertisement|announcement|non_event|unknown",\n'
        '      "summary": "concise normalized summary",\n'
        '      "relevant_from": "ISO 8601 timestamp or null",\n'
        '      "relevant_to": "ISO 8601 timestamp or null",\n'
        '      "schedule": null | {\n'
        '        "version": 1,\n'
        '        "timezone": "IANA timezone, e.g. Europe/Vilnius",\n'
        '        "kind": "occurrences",\n'
        '        "occurrences": [{"start": "local YYYY-MM-DDTHH:MM", "end": "local YYYY-MM-DDTHH:MM or null"}],\n'
        '        "source_text": "source schedule wording, optional"\n'
        '      } | {\n'
        '        "version": 1,\n'
        '        "timezone": "IANA timezone, e.g. Europe/Vilnius",\n'
        '        "kind": "recurrence",\n'
        '        "frequency": "weekly",\n'
        '        "from": "inclusive local YYYY-MM-DD",\n'
        '        "until": "inclusive local YYYY-MM-DD or null",\n'
        '        "rules": [{"weekdays": ["monday|tuesday|wednesday|thursday|friday|saturday|sunday"], "start": "HH:MM", "end": "HH:MM or null"}],\n'
        '        "source_text": "source schedule wording, optional"\n'
        "      },\n"
        '      "location": "venue or useful human-readable place, or null",\n'
        '      "category_scores": {"category_name": 0.0}\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def _coalesce_recurring_items(raw_items: list[Any]) -> list[Any]:
    groups: dict[tuple[Any, ...], list[tuple[int, dict[str, Any], _Occurrence]]] = {}
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            continue
        occurrence = _raw_occurrence(raw_item)
        key = _recurrence_group_key(raw_item, occurrence)
        if key is None or occurrence is None:
            continue
        groups.setdefault(key, []).append((index, raw_item, occurrence))

    collapsed_by_index: dict[int, dict[str, Any]] = {}
    skipped_indexes: set[int] = set()
    for rows in groups.values():
        collapsed = _collapse_weekly_group(rows)
        if collapsed is None:
            continue
        first_index = rows[0][0]
        collapsed_by_index[first_index] = collapsed
        skipped_indexes.update(index for index, _item, _occurrence in rows[1:])

    if not collapsed_by_index:
        return raw_items
    return [
        collapsed_by_index.get(index, raw_item)
        for index, raw_item in enumerate(raw_items)
        if index not in skipped_indexes
    ]


@dataclass(frozen=True)
class _Occurrence:
    start: datetime
    end: datetime | None
    day_code: str
    start_time: str
    end_time: str | None


def _raw_occurrence(raw_item: dict[str, Any]) -> _Occurrence | None:
    start = _optional_datetime(raw_item.get("relevant_from"))
    if start is None:
        return None
    end = _optional_datetime(raw_item.get("relevant_to"))
    timezone_info = ZoneInfo(DEFAULT_SOURCE_TIMEZONE)
    local_start = start.astimezone(timezone_info)
    local_end = end.astimezone(timezone_info) if end is not None else None
    return _Occurrence(
        start=start,
        end=end,
        day_code=_weekday_code(local_start),
        start_time=f"{local_start:%H:%M}",
        end_time=f"{local_end:%H:%M}" if local_end is not None else None,
    )


def _recurrence_group_key(
    raw_item: dict[str, Any],
    occurrence: _Occurrence | None,
) -> tuple[Any, ...] | None:
    if occurrence is None or normalize_schedule(raw_item.get("schedule")) is not None:
        return None
    return (
        _optional_string(raw_item.get("content_kind")) or "unknown",
        _normalized_key_text(raw_item.get("summary")),
        _normalized_key_text(raw_item.get("location")),
        _normalized_category_scores(raw_item.get("category_scores")),
        occurrence.day_code,
        occurrence.start_time,
        occurrence.end_time,
    )


def _collapse_weekly_group(
    rows: list[tuple[int, dict[str, Any], _Occurrence]],
) -> dict[str, Any] | None:
    if len(rows) < 3:
        return None
    rows = sorted(rows, key=lambda row: row[2].start)
    starts = [occurrence.start for _index, _item, occurrence in rows]
    if any((later.date() - earlier.date()).days % 7 != 0 for earlier, later in zip(starts, starts[1:])):
        return None

    first_item = dict(rows[0][1])
    last_occurrence = rows[-1][2]
    first_occurrence = rows[0][2]
    first_item["relevant_from"] = first_occurrence.start.isoformat()
    first_item["relevant_to"] = (
        last_occurrence.end.isoformat()
        if last_occurrence.end is not None
        else last_occurrence.start.isoformat()
    )
    timezone_info = ZoneInfo(DEFAULT_SOURCE_TIMEZONE)
    first_item["schedule"] = {
        "version": 1,
        "timezone": DEFAULT_SOURCE_TIMEZONE,
        "kind": "recurrence",
        "frequency": "weekly",
        "from": first_occurrence.start.astimezone(timezone_info).date().isoformat(),
        "until": last_occurrence.start.astimezone(timezone_info).date().isoformat(),
        "rules": [
            {
                "weekdays": [_weekday_name(first_occurrence.start, timezone_info)],
                "start": first_occurrence.start_time,
                "end": first_occurrence.end_time,
            }
        ],
    }
    return first_item


def _weekday_code(value: datetime) -> str:
    return ("MO", "TU", "WE", "TH", "FR", "SA", "SU")[value.weekday()]


def _weekday_name(value: datetime, timezone_info: ZoneInfo) -> str:
    local_value = value.astimezone(timezone_info)
    return (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    )[local_value.weekday()]


def _normalized_key_text(value: Any) -> str | None:
    text = _optional_string(value)
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).casefold()


def _normalized_category_scores(value: Any) -> str:
    if not isinstance(value, dict):
        return "{}"
    comparable = {
        str(key): float(score)
        for key, score in value.items()
        if isinstance(score, int | float)
    }
    return json.dumps(comparable, sort_keys=True, separators=(",", ":"))


_REFINEMENT_PAYLOAD_KEYS = {
    "date",
    "display_time",
    "location",
    "location_scopes",
    "source_date",
    "source_time",
    "timezone",
}


def _publication_date(record: Record) -> str | None:
    posted_at = _optional_datetime(record.payload.get("posted_at_utc"))
    if posted_at is None:
        return None
    return posted_at.astimezone(ZoneInfo(DEFAULT_SOURCE_TIMEZONE)).date().isoformat()


def _semantic_record_payload(value: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty_values(
        {
            key: item
            for key, item in value.items()
            if key in _REFINEMENT_PAYLOAD_KEYS
        }
    )


def _drop_empty_values(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != "" and item != [] and item != {}
    }


def build_refinement_llm_config(config, refinement_config: RefinementConfig):
    return config.model_copy(
        update={
            "model": refinement_config.model,
            "temperature": 0.0,
        },
    )


def _parse_json_object(raw_response: str) -> dict[str, Any]:
    stripped = raw_response.strip()
    parsed_objects: list[dict[str, Any]] = []
    for candidate in (stripped, *_json_object_candidates(stripped)):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            parsed_objects.append(parsed)
    for parsed in parsed_objects:
        if isinstance(parsed.get("items"), list):
            return parsed
    if parsed_objects:
        return parsed_objects[0]
    return {}


def _client_reasoning(client: LLMClient) -> str | None:
    value = getattr(client, "last_reasoning", None)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _json_object_candidates(value: str) -> list[str]:
    candidates: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(value):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
            continue
        if char != "}" or depth == 0:
            continue

        depth -= 1
        if depth == 0 and start is not None:
            candidates.append(value[start : index + 1])
            start = None

    return candidates


def _content_kind(value: Any) -> str:
    text = str(value or "unknown").strip()
    if text in {"event", "advertisement", "announcement", "non_event", "unknown"}:
        return text
    return "unknown"


def _category_scores(value: Any, config: RefinementConfig) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    allowed = {category.name for category in config.categories}
    scores: dict[str, float] = {}
    for key, raw_score in value.items():
        if key not in allowed:
            continue
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        scores[str(key)] = max(0.0, min(1.0, score))
    return scores


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_datetime(value: Any) -> datetime | None:
    text = _optional_string(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional_schedule(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _emit_progress(
    on_progress: Callable[[RefinementProgress], None] | None,
    progress: RefinementProgress,
) -> None:
    if on_progress is not None:
        on_progress(progress)
