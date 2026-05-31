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
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class MemoryEntry(BaseModel):
    """Long-lived active memory available to future Pino decisions."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    content: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """Durable chat history message exchanged by the user, Pino, or tools."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


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
    location: str | None = None
    category_scores: dict[str, float] = Field(default_factory=dict)
    embedding: list[float] | None = None
    refiner: str
    refined_at: datetime = Field(default_factory=utc_now)
    debug: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relevant_from", "relevant_to", "refined_at")
    @classmethod
    def _assume_utc_for_naive_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @field_validator("category_scores")
    @classmethod
    def _validate_category_scores(cls, value: dict[str, float]) -> dict[str, float]:
        return {key: max(0.0, min(1.0, float(score))) for key, score in value.items()}


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
