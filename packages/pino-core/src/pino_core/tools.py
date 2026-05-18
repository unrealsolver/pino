from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pino_core.models import MemoryEntry
from pino_core.pipeline import CheckPipeline, DigestService
from pino_core.sources import SourceAdapter
from pino_core.storage import SQLiteStore


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[[dict[str, Any]], str]


def build_tools(store: SQLiteStore, sources: list[SourceAdapter]) -> dict[str, Tool]:
    def memory_add(arguments: dict[str, Any]) -> str:
        content = str(arguments.get("content", "")).strip()
        if not content:
            return "memory.add failed: content is required."
        tags = arguments.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        memory = MemoryEntry(content=content, tags=[str(tag) for tag in tags])
        store.add_memory(memory)
        return f"Added active memory: {memory.content}"

    def memory_list(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 20))
        memories = store.list_memory(limit=limit)
        if not memories:
            return "No active memory entries."
        return "\n".join(f"- {memory.content}" for memory in memories)

    def records_list(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 10))
        records = store.list_records(limit=limit)
        if not records:
            return "No records captured yet."
        return "\n".join(f"- {record.title or record.kind}: {record.text}" for record in records)

    def digest_create(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 20))
        return DigestService(store).create_digest(limit=limit).body

    def sources_check(arguments: dict[str, Any]) -> str:
        records = CheckPipeline(store=store, sources=sources).run()
        return f"Captured {len(records)} record(s)."

    tools = [
        Tool("memory.add", "Add an active memory entry. Arguments: content, tags.", memory_add),
        Tool("memory.list", "List active memory entries. Arguments: limit.", memory_list),
        Tool("records.list", "List recent captured records. Arguments: limit.", records_list),
        Tool("digest.create", "Create a digest from recent records. Arguments: limit.", digest_create),
        Tool("sources.check", "Fetch configured sources and store records.", sources_check),
    ]
    return {tool.name: tool for tool in tools}


def describe_tools(tools: dict[str, Tool]) -> str:
    return "\n".join(f"- {tool.name}: {tool.description}" for tool in tools.values())

