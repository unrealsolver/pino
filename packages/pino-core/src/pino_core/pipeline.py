from __future__ import annotations

from pino_core.models import Artifact, Record
from pino_core.sources import SourceAdapter
from pino_core.storage import SQLiteStore


class CheckPipeline:
    def __init__(self, store: SQLiteStore, sources: list[SourceAdapter]) -> None:
        self.store = store
        self.sources = sources

    def run(self) -> list[Record]:
        self.store.init_schema()
        records: list[Record] = []
        for source in self.sources:
            fetched = source.fetch()
            for record in fetched:
                self.store.add_record(record)
            records.extend(fetched)
        return records


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

