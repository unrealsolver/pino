from __future__ import annotations

from dataclasses import dataclass

from pino_core.models import Artifact, Record
from pino_core.sources import SourceAdapter
from pino_core.storage import SQLiteStore


@dataclass(frozen=True)
class CheckResult:
    fetched: int
    inserted: int
    duplicates: int
    records: list[Record]


class CheckPipeline:
    def __init__(self, store: SQLiteStore, sources: list[SourceAdapter]) -> None:
        self.store = store
        self.sources = sources

    def run(self) -> CheckResult:
        self.store.init_schema()
        records: list[Record] = []
        fetched_count = 0
        inserted_count = 0
        duplicate_count = 0
        for source in self.sources:
            fetched = source.fetch()
            fetched_count += len(fetched)
            for record in fetched:
                result = self.store.add_record(record)
                if result.inserted:
                    inserted_count += 1
                    records.append(result.record)
                else:
                    duplicate_count += 1
        return CheckResult(
            fetched=fetched_count,
            inserted=inserted_count,
            duplicates=duplicate_count,
            records=records,
        )


class DigestService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def create_digest(self, limit: int = 20) -> Artifact:
        self.store.init_schema()
        records = self.store.list_records(limit=limit)

        if not records:
            body = "No records captured yet."
        else:
            lines = []
            for record in records:
                label = record.title or record.kind
                source = f" ({record.source})" if record.source else ""
                lines.append(f"- {label}{source}: {record.text}")
            body = "\n".join(lines)

        artifact = Artifact(
            kind="digest",
            title="Latest digest",
            body=body,
            record_ids=[record.id for record in records],
        )
        self.store.add_artifact(artifact)
        return artifact
