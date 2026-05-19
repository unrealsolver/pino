from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pino_core import (
    ChatAgent,
    CheckPipeline,
    DigestService,
    EvaluationService,
    LLMError,
    MemoryEntry,
    PinoConfig,
    SQLiteStore,
    build_evaluation_llm_config,
    build_llm_client,
    build_sources,
    build_tools,
    load_config,
)

app = typer.Typer(no_args_is_help=True)
chat_app = typer.Typer(no_args_is_help=False, invoke_without_command=True)
memory_app = typer.Typer(no_args_is_help=True)
sources_app = typer.Typer(no_args_is_help=True)
app.add_typer(chat_app, name="chat")
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
    result = pipeline.run()
    console.print(
        f"Fetched {result.fetched}; inserted {result.inserted}; "
        f"duplicates {result.duplicates}.",
    )


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
    console.print(artifact.body, markup=False)


@app.command()
def evaluate(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    limit: Annotated[int | None, typer.Option("--limit", "-n", min=1)] = None,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Evaluate unevaluated records against configured goals."""
    config = get_config(config_path)
    llm_config = build_evaluation_llm_config(config.llm, config.evaluation)
    store = get_store(config)
    service = EvaluationService(
        store=store,
        client=build_llm_client(llm_config),
        config=config.evaluation,
    )
    result = service.evaluate_pending(limit=limit)
    if debug:
        table = Table("Field", "Value")
        table.add_row("provider", plain_text(llm_config.default_provider))
        table.add_row("model", plain_text(llm_config.selected_model()))
        table.add_row("requested", plain_text(result.requested))
        table.add_row("evaluated", plain_text(result.evaluated))
        table.add_row("skipped", plain_text(result.skipped))
        console.print(Panel(table, title="Evaluation debug", border_style="blue"))
    console.print(
        f"Requested {result.requested}; evaluated {result.evaluated}; skipped {result.skipped}.",
    )


@chat_app.callback(invoke_without_command=True)
def chat_main(
    ctx: typer.Context,
    message: Annotated[str | None, typer.Option("--message", "-m")] = None,
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    debug: Annotated[bool, typer.Option("--debug")] = False,
    history_limit: Annotated[int | None, typer.Option("--history-limit", min=0)] = None,
) -> None:
    """Start interactive chat or send a single chat message."""
    if ctx.invoked_subcommand is not None:
        return

    config = get_config(config_path)
    if history_limit is not None:
        config.chat.history_limit = history_limit
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
        if debug:
            print_chat_debug(config, result)
        console.print(result.content, markup=False)
        return

    console.print("Pino chat. Type /exit to quit.")
    if debug:
        print_chat_config_debug(config)
    while True:
        user_input = console.input("[bold]Boss[/bold]> ").strip()
        if user_input in {"/exit", "/quit"}:
            return
        if not user_input:
            continue
        result = respond_or_exit(agent, user_input)
        if debug:
            print_chat_debug(config, result)
        console.print(result.content, markup=False)


@chat_app.command("reset")
def chat_reset(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Clear stored chat history."""
    config = get_config(config_path)
    store = get_store(config)
    deleted = store.clear_chat_messages()
    console.print(f"Deleted {deleted} chat message(s).")


def respond_or_exit(agent: ChatAgent, user_input: str):
    try:
        return agent.respond(user_input)
    except LLMError as exc:
        print_provider_error(exc)
        raise typer.Exit(code=1) from exc


def print_chat_config_debug(config: PinoConfig) -> None:
    table = Table("Field", "Value")
    table.add_row("provider", plain_text(config.llm.default_provider))
    table.add_row("model", plain_text(config.llm.selected_model()))
    table.add_row("history_limit", plain_text(config.chat.history_limit))
    table.add_row("max_tool_rounds", plain_text(config.chat.max_tool_rounds))
    console.print(Panel(table, title="Chat debug", border_style="blue"))


def print_chat_debug(config: PinoConfig, result) -> None:
    table = Table("Field", "Value")
    table.add_row("provider", plain_text(config.llm.default_provider))
    table.add_row("model", plain_text(config.llm.selected_model()))
    table.add_row("tool_calls", plain_text(", ".join(result.tool_calls) or "<none>"))
    console.print(Panel(table, title="Chat debug", border_style="blue"))

    rounds = result.debug.get("rounds", [])
    if isinstance(rounds, list) and rounds:
        rounds_table = Table("Round", "Messages", "Roles", "Tool Context", "Action", "Tool")
        for item in rounds:
            if not isinstance(item, dict):
                continue
            rounds_table.add_row(
                plain_text(item.get("round", "")),
                plain_text(item.get("message_count", "")),
                plain_text(summarize_roles(item.get("message_roles"))),
                plain_text(item.get("tool_context_count", "")),
                plain_text(item.get("action", "")),
                plain_text(item.get("tool", "")),
            )
        console.print(Panel(rounds_table, title="LLM rounds", border_style="blue"))

    tool_usage = result.debug.get("tool_usage", [])
    if isinstance(tool_usage, list) and tool_usage:
        usage_table = Table("Tool", "Arguments", "Result")
        for item in tool_usage:
            if not isinstance(item, dict):
                continue
            usage_table.add_row(
                plain_text(item.get("name", "")),
                plain_text(json_dumps(item.get("arguments", {}))),
                plain_text(item.get("result", "")),
            )
        console.print(Panel(usage_table, title="Tool usage", border_style="blue"))


def summarize_roles(value: object) -> str:
    if not isinstance(value, list):
        return ""
    counts: dict[str, int] = {}
    for item in value:
        role = str(item)
        counts[role] = counts.get(role, 0) + 1
    return ", ".join(f"{role}:{count}" for role, count in counts.items())


def print_provider_error(exc: LLMError) -> None:
    table = Table("Field", "Value")
    table.add_row("provider", plain_text(exc.provider))
    table.add_row("model", plain_text(exc.model))
    table.add_row("url", plain_text(exc.url))
    if exc.status_code is not None:
        table.add_row("status", plain_text(exc.status_code))
    if exc.request:
        table.add_row("request", plain_text(json_dumps(exc.request)))

    console.print(Panel(table, title="LLM provider error", border_style="red"))
    if exc.response_body:
        console.print(Panel(plain_text(exc.response_body), title="Response body", border_style="red"))


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


def plain_text(value: object) -> Text:
    return Text(str(value))


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
        table.add_row(
            plain_text(row.created_at.isoformat()),
            plain_text(", ".join(row.tags)),
            plain_text(row.content),
        )
    console.print(table)


@sources_app.command("list")
def sources_list(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """List configured source adapters."""
    config = get_config(config_path)
    table = Table("Name", "Type", "Status")
    for source in config.sources:
        table.add_row(
            plain_text(source.name),
            plain_text(source.type),
            plain_text("enabled" if source.enabled else "disabled"),
        )
    console.print(table)
