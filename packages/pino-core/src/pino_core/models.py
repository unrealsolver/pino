from __future__ import annotations

from hashlib import sha256
import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    kind: str
    source: str
    external_id: str | None = None
    fingerprint: str | None = None
    title: str | None = None
    text: str
    url: str | None = None
    observed_at: datetime | None = None
    captured_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    def with_fingerprint(self) -> Record:
        if self.fingerprint:
            return self
        return self.model_copy(update={"fingerprint": compute_record_fingerprint(self)})


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    kind: str
    title: str
    body: str
    created_at: datetime = Field(default_factory=utc_now)
    record_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class MemoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    content: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class Evaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


def compute_record_fingerprint(record: Record) -> str:
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
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_url(value: str) -> str:
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
