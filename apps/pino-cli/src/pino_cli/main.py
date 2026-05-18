from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pino_core import CheckPipeline, DigestService, MemoryEntry, SQLiteStore
from pino_core.sources import StaticYamlSource

app = typer.Typer(no_args_is_help=True)
memory_app = typer.Typer(no_args_is_help=True)
sources_app = typer.Typer(no_args_is_help=True)
app.add_typer(memory_app, name="memory")
app.add_typer(sources_app, name="sources")

console = Console()
DEFAULT_DB = Path(".pino/pino.sqlite")
DEFAULT_SOURCE = Path("samples/fake-source.yaml")


def get_store(db: Path) -> SQLiteStore:
    store = SQLiteStore(db)
    store.init_schema()
    return store


@app.command()
def check(
    source: Annotated[Path, typer.Option("--source", "-s")] = DEFAULT_SOURCE,
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_DB,
) -> None:
    """Fetch records from a static source and store them."""
    store = get_store(db)
    pipeline = CheckPipeline(store=store, sources=[StaticYamlSource(source)])
    records = pipeline.run()
    console.print(f"Captured {len(records)} record(s).")


@app.command()
def digest(
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_DB,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 20,
) -> None:
    """Create and print a digest from recent records."""
    store = get_store(db)
    artifact = DigestService(store).create_digest(limit=limit)
    console.rule(artifact.title)
    console.print(artifact.body)


@memory_app.command("add")
def memory_add(
    content: Annotated[str, typer.Argument()],
    tags: Annotated[list[str] | None, typer.Option("--tag", "-t")] = None,
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_DB,
) -> None:
    """Add an active memory entry."""
    store = get_store(db)
    memory = MemoryEntry(content=content, tags=tags or [])
    store.add_memory(memory)
    console.print(f"Added memory {memory.id}.")


@memory_app.command("list")
def memory_list(
    db: Annotated[Path, typer.Option("--db")] = DEFAULT_DB,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 50,
) -> None:
    """List active memory entries."""
    store = get_store(db)
    rows = store.list_memory(limit=limit)
    table = Table("Created", "Tags", "Content")
    for row in rows:
        table.add_row(row.created_at.isoformat(), ", ".join(row.tags), row.content)
    console.print(table)


@sources_app.command("list")
def sources_list() -> None:
    """List currently available source adapters."""
    table = Table("Adapter", "Status")
    table.add_row("static-yaml", "available")
    console.print(table)

