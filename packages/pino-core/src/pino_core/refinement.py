from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pino_llm import LLMClient, LLMMessage

from pino_core.config import RefinementConfig
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import Record, Refinement
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
    """Raised when the model does not return a usable refinement item."""


_CONTENT_KINDS = {"event", "advertisement", "announcement", "non_event", "unknown"}


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
        if error := _response_error(data):
            raise RefinementResponseError(error)
        if not _is_refinement_item(data):
            raise RefinementResponseError("refinement response is missing an item")
        return [self._build_refinement(record, data)]

    def debug_refine_record(self, record: Record) -> RefinementDebugResult:
        messages = self._record_messages(record)
        raw_response = self.client.complete(messages, operation="refinement.extract")
        data = _parse_json_object(raw_response)
        refinements: list[Refinement] = []
        error = _response_error(data)
        if error is None:
            if _is_refinement_item(data):
                refinements = [self._build_refinement(record, data)]
            else:
                error = "refinement response is missing an item"
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
        raw_item: dict[str, Any],
    ) -> Refinement:
        return Refinement(
            record_id=record.id,
            item_index=0,
            schema_version=self.config.schema_version,
            taxonomy_version=self.config.taxonomy_version,
            content_kind=_content_kind(raw_item.get("content_kind")),
            summary=_optional_string(raw_item.get("summary")),
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
        'Return exactly one normalized item object. If one reliable item cannot be produced, return only {"error": "short reason"}. A non-event is still a valid item, not an error.\n'
        # Previous schedule instructions, retained for comparison:
        # "Prefer one item with a recurrence schedule for repeated instances of the same event.\n"
        # "Only return multiple items when the source describes genuinely different events.\n"
        # "Use ISO 8601 timestamps with timezone offsets outside schedule. Use null when unknown.\n"
        # "When publication_date is present, use it to resolve today, tomorrow, weekdays, and omitted years.\n"
        # "Do not calculate, verify, or correct weekdays from date lists; preserve source dates, weekdays, and recurrence claims as written.\n"
        # "relevant_from is the earliest known start or active searchable datetime for the normalized item.\n"
        # "relevant_to is the latest known end or active searchable datetime for the normalized item.\n"
        # "Use schedule kind occurrences for one or more explicit finite dates and recurrence for a stated weekly pattern.\n"
        # "Use only the fields for the selected schedule kind; do not mix occurrences and recurrence fields.\n"
        # "For scheduled items, set relevant_from and relevant_to to null; Pino derives the searchable envelope from schedule.\n"
        # "Schedule occurrence datetimes and recurrence times are local to the schedule timezone and do not include UTC offsets.\n"
        # "Use schedule null only when no schedule or recurrence can be inferred.\n"
        "Event and schedule rules; apply them in order:\n"
        "1. The input must describe one coherent item. If it contains genuinely different events that require splitting, return the error object. If the source is not an event, use the appropriate non-event content_kind and schedule null. An event is one coherent activity or program that occurs at one or more times. Prefer one item with a recurrence schedule for repeated instances of the same event. A single program may have several explicitly timed sessions; represent each session separately within its schedule.\n"
        "2. schedule is the only output field for event timing. Do not turn a publication timestamp, a bare time, a contextual date, or a non-event validity or availability period into an event occurrence. If the source provides enough evidence to determine event dates or a repeated pattern, schedule MUST be non-null.\n"
        "3. Use schedule kind occurrences for one or more explicitly stated finite dates without a recurring pattern, and recurrence for a stated weekly pattern. Each explicitly stated session start is a separate occurrence. A later session start is not an end time for an earlier session.\n"
        "4. Recurrence requires an explicitly repeated weekly pattern. A weekday attached to one explicit date is descriptive and does not imply recurrence. Do not approximate a non-weekly pattern, such as a monthly or irregular pattern, as weekly recurrence; use its explicit occurrences when available, otherwise use schedule null.\n"
        "5. When a weekly pattern and explicit dates are both stated, use recurrence; the earliest and latest listed dates establish from and until unless the source explicitly states a broader active period. Recurrence from and until are inclusive boundaries of that stated period, not necessarily occurrence dates. Derive duration-based boundaries by calendar addition from the stated start. Treat a named period as a boundary only when the source explicitly names it; never infer one from the activity, venue, or seasonality.\n"
        "6. A time without a date or recurring pattern is insufficient for a schedule. Never use publication_date itself as the event occurrence date. When publication_date is present, it is the authoritative date anchor: an omitted year equals publication_date's year unless an explicit year or relative expression necessarily crosses a year boundary. Never choose a year from the model's current date, external knowledge, the URL, or weekday/date agreement, and never change a year merely to make a weekday match.\n"
        "7. Preserve every explicitly stated day, month, start time, and schedule claim. Copy only the weekdays explicitly belonging to a recurring pattern. Never invent an end time; derive one only from an explicit end or duration. Do not calculate, verify, or correct weekdays from date lists; preserve source dates, weekdays, and recurrence claims as written.\n"
        "8. Use only the fields for the selected schedule kind; do not mix occurrences and recurrence fields. Schedule occurrence datetimes and recurrence times are local to the schedule timezone and do not include UTC offsets.\n"
        "Before returning, verify event grouping; that every schedule is supported by event timing rather than contextual availability; that each explicit session start was preserved; that recurrence is explicit, weekly, and uses only stated weekdays and boundaries; that omitted years follow publication_date; that no date or end time was invented; and that the response is valid JSON with escaped strings and no duplicate keys.\n"
        "Use only configured category keys with positive evidence and scores from 0 to 1; omit zero-score categories.\n\n"
        "Categories:\n"
        f"{categories}\n\n"
        "Normalized item JSON object shape:\n"
        "{\n"
        '  "content_kind": "event|advertisement|announcement|non_event|unknown",\n'
        '  "summary": "concise normalized summary",\n'
        '  "schedule": null | {\n'
        '    "version": 1,\n'
        '    "timezone": "IANA timezone, e.g. Europe/Vilnius",\n'
        '    "kind": "occurrences",\n'
        '    "occurrences": [{"start": "local YYYY-MM-DDTHH:MM", "end": "local YYYY-MM-DDTHH:MM or null"}]\n'
        "  } | {\n"
        '    "version": 1,\n'
        '    "timezone": "IANA timezone, e.g. Europe/Vilnius",\n'
        '    "kind": "recurrence",\n'
        '    "frequency": "weekly",\n'
        '    "from": "inclusive local YYYY-MM-DD",\n'
        '    "until": "inclusive local YYYY-MM-DD or null",\n'
        '    "rules": [{"weekdays": ["monday|tuesday|wednesday|thursday|friday|saturday|sunday"], "start": "HH:MM", "end": "HH:MM or null"}]\n'
        "  },\n"
        '  "location": "venue or useful human-readable place, or null",\n'
        '  "category_scores": {"category_name": 0.0}\n'
        "}\n"
        "Error JSON object shape:\n"
        '{"error": "short reason"}'
    )


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
        {key: item for key, item in value.items() if key in _REFINEMENT_PAYLOAD_KEYS}
    )


def _drop_empty_values(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != "" and item != [] and item != {}
    }


def build_refinement_llm_config(config, refinement_config: RefinementConfig):
    return config.with_model(refinement_config.model)


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
        if _is_refinement_item(parsed) or _response_error(parsed) is not None:
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


def _is_refinement_item(value: dict[str, Any]) -> bool:
    return value.get("content_kind") in _CONTENT_KINDS


def _response_error(value: dict[str, Any]) -> str | None:
    reason = _optional_string(value.get("error"))
    if reason is None:
        return None
    return f"model could not refine record: {reason}"


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
    if text in _CONTENT_KINDS:
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
