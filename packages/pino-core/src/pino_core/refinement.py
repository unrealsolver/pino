from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pino_llm import LLMClient, LLMMessage

from pino_core.config import RefinementConfig
from pino_core.models import Record, Refinement, normalize_schedule
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
        raw_response = self.client.complete(self._record_messages(record))
        data = _parse_json_object(raw_response)
        raw_items = data.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise RefinementResponseError("refinement response is missing items")
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
        raw_response = self.client.complete(messages)
        data = _parse_json_object(raw_response)
        raw_items = data.get("items")
        refinements: list[Refinement] = []
        error: str | None = None
        if not isinstance(raw_items, list) or not raw_items:
            error = "refinement response is missing items"
        else:
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
        payload = {
            "id": record.id,
            "kind": record.kind,
            "source": record.source,
            "title": record.title,
            "text": record.text,
            "url": record.url,
            "payload": record.payload,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

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
        "A source record may describe multiple events: return one item per event.\n"
        "Use ISO 8601 timestamps with timezone offsets. Use null when unknown.\n"
        "For event schedules, use null when unavailable. If present, use only the documented schedule shapes and rules with days; do not include a frequency field.\n"
        "Use only configured category keys and scores from 0 to 1.\n\n"
        "Categories:\n"
        f"{categories}\n\n"
        "JSON schema:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "content_kind": "event|advertisement|announcement|non_event|unknown",\n'
        '      "summary": "concise normalized summary",\n'
        '      "relevant_from": "ISO 8601 timestamp or null",\n'
        '      "relevant_to": "ISO 8601 timestamp or null",\n'
        '      "schedule": null,\n'
        '      "location": "venue or useful human-readable place, or null",\n'
        '      "category_scores": {"category_name": 0.0}\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def build_refinement_llm_config(config, refinement_config: RefinementConfig):
    return config.model_copy(
        update={
            "model": refinement_config.model,
            "temperature": 0.0,
        },
    )


def _parse_json_object(raw_response: str) -> dict[str, Any]:
    stripped = raw_response.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


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
    return normalize_schedule(value)


def _emit_progress(
    on_progress: Callable[[RefinementProgress], None] | None,
    progress: RefinementProgress,
) -> None:
    if on_progress is not None:
        on_progress(progress)
