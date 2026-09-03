from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pino_core import (
    ChatAgent,
    ChatMessage,
    CheckPipeline,
    CheckResult,
    DatabaseStore,
    LLMError,
    MemoryEntry,
    PinoConfig,
    Record,
    Refinement,
    RefinementDebugResult,
    RefinementProgress,
    RefinementService,
    build_refinement_llm_config,
    build_llm_client,
    build_tools,
    load_config,
    recent_chat_history,
    render_chat_system_prompt,
    render_refinement_system_prompt,
)
from pino_core.db import current_database_revision, show_migration_history, upgrade_database
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.schedule_evaluation import (
    ScheduleEvalProgress,
    ScheduleKindScore,
    evaluate_schedule_model,
    load_schedule_eval_corpus,
)
from pino_core.storage import normalize_database_url
from pino_integration import build_refinement_qc, build_sources

app = typer.Typer(no_args_is_help=True)
chat_app = typer.Typer(no_args_is_help=False, invoke_without_command=True)
memory_app = typer.Typer(no_args_is_help=True)
sources_app = typer.Typer(no_args_is_help=True)
debug_app = typer.Typer(no_args_is_help=True)
db_app = typer.Typer(no_args_is_help=True)
usage_app = typer.Typer(no_args_is_help=True)
eval_app = typer.Typer(no_args_is_help=True)
app.add_typer(chat_app, name="chat")
app.add_typer(memory_app, name="memory")
app.add_typer(sources_app, name="sources")
app.add_typer(debug_app, name="debug")
app.add_typer(db_app, name="db")
app.add_typer(usage_app, name="usage")
app.add_typer(eval_app, name="eval")

console = Console()


def get_config(path: Path | None) -> PinoConfig:
    return load_config(path)


def get_store(config: PinoConfig) -> DatabaseStore:
    store = DatabaseStore(config.storage.database_url())
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
    print_check_result(result)


def print_check_result(result: CheckResult) -> None:
    summary = Table("Metric", "Count", show_edge=False)
    summary.add_row("Fetched", plain_text(result.fetched))
    summary.add_row("Inserted", plain_text(result.inserted))
    summary.add_row("Duplicates", plain_text(result.duplicates))
    summary.add_row("Pending refinement", plain_text(result.pending_refinement_total))
    summary.add_row("Pending from this check", plain_text(result.pending_refinement_new))
    console.print(Panel(summary, title="Check complete", border_style="green"))

    if result.sources:
        sources = Table("Source", "Fetched", "Inserted", "Duplicates", "Cursor")
        for source in result.sources:
            sources.add_row(
                plain_text(_format_source_label(source.kind, source.name)),
                plain_text(source.fetched),
                plain_text(source.inserted),
                plain_text(source.duplicates),
                _format_cursor_status(source.cursor_status),
            )
        console.print(sources)

    if result.records:
        records = Table("New record", "Source", "Kind")
        for record in result.records[:10]:
            records.add_row(
                plain_text(record.title or _truncate_inline(record.text, 60)),
                plain_text(_format_source_label(_record_source_kind(record), record.source)),
                plain_text(record.kind),
            )
        console.print(records)
        if len(result.records) > 10:
            console.print(Text(f"... {len(result.records) - 10} more new record(s)", style="dim"))
    else:
        console.print(Text("No new records inserted.", style="dim"))


@app.command()
def refine(
    selected_id: Annotated[str | None, typer.Argument()] = None,
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    limit: Annotated[int | None, typer.Option("--limit", "-n", min=1)] = None,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Refine captured records into reusable normalized items."""
    _run_refine(config_path=config_path, limit=limit, debug=debug, selected_id=selected_id)


@app.command()
def evaluate(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    limit: Annotated[int | None, typer.Option("--limit", "-n", min=1)] = None,
    debug: Annotated[bool, typer.Option("--debug")] = False,
) -> None:
    """Deprecated alias for `pino refine`."""
    _run_refine(config_path=config_path, limit=limit, debug=debug, selected_id=None)


@eval_app.command("schedules")
def eval_schedules(
    models: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            "-m",
            help="Fully qualified model profile reference (provider:name).",
        ),
    ] = None,
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    fixtures: Annotated[
        Path,
        typer.Option("--fixtures", exists=True, file_okay=False, readable=True),
    ] = Path("packages/pino-core/tests/integration/golden/afisha_vilnius"),
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path(".pino/evals/afisha_vilnius"),
    limit: Annotated[int | None, typer.Option("--limit", "-n", min=1)] = None,
    timeout: Annotated[int, typer.Option("--timeout", min=1, help="Seconds per request.")] = 15,
) -> None:
    """Compare explicit model profiles against reviewed schedule fixtures."""
    if not models:
        raise typer.BadParameter("at least one --model is required", param_hint="--model")
    config = get_config(config_path)
    for model in models:
        try:
            config.llm.profile(model)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--model") from exc
    corpus = load_schedule_eval_corpus(fixtures)
    store = get_store(config)
    selected_total = min(limit, len(corpus.fixtures)) if limit is not None else len(corpus.fixtures)
    reports = []
    for model in models:
        console.print(f"Evaluating {model} on {selected_total} fixture(s)...")
        report = evaluate_schedule_model(
            config=config,
            model=model,
            corpus=corpus,
            output_dir=output_dir,
            limit=limit,
            usage_recorder=store.add_llm_usage_event,
            on_progress=print_schedule_eval_progress,
            timeout_seconds=timeout,
            quality_check=build_refinement_qc(config.sources),
        )
        reports.append(report)
        console.print(
            Text(
                f"Completed {model}: {report.summary.passed}/{report.summary.total} exact "
                f"({report.summary.accuracy:.1%}), {report.summary.invalid} invalid. "
                f"Summary: {report.summary_path}",
                style="green" if report.summary.passed == report.summary.total else "yellow",
            )
        )

    table = Table(
        "Model",
        "Exact",
        "Occurrence",
        "Recurrence",
        "No schedule",
        "Invalid",
        "Generation",
        "Time total / min / p50 / mean / max",
    )
    for report in reports:
        summary = report.summary
        table.add_row(
            plain_text(summary.model),
            plain_text(f"{summary.passed}/{summary.total} ({summary.accuracy:.1%})"),
            plain_text(_format_schedule_score(summary.by_kind["occurrences"])),
            plain_text(_format_schedule_score(summary.by_kind["recurrence"])),
            plain_text(_format_schedule_score(summary.by_kind["null"])),
            plain_text(summary.invalid),
            plain_text(
                f"{summary.output_tokens} tok / {summary.tokens_per_second:.1f} tok/s"
                if summary.tokens_per_second is not None
                else f"{summary.output_tokens} tok"
                if summary.output_tokens
                else "-"
            ),
            plain_text(
                " / ".join(
                    _format_duration_ms(value)
                    for value in (
                        summary.total_duration_ms,
                        summary.min_duration_ms,
                        summary.p50_duration_ms,
                        summary.mean_duration_ms,
                        summary.max_duration_ms,
                    )
                )
            ),
        )
    console.print(table)
    console.print(
        Text(
            f"Excluded {corpus.excluded} human-marked bad fixture(s).",
            style="dim",
        )
    )


def print_schedule_eval_progress(progress: ScheduleEvalProgress) -> None:
    if progress.status == "started":
        console.print(Text(f"Live summary: {progress.summary_path}", style="dim"))
        return
    console.print(
        Text(
            f"[{progress.model} {progress.completed}/{progress.total}] "
            f"{progress.fixture}: {progress.status} | exact {progress.passed}, "
            f"invalid {progress.invalid} | {progress.elapsed_ms / 1000:.1f}s",
            style="dim" if progress.status == "pass" else "yellow",
        )
    )
    if progress.case is not None and progress.case.qc.schedule is not None:
        flag = progress.case.qc.schedule
        console.print(
            Text(
                f"Schedule QC {flag.level}: {flag.message or 'quality check failed'}",
                style="red" if flag.level == "error" else "yellow",
            )
        )
    if progress.case is None or progress.case.passed:
        return
    console.print(
        Panel(
            plain_text(json_dumps(progress.case.expected)),
            title=f"{progress.case.fixture} expected",
            border_style="red",
        )
    )
    console.print(
        Panel(
            plain_text(json_dumps(progress.case.actual)),
            title=f"{progress.case.fixture} actual",
            border_style="red",
        )
    )
    if progress.case.error:
        console.print(Text(f"Error: {progress.case.error}", style="red"))
    if progress.response_path is not None:
        console.print(Text(f"Response: {progress.response_path}", style="dim"))
    if progress.reasoning_path is not None:
        console.print(Text(f"Reasoning: {progress.reasoning_path}", style="dim"))


@db_app.command("upgrade")
def db_upgrade(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    revision: Annotated[str, typer.Argument()] = "head",
) -> None:
    """Upgrade the configured storage database with Alembic."""
    config = get_config(config_path)
    upgrade_database(config.storage.database_url(), revision)
    console.print(Text(f"Database upgraded to {revision}.", style="green"))


@db_app.command("current")
def db_current(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Print the configured storage database migration revision."""
    config = get_config(config_path)
    current_database_revision(config.storage.database_url())


@db_app.command("history")
def db_history(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Print known Alembic migration history."""
    config = get_config(config_path)
    show_migration_history(config.storage.database_url())


@db_app.command("url")
def db_url(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Print the configured storage database URL with the password hidden."""
    config = get_config(config_path)
    url = normalize_database_url(config.storage.database_url())
    table = Table("Field", "Value")
    table.add_row("storage.use", plain_text(config.storage.use))
    table.add_row("database_url", plain_text(url.render_as_string(hide_password=True)))
    console.print(table)


@usage_app.command("summary")
def usage_summary(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    days: Annotated[int, typer.Option("--days", min=1)] = 7,
    group_by: Annotated[
        str | None,
        typer.Option("--group-by", help="One of: provider, model, operation."),
    ] = None,
) -> None:
    """Summarize persisted LLM token usage."""
    config = get_config(config_path)
    store = get_store(config)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        summaries = store.summarize_llm_usage(since=since, group_by=group_by)
    except ValueError as exc:
        console.print(Text(str(exc), style="red"))
        raise typer.Exit(code=1) from exc

    table = Table(
        "Key",
        "Calls",
        "Input",
        "Cached Input",
        "Uncached Input",
        "Output",
        "Cache Hit",
        "Avg Duration",
    )
    for key, summary in summaries.items():
        table.add_row(
            plain_text(key),
            plain_text(summary.calls),
            plain_text(_format_int(summary.input_tokens)),
            plain_text(_format_int(summary.cached_input_tokens)),
            plain_text(_format_int(summary.uncached_input_tokens)),
            plain_text(_format_int(summary.output_tokens)),
            plain_text(_format_percent(summary.cache_hit_ratio)),
            plain_text(f"{summary.average_duration_ms} ms"),
        )
    console.print(Panel(table, title=f"LLM usage, last {days} day(s)", border_style="blue"))


@usage_app.command("recent")
def usage_recent(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 20,
) -> None:
    """Print recent persisted LLM token usage events."""
    config = get_config(config_path)
    store = get_store(config)
    rows = store.list_llm_usage_events(limit=limit)
    table = Table(
        "Created", "Provider", "Model", "Operation", "Input", "Cached", "Output", "Duration"
    )
    for row in rows:
        table.add_row(
            plain_text(row.created_at.isoformat()),
            plain_text(row.provider),
            plain_text(row.model),
            plain_text(row.operation),
            plain_text(_format_int(row.input_tokens)),
            plain_text(_format_int(row.cached_input_tokens)),
            plain_text(_format_int(row.output_tokens)),
            plain_text(f"{row.duration_ms} ms"),
        )
    console.print(table)


def _run_refine(
    *,
    config_path: Path | None,
    limit: int | None,
    debug: bool,
    selected_id: str | None = None,
) -> None:
    config = get_config(config_path)
    llm_config = build_refinement_llm_config(config.llm)
    store = get_store(config)
    service = RefinementService(
        store=store,
        client=build_llm_client(llm_config, usage_recorder=store.add_llm_usage_event),
        config=config.refinement,
        quality_check=build_refinement_qc(config.sources),
        model=llm_config.model,
    )
    if selected_id is not None:
        _run_refine_debug_id(
            store=store,
            service=service,
            llm_config=llm_config,
            selected_id=selected_id,
        )
        return
    result = service.refine_pending(limit=limit, on_progress=print_refinement_progress)
    if debug:
        table = Table("Field", "Value")
        table.add_row("provider", plain_text(llm_config.selected_provider()))
        table.add_row("model", plain_text(llm_config.model))
        table.add_row("requested", plain_text(result.requested))
        table.add_row("refined", plain_text(result.refined))
        table.add_row("items", plain_text(result.items))
        table.add_row("skipped", plain_text(result.skipped))
        console.print(Panel(table, title="Refinement debug", border_style="blue"))
    console.print(
        f"Requested {result.requested}; refined {result.refined}; "
        f"items {result.items}; skipped {result.skipped}.",
    )


def _run_refine_debug_id(
    *,
    store: DatabaseStore,
    service: RefinementService,
    llm_config,
    selected_id: str,
) -> None:
    normalized_id = normalize_refinement_debug_id(selected_id)
    if not normalized_id:
        console.print(Text("Refinement id is required.", style="red"))
        raise typer.Exit(code=1)
    record, existing_refinement, resolved_kind = resolve_refinement_debug_target(
        store,
        normalized_id,
    )
    try:
        result = service.debug_refine_record(record)
    except LLMError as exc:
        print_provider_error(exc)
        raise typer.Exit(code=1) from exc
    print_refinement_debug_rerun(
        selected_id=normalized_id,
        resolved_kind=resolved_kind,
        provider=llm_config.selected_provider(),
        model=llm_config.model,
        existing_refinement=existing_refinement,
        result=result,
    )


def normalize_refinement_debug_id(selected_id: str) -> str:
    normalized_id = selected_id.strip()
    if normalized_id.lower().startswith("id "):
        return normalized_id[3:].strip()
    return normalized_id


def resolve_refinement_debug_target(
    store: DatabaseStore,
    selected_id: str,
) -> tuple[Record, Refinement | None, str]:
    refinement = store.get_refinement(selected_id)
    if refinement is not None:
        record = store.get_record(refinement.record_id)
        if record is None:
            console.print(Text("Refinement source record not found.", style="red"))
            raise typer.Exit(code=1)
        return record, refinement, "refinement"
    record = store.get_record(selected_id)
    if record is not None:
        return record, None, "record"
    console.print(Text("Refinement or record id not found.", style="red"))
    raise typer.Exit(code=1)


def print_refinement_debug_rerun(
    *,
    selected_id: str,
    resolved_kind: str,
    provider: str,
    model: str,
    existing_refinement: Refinement | None,
    result: RefinementDebugResult,
) -> None:
    summary = Table("Field", "Value")
    summary.add_row("selected_id", plain_text(selected_id))
    summary.add_row("resolved_kind", plain_text(resolved_kind))
    summary.add_row("persisted", plain_text(False))
    summary.add_row("provider", plain_text(provider))
    summary.add_row("model", plain_text(model))
    summary.add_row("record_id", plain_text(result.record.id))
    summary.add_row("record_title", plain_text(result.record.title or ""))
    if existing_refinement is not None:
        summary.add_row("existing_refinement_id", plain_text(existing_refinement.id))
        summary.add_row("existing_item_index", plain_text(existing_refinement.item_index))
        summary.add_row("existing_summary", plain_text(existing_refinement.summary or ""))
    if result.error is not None:
        summary.add_row("error", plain_text(result.error))
    if result.qc.schedule is not None:
        summary.add_row("schedule_qc", plain_text(result.qc.schedule.level))
        summary.add_row("schedule_qc_message", plain_text(result.qc.schedule.message or ""))
    console.print(Panel(summary, title="Refinement dry run", border_style="blue"))

    for message in result.messages:
        console.print(
            Panel(
                plain_text(message.content),
                title=f"Prompt: {message.role}",
                border_style="blue",
            )
        )
    if result.reasoning is not None:
        console.print(Panel(plain_text(result.reasoning), title="Reasoning", border_style="blue"))
    console.print(Panel(plain_text(result.raw_response), title="Raw response", border_style="blue"))
    console.print(
        Panel(
            plain_text(json_dumps(result.parsed_response)),
            title="Parsed response",
            border_style="blue",
        )
    )
    console.print(
        Panel(
            plain_text(
                json_dumps(
                    [refinement.model_dump(mode="json") for refinement in result.refinements]
                )
            ),
            title="Generated refinements",
            border_style="blue",
        )
    )


def print_refinement_progress(progress: RefinementProgress) -> None:
    if progress.status == "selected":
        if progress.total == 0:
            console.print("No unrefined records found.")
        else:
            console.print(f"Refining {progress.total} record(s)...")
        return

    label = progress.record.title or progress.record.kind if progress.record else "record"
    prefix = f"[{progress.index}/{progress.total}]" if progress.index is not None else ""
    if progress.status == "refining":
        console.print(Text(f"  {prefix} {label}", style="dim"))
        return

    if progress.status == "refined" and progress.refinements is not None:
        message = f"    refined {len(progress.refinements)} item(s)"
        if progress.refinements:
            refinement = progress.refinements[0]
            relevant_from = (
                refinement.relevant_from.isoformat()
                if refinement.relevant_from is not None
                else "undated"
            )
            summary = _truncate_inline(refinement.summary or "<no summary>", 100)
            message += f": {relevant_from} — {summary}"
        console.print(Text(message, style="green"))
        if progress.qc is not None and progress.qc.schedule is not None:
            flag = progress.qc.schedule
            console.print(Text(f"    schedule QC {flag.level}: {flag.message}", style="yellow"))
        return

    reason = progress.reason or "skipped"
    console.print(Text(f"    skipped: {reason}", style="yellow"))


@debug_app.command("prompts")
def debug_prompts(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
) -> None:
    """Print rendered prompts used by local LLM calls."""
    config = get_config(config_path)
    store = get_store(config)
    sources = build_sources(config.sources)
    tools = build_tools(store, sources)

    console.rule("Chat system prompt")
    console.print(
        plain_text(
            render_chat_system_prompt(
                store=store,
                tools=tools,
                config=config.chat,
                goals=config.profile.goals,
            ),
        ),
    )
    console.rule("Refinement system prompt")
    console.print(plain_text(render_refinement_system_prompt(config.refinement)))


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
    llm_config = config.llm.for_role("chat")
    if history_limit is not None:
        config.chat.history_limit = history_limit
    store = get_store(config)
    sources = build_sources(config.sources)
    agent = ChatAgent(
        store=store,
        provider=build_llm_client(llm_config, usage_recorder=store.add_llm_usage_event),
        tools=build_tools(store, sources),
        config=config.chat,
        goals=config.profile.goals,
    )

    if message:
        result = respond_or_exit(agent, message)
        if debug:
            print_chat_debug(config, result)
        print_chat_result(result, show_tool_calls=not debug)
        return

    console.print("Pino chat. Type /exit to quit.")
    print_recent_chat_history(store, config.chat.history_limit)
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
        print_chat_result(result, show_tool_calls=not debug)


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


def print_chat_result(result, *, show_tool_calls: bool = True) -> None:
    if show_tool_calls:
        print_chat_tool_calls(result)
    print_markdown(result.content)


def print_markdown(content: str) -> None:
    console.print(Markdown(content))


def print_chat_tool_calls(result) -> None:
    tool_usage = result.debug.get("tool_usage", []) if isinstance(result.debug, dict) else []
    printed = False
    if isinstance(tool_usage, list):
        for item in tool_usage:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            arguments = json_dumps_compact(item.get("arguments", {}))
            console.print(Text(f"  -> {name} {arguments}", style="dim"))
            printed = True

    if printed:
        return

    for name in result.tool_calls:
        console.print(Text(f"  -> {name}", style="dim"))


def print_chat_config_debug(config: PinoConfig) -> None:
    llm_config = config.llm.for_role("chat")
    table = Table("Field", "Value")
    table.add_row("provider", plain_text(llm_config.selected_provider()))
    table.add_row("model", plain_text(llm_config.model))
    table.add_row("history_limit", plain_text(config.chat.history_limit))
    table.add_row("active_memory_limit", plain_text(config.chat.active_memory_limit))
    table.add_row("max_tool_rounds", plain_text(config.chat.max_tool_rounds))
    table.add_row("max_tools_per_round", plain_text(config.chat.max_tools_per_round))
    console.print(Panel(table, title="Chat debug", border_style="blue"))


def print_chat_debug(config: PinoConfig, result) -> None:
    llm_config = config.llm.for_role("chat")
    table = Table("Field", "Value")
    table.add_row("provider", plain_text(llm_config.selected_provider()))
    table.add_row("model", plain_text(llm_config.model))
    table.add_row("tool_calls", plain_text(", ".join(result.tool_calls) or "<none>"))
    console.print(Panel(table, title="Chat debug", border_style="blue"))

    rounds = result.debug.get("rounds", [])
    if isinstance(rounds, list) and rounds:
        rounds_table = Table("Round", "Messages", "Roles", "Tool Context", "Action", "Tools")
        for item in rounds:
            if not isinstance(item, dict):
                continue
            tools = item.get("tools")
            if not isinstance(tools, list):
                tools = [item.get("tool", "")]
            rounds_table.add_row(
                plain_text(item.get("round", "")),
                plain_text(item.get("message_count", "")),
                plain_text(summarize_roles(item.get("message_roles"))),
                plain_text(item.get("tool_context_count", "")),
                plain_text(item.get("action", "")),
                plain_text(", ".join(str(tool) for tool in tools if tool)),
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


def print_recent_chat_history(store: DatabaseStore, limit: int) -> None:
    history = [
        message
        for message in recent_chat_history(store, limit)
        if message.role in {"user", "assistant"}
    ]
    if not history:
        return

    for message in history:
        print_chat_history_message(message)


def print_chat_history_message(message: ChatMessage) -> None:
    print_markdown(f"{chat_display_name(message.role)}> {message.content}")


def chat_display_name(role: str) -> str:
    if role == "user":
        return "Boss"
    if role == "assistant":
        return "Pino"
    return role


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
        console.print(
            Panel(plain_text(exc.response_body), title="Response body", border_style="red")
        )


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


def json_dumps_compact(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def plain_text(value: object) -> Text:
    return Text(str(value))


def _format_int(value: int) -> str:
    return f"{value:,}"


def _format_percent(value: float) -> str:
    return f"{value:.1%}"


def _format_schedule_score(score: ScheduleKindScore) -> str:
    if not score.total:
        return "-"
    return f"{score.passed}/{score.total} ({score.accuracy:.1%})"


def _format_duration_ms(value: int) -> str:
    if value >= 60_000:
        return f"{value / 60_000:.1f}m"
    if value >= 1_000:
        return f"{value / 1_000:.1f}s"
    return f"{value}ms"


def _truncate_inline(value: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _format_cursor_status(value: str) -> str:
    if value == "unsupported":
        return "-"
    return value


def _format_source_label(kind: str, name: str) -> str:
    prefix = "tg" if kind == "tg" else "web"
    if name.startswith(("web:", "tg:")):
        return name
    return f"{prefix}:{name}"


def _record_source_kind(record: Record) -> str:
    return "tg" if record.provenance.get("adapter") == "telegram_channel" else "web"


def _config_source_kind(source_type: str) -> str:
    return "tg" if source_type == "telegram_channel" else "web"


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
            plain_text(_format_source_label(_config_source_kind(source.type), source.name)),
            plain_text(source.type),
            plain_text("enabled" if source.enabled else "disabled"),
        )
    console.print(table)


@sources_app.command("stats")
def sources_stats(
    config_path: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    weeks: Annotated[int, typer.Option("--weeks", min=1, max=52)] = 8,
) -> None:
    """Show weekly source publication counts."""
    config = get_config(config_path)
    store = get_store(config)
    timezone_info = ZoneInfo(DEFAULT_SOURCE_TIMEZONE)
    print_source_stats(
        config,
        store,
        weeks=weeks,
        today=datetime.now(timezone_info).date(),
    )


def print_source_stats(
    config: PinoConfig,
    store: DatabaseStore,
    *,
    weeks: int,
    today: date,
) -> None:
    timezone_info = ZoneInfo(DEFAULT_SOURCE_TIMEZONE)
    current_week = today - timedelta(days=today.weekday())
    week_starts = [current_week - timedelta(weeks=index) for index in range(weeks - 1, -1, -1)]
    window_start = datetime.combine(week_starts[0], time.min, tzinfo=timezone_info)
    window_end = datetime.combine(
        week_starts[-1] + timedelta(weeks=1),
        time.min,
        tzinfo=timezone_info,
    )
    counts, unknown = store.summarize_source_publications(
        window_start=window_start.astimezone(timezone.utc),
        window_end=window_end.astimezone(timezone.utc),
        timezone_name=DEFAULT_SOURCE_TIMEZONE,
    )

    configured = {source.name: source for source in config.sources}
    source_names = list(configured)
    source_names.extend(
        sorted((set(source for source, _week in counts) | set(unknown)) - set(configured))
    )
    table = Table("Source", *(week.strftime("%b %d") for week in week_starts), "Unknown")
    for source_name in source_names:
        source = configured.get(source_name)
        label = (
            _format_source_label(_config_source_kind(source.type), source.name)
            if source is not None
            else source_name
        )
        table.add_row(
            plain_text(label),
            *(plain_text(counts.get((source_name, week), 0)) for week in week_starts),
            plain_text(unknown.get(source_name, 0)),
        )
    console.print(table)
    if unknown:
        console.print(Text("Unknown counts records without publication time.", style="dim"))
