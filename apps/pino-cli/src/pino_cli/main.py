from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pino_core import (
    ChatAgent,
    CheckPipeline,
    DigestService,
    LLMError,
    MemoryEntry,
    PinoConfig,
    SQLiteStore,
    build_llm_client,
    build_sources,
    build_tools,
    load_config,
)

app = typer.Typer(no_args_is_help=True)
memory_app = typer.Typer(no_args_is_help=True)
sources_app = typer.Typer(no_args_is_help=True)
app.add_typer(memory_app, name="memory")
app.add_typer(sources_app, name="sources")

console = Console()


def get_config(path: Path | None) -> PinoConfig:
    return load_config(path)


def get_store(config: PinoConfig) -> SQLiteStore:
    store = SQLiteStore(config.storage.path)
    store.init_schema()
    return store


@app.command()
def check(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Fetch configured sources and store records."""
    config = get_config(config_path)
    store = get_store(config)
    pipeline = CheckPipeline(store=store, sources=build_sources(config.sources))
    records = pipeline.run()
    console.print(f"Captured {len(records)} record(s).")


@app.command()
def digest(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 20,
) -> None:
    """Create and print a digest from recent records."""
    config = get_config(config_path)
    store = get_store(config)
    artifact = DigestService(store).create_digest(limit=limit)
    console.rule(artifact.title)
    console.print(artifact.body)


@app.command()
def chat(
    message: Annotated[str | None, typer.Option("--message", "-m")] = None,
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Start interactive chat or send a single chat message."""
    config = get_config(config_path)
    store = get_store(config)
    sources = build_sources(config.sources)
    agent = ChatAgent(
        store=store,
        provider=build_llm_client(config.llm),
        tools=build_tools(store, sources),
        config=config.chat,
    )

    if message:
        result = respond_or_exit(agent, message)
        console.print(result.content)
        return

    console.print("Pino chat. Type /exit to quit.")
    while True:
        user_input = console.input("[bold]Boss[/bold]> ").strip()
        if user_input in {"/exit", "/quit"}:
            return
        if not user_input:
            continue
        result = respond_or_exit(agent, user_input)
        console.print(result.content)


def respond_or_exit(agent: ChatAgent, user_input: str):
    try:
        return agent.respond(user_input)
    except LLMError as exc:
        print_provider_error(exc)
        raise typer.Exit(code=1) from exc


def print_provider_error(exc: LLMError) -> None:
    table = Table("Field", "Value")
    table.add_row("provider", exc.provider)
    table.add_row("model", exc.model)
    table.add_row("url", exc.url)
    if exc.status_code is not None:
        table.add_row("status", str(exc.status_code))
    if exc.request:
        table.add_row("request", json_dumps(exc.request))

    console.print(Panel(table, title="LLM provider error", border_style="red"))
    if exc.response_body:
        console.print(Panel(exc.response_body, title="Response body", border_style="red"))


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


@memory_app.command("add")
def memory_add(
    content: Annotated[str, typer.Argument()],
    tags: Annotated[list[str] | None, typer.Option("--tag", "-t")] = None,
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Add an active memory entry."""
    config = get_config(config_path)
    store = get_store(config)
    memory = MemoryEntry(content=content, tags=tags or [])
    store.add_memory(memory)
    console.print(f"Added memory {memory.id}.")


@memory_app.command("list")
def memory_list(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 50,
) -> None:
    """List active memory entries."""
    config = get_config(config_path)
    store = get_store(config)
    rows = store.list_memory(limit=limit)
    table = Table("Created", "Tags", "Content")
    for row in rows:
        table.add_row(row.created_at.isoformat(), ", ".join(row.tags), row.content)
    console.print(table)


@sources_app.command("list")
def sources_list(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """List configured source adapters."""
    config = get_config(config_path)
    table = Table("Name", "Type", "Status")
    for source in config.sources:
        table.add_row(source.name, source.type, "enabled" if source.enabled else "disabled")
    console.print(table)
