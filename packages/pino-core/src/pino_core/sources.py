from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import yaml

from pino_core.models import Record


class SourceAdapter(Protocol):
    name: str

    def fetch(self) -> list[Record]:
        """Fetch records from a source."""


class StaticYamlSource:
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
