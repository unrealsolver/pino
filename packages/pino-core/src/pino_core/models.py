from __future__ import annotations

import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


def ensure_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Record(BaseModel):
    """Persistable unit of captured or derived information.

    Records are intentionally generic. Source adapters can provide structured
    details in ``payload`` and identity hints in ``external_id`` without forcing
    source-specific concepts into the core schema.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    kind: str
    source: str
    external_id: str | None = None
    fingerprint: str | None = None
    title: str | None = None
    text: str
    url: str | None = None
    captured_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    def with_fingerprint(self) -> Record:
        """Return this record with a deterministic idempotency fingerprint."""
        if self.fingerprint:
            return self
        return self.model_copy(update={"fingerprint": compute_record_fingerprint(self)})

    @field_validator("captured_at")
    @classmethod
    def _assume_utc_for_naive_datetimes(cls, value: datetime | None) -> datetime | None:
        return ensure_utc_datetime(value)


class MemoryEntry(BaseModel):
    """Long-lived active memory available to future Pino decisions."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    content: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _normalize_datetimes_to_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc_datetime(value)


class ChatMessage(BaseModel):
    """Durable chat history message exchanged by the user, Pino, or tools."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at")
    @classmethod
    def _normalize_datetimes_to_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc_datetime(value)


class Refinement(BaseModel):
    """Reusable normalized item extracted from a captured record."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    record_id: str
    item_index: int = Field(default=0, ge=0)
    schema_version: int = Field(default=1, ge=1)
    taxonomy_version: int = Field(default=1, ge=1)
    content_kind: Literal["event", "advertisement", "announcement", "non_event", "unknown"] = (
        "unknown"
    )
    summary: str | None = None
    relevant_from: datetime | None = None
    relevant_to: datetime | None = None
    schedule: dict[str, Any] | None = None
    location: str | None = None
    category_scores: dict[str, float] = Field(default_factory=dict)
    embedding: list[float] | None = None
    refiner: str
    refined_at: datetime = Field(default_factory=utc_now)
    debug: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relevant_from", "relevant_to", "refined_at")
    @classmethod
    def _assume_utc_for_naive_datetimes(cls, value: datetime | None) -> datetime | None:
        return ensure_utc_datetime(value)

    @field_validator("category_scores")
    @classmethod
    def _validate_category_scores(cls, value: dict[str, float]) -> dict[str, float]:
        return {key: max(0.0, min(1.0, float(score))) for key, score in value.items()}

    @field_validator("schedule", mode="before")
    @classmethod
    def _validate_schedule(cls, value: Any) -> dict[str, Any] | None:
        return normalize_schedule(value)


class LLMUsageEvent(BaseModel):
    """Persisted token usage for one completed LLM call."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    created_at: datetime = Field(default_factory=utc_now)
    provider: str
    model: str
    operation: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    duration_ms: int = Field(ge=0)

    @field_validator("created_at")
    @classmethod
    def _normalize_created_at_to_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc_datetime(value)


def compute_record_fingerprint(record: Record) -> str:
    """Compute deterministic storage identity for a record.

    The fingerprint is deliberately non-semantic: prefer explicit source
    identity, then URL identity, then normalized text. Semantic duplicate
    detection belongs in a later refinement layer.
    """
    if record.external_id:
        parts = [record.source, record.kind, record.external_id]
    elif record.url:
        parts = [record.source, record.kind, _normalize_url(record.url)]
    else:
        parts = [
            record.source,
            record.kind,
            _normalize_text(record.title or ""),
            _normalize_text(record.text),
        ]
    raw = "\x1f".join(_normalize_text(part) for part in parts)
    return sha256(raw.encode("utf-8")).hexdigest()


def normalize_schedule(value: Any) -> dict[str, Any] | None:
    if value is None or not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if kind not in {"opening_hours", "recurrence"}:
        return None
    timezone_name = _non_empty_string(value.get("timezone"))
    if timezone_name is None:
        return None
    raw_rules = value.get("rules")
    if not isinstance(raw_rules, list):
        return None
    rules = [_normalize_schedule_rule(rule) for rule in raw_rules]
    rules = [rule for rule in rules if rule is not None]
    if not rules:
        return None
    schedule: dict[str, Any] = {
        "timezone": timezone_name,
        "kind": kind,
        "rules": rules,
        "exceptions": value.get("exceptions") if isinstance(value.get("exceptions"), list) else [],
    }
    source_text = _non_empty_string(value.get("source_text"))
    if source_text is not None:
        schedule["source_text"] = source_text
    return schedule


def _normalize_schedule_rule(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or "frequency" in value:
        return None
    raw_days = value.get("days")
    if not isinstance(raw_days, list):
        return None
    days = [_normalize_weekday(day) for day in raw_days]
    days = [day for day in days if day is not None]
    if not days:
        return None
    start = _non_empty_string(value.get("start"))
    if start is None or not _is_hhmm_time(start):
        return None
    end = _non_empty_string(value.get("end"))
    if end is not None and not _is_hhmm_time(end):
        return None
    return {"days": days, "start": start, "end": end}


_WEEKDAY_CODES = {
    "MO": "MO",
    "MONDAY": "MO",
    "TU": "TU",
    "TUESDAY": "TU",
    "WE": "WE",
    "WEDNESDAY": "WE",
    "TH": "TH",
    "THURSDAY": "TH",
    "FR": "FR",
    "FRIDAY": "FR",
    "SA": "SA",
    "SATURDAY": "SA",
    "SU": "SU",
    "SUNDAY": "SU",
}


def _normalize_weekday(value: Any) -> str | None:
    return _WEEKDAY_CODES.get(str(value).strip().upper())


def _non_empty_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_hhmm_time(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2:
        return False
    try:
        hour, minute = (int(part) for part in parts)
    except ValueError:
        return False
    return 0 <= hour <= 23 and 0 <= minute <= 59


def _normalize_text(value: str) -> str:
    """Normalize text for deterministic identity comparisons."""
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_url(value: str) -> str:
    """Normalize URLs enough for first-pass source idempotency."""
    split = urlsplit(value.strip())
    query = [
        (key, val)
        for key, val in parse_qsl(split.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    normalized = urlunsplit(
        (
            split.scheme.lower(),
            split.netloc.lower(),
            split.path.rstrip("/"),
            urlencode(query),
            "",
        ),
    )
    return normalized
