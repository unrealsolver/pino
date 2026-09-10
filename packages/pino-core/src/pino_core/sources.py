from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

import yaml

from pino_core.config import SourceConfig
from pino_core.models import Record
from pino_core.media import MediaStore


class SourceAdapter(Protocol):
    name: str

    def fetch(self) -> list[Record]:
        """Fetch records from a source."""


@dataclass(frozen=True)
class CursorFetchResult:
    records: list[Record]
    cursor: str | None


@runtime_checkable
class CursorSourceAdapter(Protocol):
    name: str

    def fetch_since(self, cursor: str | None) -> CursorFetchResult:
        """Fetch records newer than a durable source cursor."""


SourceFactory = Callable[[SourceConfig], SourceAdapter]


@runtime_checkable
class MediaSourceAdapter(Protocol):
    def enrich_media(self, records: list[Record], media: MediaStore) -> list[Record]:
        """Return changed records after best-effort authenticated media retrieval."""


class SourceRegistry:
    """Resolve source config objects through registered factories."""

    def __init__(self) -> None:
        self._factories: dict[str, SourceFactory] = {}

    def register(self, source_type: str, factory: SourceFactory) -> None:
        """Register a factory for a source type."""
        self._factories[source_type] = factory

    def build(self, config: SourceConfig) -> SourceAdapter:
        """Build one source adapter from config."""
        try:
            factory = self._factories[config.type]
        except KeyError as exc:
            raise ValueError(f"Unsupported source type: {config.type}") from exc
        return factory(config)

    def build_many(self, configs: list[SourceConfig]) -> list[SourceAdapter]:
        """Build enabled source adapters from config."""
        return [self.build(config) for config in configs if config.enabled]


class StaticYamlSource:
    source_kind = "web"

    def __init__(self, path: Path, name: str = "static-yaml") -> None:
        self.path = path
        self.name = name

    def fetch(self) -> list[Record]:
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        raw_records = data.get("records", [])
        if not isinstance(raw_records, list):
            raise ValueError("Static source YAML must contain a 'records' list.")

        return [self._load_record(index, raw) for index, raw in enumerate(raw_records)]

    def _load_record(self, index: int, raw: Any) -> Record:
        if not isinstance(raw, dict):
            raise ValueError(f"Record #{index + 1} must be a mapping.")

        raw = dict(raw)
        raw.setdefault("kind", "note")
        raw.setdefault("source", self.name)
        raw.setdefault("provenance", {})
        raw["provenance"] = {
            "adapter": self.name,
            "path": str(self.path),
            "index": index,
            **raw["provenance"],
        }
        return Record.model_validate(raw)


def build_static_yaml_source(config: SourceConfig) -> SourceAdapter:
    """Build the static YAML source adapter from config."""
    if config.path is None:
        raise ValueError("static_yaml source requires path")
    return StaticYamlSource(config.path, name=config.name)
