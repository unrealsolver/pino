from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from rich.console import Console
from pino_llm import LLMMessage, LLMUsage

from pino_cli import main
from pino_core.config import PinoConfig, SourceConfig, StorageConfig
from pino_core.models import ChatMessage, Record, Refinement
from pino_core.pipeline import CheckResult, SourceCheckResult
from pino_core.refinement import RefinementProgress
from pino_core.schedule_evaluation import ScheduleKindScore
from pino_core.storage import SQLiteStore


class StaticRefinementClient:
    def __init__(self, response: str, *, reasoning: str | None = None) -> None:
        self.response = response
        self.last_reasoning = reasoning
        self.messages: list[LLMMessage] = []

    def complete(self, messages: list[LLMMessage], *, operation: str = "unknown") -> str:
        self.messages = messages
        return self.response


def test_eval_schedules_requires_an_explicit_model(tmp_path: Path) -> None:
    with pytest.raises(typer.BadParameter, match="at least one --model"):
        main.eval_schedules(
            models=None,
            config_path=None,
            fixtures=tmp_path,
            output_dir=tmp_path / "output",
            limit=None,
            timeout=15,
        )


def test_eval_schedules_prints_model_comparison(tmp_path: Path, monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=220))
    corpus = SimpleNamespace(fixtures=[object()], excluded=10)
    scores = {
        "occurrences": ScheduleKindScore(passed=0, total=1),
        "recurrence": ScheduleKindScore(passed=0, total=0),
        "null": ScheduleKindScore(passed=0, total=0),
    }
    report = SimpleNamespace(
        summary=SimpleNamespace(
            model="ollama:small-local",
            passed=0,
            total=1,
            accuracy=0.0,
            invalid=0,
            total_duration_ms=1200,
            min_duration_ms=1200,
            p50_duration_ms=1200,
            mean_duration_ms=12,
            max_duration_ms=1200,
            output_tokens=25,
            tokens_per_second=20.0,
            by_kind=scores,
        ),
        summary_path=tmp_path / "output/small-local/run/summary.yaml",
    )
    config = PinoConfig(
        llm={
            "roles": {
                "chat": "ollama:small-local",
                "refine": "ollama:small-local",
            },
            "models": {
                "ollama": {
                    "small-local": {
                        "model": "gemma4:e4b",
                    }
                }
            },
        },
    )
    monkeypatch.setattr(main, "get_config", lambda path: config)
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    monkeypatch.setattr(main, "get_store", lambda actual_config: store)
    monkeypatch.setattr(main, "load_schedule_eval_corpus", lambda path: corpus)

    def fake_evaluate_schedule_model(**kwargs):
        assert kwargs["timeout_seconds"] == 15
        kwargs["usage_recorder"](
            LLMUsage(
                provider="ollama",
                model="gemma4:e4b",
                operation="evaluation.schedule",
                input_tokens=100,
                output_tokens=25,
                cached_input_tokens=0,
                duration_ms=1200,
            )
        )
        summary_path = tmp_path / "output/small-local/run/summary.yaml"
        kwargs["on_progress"](
            main.ScheduleEvalProgress(
                model="ollama:small-local",
                completed=0,
                total=1,
                fixture="",
                status="started",
                passed=0,
                invalid=0,
                elapsed_ms=0,
                summary_path=summary_path,
            )
        )
        case = SimpleNamespace(
            fixture="001",
            status="mismatch",
            passed=False,
            expected={"kind": "occurrences"},
            actual=None,
            error=None,
            qc=SimpleNamespace(schedule=None),
        )
        kwargs["on_progress"](
            main.ScheduleEvalProgress(
                model="ollama:small-local",
                completed=1,
                total=1,
                fixture="001",
                status="mismatch",
                passed=0,
                invalid=0,
                elapsed_ms=1200,
                summary_path=summary_path,
                case=case,
                response_path=tmp_path / "output/small-local/run/responses/001.json",
                reasoning_path=tmp_path / "output/small-local/run/reasoning/001.txt",
            )
        )
        return report

    monkeypatch.setattr(main, "evaluate_schedule_model", fake_evaluate_schedule_model)

    main.eval_schedules(
        models=["ollama:small-local"],
        config_path=None,
        fixtures=tmp_path,
        output_dir=tmp_path / "output",
        limit=None,
        timeout=15,
    )

    rendered = output.getvalue()
    assert "Evaluating ollama:small-local on 1 fixture(s)" in rendered
    assert "Live summary:" in rendered
    assert "[ollama:small-local 1/1] 001: mismatch" in rendered
    assert "exact 0, invalid 0 | 1.2s" in rendered
    assert "1.2s / 1.2s / 1.2s / 12ms / 1.2s" in rendered
    assert "25 tok / 20.0 tok/s" in rendered
    assert "small-local" in rendered
    assert "0/1 (0.0%)" in rendered
    assert "001 expected" in rendered
    assert '"kind": "occurrences"' in rendered
    assert "001 actual" in rendered
    assert "responses/001.json" in rendered
    assert "reasoning/001.txt" in rendered
    assert "Completed ollama:small-local: 0/1 exact (0.0%)" in rendered
    assert "Summary:" in rendered
    assert "Excluded 10 human-marked bad fixture(s)" in rendered
    usage = store.list_llm_usage_events()
    assert len(usage) == 1
    assert usage[0].operation == "evaluation.schedule"


def test_chat_debug_prints_tool_markup_as_plain_text(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=True, width=100))
    result = SimpleNamespace(
        tool_calls=["records.list"],
        debug={
            "rounds": [
                {
                    "round": 1,
                    "message_count": 2,
                    "message_roles": ["system", "user"],
                    "tool_context_count": 0,
                    "action": "tool",
                    "tool": "records.list",
                },
            ],
            "tool_usage": [
                {
                    "name": "records.list",
                    "arguments": {},
                    "result": "model emitted [/TOOL_CALL] marker",
                },
            ],
        },
    )

    main.print_chat_debug(PinoConfig(), result)

    assert "[/TOOL_CALL]" in output.getvalue()


def test_chat_result_renders_markdown(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=100))
    result = SimpleNamespace(content="**Important** note", tool_calls=[], debug={})

    main.print_chat_result(result)

    rendered = output.getvalue()
    assert "Important note" in rendered
    assert "**Important**" not in rendered


def test_chat_result_prints_compact_tool_usage(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=100))
    result = SimpleNamespace(
        content="Done",
        tool_calls=["records.list"],
        debug={
            "tool_usage": [
                {
                    "name": "records.list",
                    "arguments": {"limit": 2},
                    "result": "hidden from compact output",
                },
            ],
        },
    )

    main.print_chat_result(result)

    rendered = output.getvalue()
    assert '-> records.list {"limit":2}' in rendered
    assert "hidden from compact output" not in rendered
    assert "Done" in rendered


def test_check_result_prints_pending_refinement_counts(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))

    main.print_check_result(
        CheckResult(
            fetched=84,
            inserted=12,
            duplicates=72,
            records=[
                Record(
                    kind="event",
                    source="vilnius-events",
                    title="Synth night",
                    text="Synth event text",
                    provenance={"adapter": "vilnius_events"},
                ),
            ],
            pending_refinement_total=37,
            pending_refinement_new=12,
            sources=[
                SourceCheckResult(
                    name="vilnius-events",
                    fetched=84,
                    inserted=12,
                    duplicates=72,
                    kind="web",
                    cursor_updated=True,
                    cursor_status="updated",
                ),
                SourceCheckResult(
                    name="afisha-vilnius",
                    fetched=0,
                    inserted=0,
                    duplicates=0,
                    kind="tg",
                    cursor_status="unchanged",
                ),
            ],
        ),
    )

    rendered = output.getvalue()
    assert "Check complete" in rendered
    assert "Fetched" in rendered
    assert "84" in rendered
    assert "Inserted" in rendered
    assert "12" in rendered
    assert "Duplicates" in rendered
    assert "72" in rendered
    assert "Pending refinement" in rendered
    assert "Pending from this check" in rendered
    assert "37" in rendered
    assert "web:vilnius-events" in rendered
    assert "updated" in rendered
    assert "tg:afisha-vilnius" in rendered
    assert "unchanged" in rendered
    assert "Synth night" in rendered
    assert "no source failures" in rendered


@pytest.mark.parametrize("all_failed", [False, True])
def test_check_reports_activity_and_failures_before_completion(tmp_path, monkeypatch, all_failed):
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    monkeypatch.setattr(main, "get_config", lambda _: PinoConfig())
    store = SQLiteStore(tmp_path / "pino.sqlite")
    monkeypatch.setattr(main, "get_store", lambda _: store)

    class FailedSource:
        name = "broken"
        source_kind = "web"

        def fetch(self):
            assert "Fetching web:broken" in output.getvalue()
            assert "Check complete" not in output.getvalue()
            raise ValueError("missing [event] cards")

    class HealthySource:
        name = "healthy"
        source_kind = "tg"

        def fetch(self):
            rendered = output.getvalue()
            assert "FAILED web:broken: ValueError: missing [event] cards" in rendered
            assert "Fetching tg:healthy" in rendered
            assert "Check complete" not in rendered
            return [Record(kind="note", source=self.name, text="test")]

    original_add = store.add_record

    def add_record(record):
        assert "Storing tg:healthy" in output.getvalue()
        assert "Check complete" not in output.getvalue()
        return original_add(record)

    monkeypatch.setattr(store, "add_record", add_record)
    sources = [FailedSource()] if all_failed else [FailedSource(), HealthySource()]
    monkeypatch.setattr(main, "build_sources", lambda _: sources)

    main.check(config_path=None)

    rendered = output.getvalue()
    assert "Check complete — 1 source(s) failed" in rendered
    assert rendered.count("ValueError: missing [event] cards") == 2
    assert "no source failures" not in rendered
    if not all_failed:
        assert "OK tg:healthy: 1 fetched, 1 new, 0 duplicates" in rendered
        assert len(store.list_records()) == 1


def test_check_result_distinguishes_no_sources(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    main.print_check_result(
        CheckResult(fetched=0, inserted=0, duplicates=0, records=[], sources=[])
    )
    assert "no sources checked" in output.getvalue()


def test_sources_list_prefixes_source_names(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    config = PinoConfig(
        sources=[
            SourceConfig(name="vilnius-events", type="vilnius_events"),
            SourceConfig(
                name="afisha-vilnius",
                type="telegram_channel",
                settings={"api_id": 12345, "api_hash": "hash"},
            ),
        ],
    )
    monkeypatch.setattr(main, "get_config", lambda config_path: config)

    main.sources_list()

    rendered = output.getvalue()
    assert "web:vilnius-events" in rendered
    assert "tg:afisha-vilnius" in rendered


def test_source_stats_prints_weekly_grid_and_unknown_dates(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    config = PinoConfig(
        sources=[
            SourceConfig(
                name="afisha-vilnius",
                type="telegram_channel",
                settings={"api_id": 1, "api_hash": "hash"},
            ),
            SourceConfig(name="kaveikti-vilnius", type="kaveikti", enabled=False),
        ]
    )
    store = SimpleNamespace(
        summarize_source_publications=lambda **kwargs: (
            {
                ("afisha-vilnius", date(2026, 8, 24)): 4,
                ("afisha-vilnius", date(2026, 8, 31)): 7,
            },
            {"kaveikti-vilnius": 12},
        )
    )

    main.print_source_stats(config, store, weeks=2, today=date(2026, 9, 3))

    rendered = output.getvalue()
    assert "Source" in rendered
    assert "Aug 24" in rendered
    assert "Aug 31" in rendered
    assert "Unknown" in rendered
    assert "tg:afisha-vilnius" in rendered
    assert "web:kaveikti-vilnius" in rendered
    assert "4" in rendered and "7" in rendered and "12" in rendered


def test_debug_prompts_prints_rendered_prompts(tmp_path, monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    config = PinoConfig(
        storage=StorageConfig(local={"type": "sqlite", "path": tmp_path / "pino.sqlite"}),
    )
    monkeypatch.setattr(main, "get_config", lambda config_path: config)

    main.debug_prompts()

    rendered = output.getvalue()
    assert "Chat system prompt" in rendered
    assert "Available tools:" in rendered
    assert "records.relevant" in rendered
    assert "Current time:" in rendered
    assert "Goals:" in rendered
    assert "Refinement system prompt" in rendered
    assert "Normalized item JSON object shape:" in rendered


def test_db_upgrade_uses_configured_database_url(tmp_path, monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    config = PinoConfig(
        storage=StorageConfig(local={"type": "sqlite", "path": tmp_path / "pino.sqlite"}),
    )
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(main, "get_config", lambda config_path: config)
    monkeypatch.setattr(
        main,
        "upgrade_database",
        lambda database_url, revision: calls.append((database_url, revision)),
    )

    main.db_upgrade(revision="head")

    assert calls == [(config.storage.database_url(), "head")]
    assert "Database upgraded to head." in output.getvalue()


def test_db_current_uses_configured_database_url(tmp_path, monkeypatch) -> None:
    config = PinoConfig(
        storage=StorageConfig(local={"type": "sqlite", "path": tmp_path / "pino.sqlite"}),
    )
    calls: list[str] = []
    monkeypatch.setattr(main, "get_config", lambda config_path: config)
    monkeypatch.setattr(main, "current_database_revision", calls.append)

    main.db_current()

    assert calls == [config.storage.database_url()]


def test_db_url_prints_redacted_configured_database_url(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    config = PinoConfig(
        storage=StorageConfig.model_validate(
            {
                "use": "pg_vps",
                "pg_vps": {
                    "type": "postgres",
                    "url": "postgresql://pino:secret@example.test/pino",
                },
            }
        ),
    )
    monkeypatch.setattr(main, "get_config", lambda config_path: config)

    main.db_url()

    rendered = output.getvalue()
    assert "pg_vps" in rendered
    assert "postgresql+psycopg://pino:***@example.test/pino" in rendered
    assert "secret" not in rendered


def test_usage_summary_prints_persisted_token_totals(tmp_path, monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    config = PinoConfig(
        storage=StorageConfig(local={"type": "sqlite", "path": tmp_path / "pino.sqlite"}),
    )
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_llm_usage_event(
        LLMUsage(
            provider="minimax",
            model="MiniMax-M3",
            operation="refinement.extract",
            input_tokens=1000,
            output_tokens=200,
            cached_input_tokens=750,
            duration_ms=1200,
        )
    )
    monkeypatch.setattr(main, "get_config", lambda config_path: config)

    main.usage_summary(days=7)

    rendered = output.getvalue()
    assert "LLM usage, last 7 day(s)" in rendered
    assert "1,000" in rendered
    assert "750" in rendered
    assert "250" in rendered
    assert "75.0%" in rendered


def test_usage_recent_prints_persisted_token_events(tmp_path, monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    config = PinoConfig(
        storage=StorageConfig(local={"type": "sqlite", "path": tmp_path / "pino.sqlite"}),
    )
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_llm_usage_event(
        LLMUsage(
            provider="ollama",
            model="gpt-oss-20b",
            operation="chat",
            input_tokens=42,
            output_tokens=12,
            cached_input_tokens=0,
            duration_ms=99,
        )
    )
    monkeypatch.setattr(main, "get_config", lambda config_path: config)

    main.usage_recent(limit=10)

    rendered = output.getvalue()
    assert "ollama" in rendered
    assert "gpt-oss-20b" in rendered
    assert "chat" in rendered
    assert "42" in rendered
    assert "12" in rendered


def test_recent_chat_history_formats_stored_markdown(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_chat_message(
        ChatMessage(
            role="assistant",
            content="**recent assistant**",
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        ),
    )
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))

    main.print_recent_chat_history(store, limit=1)

    rendered = output.getvalue()
    assert "Pino> recent assistant" in rendered
    assert "**recent assistant**" not in rendered


def test_recent_chat_history_prints_chat_transcript_without_tools(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_chat_message(
        ChatMessage(
            role="user",
            content="old user",
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        ),
    )
    store.add_chat_message(
        ChatMessage(
            role="tool",
            content="tool implementation detail",
            created_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
        ),
    )
    store.add_chat_message(
        ChatMessage(
            role="user",
            content="recent user",
            created_at=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc),
        ),
    )
    store.add_chat_message(
        ChatMessage(
            role="assistant",
            content="recent assistant",
            created_at=datetime(2026, 1, 1, 10, 3, tzinfo=timezone.utc),
        ),
    )
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))

    main.print_recent_chat_history(store, limit=3)

    rendered = output.getvalue()
    assert "Boss> recent user" in rendered
    assert "Pino> recent assistant" in rendered
    assert "tool implementation detail" not in rendered
    assert "old user" not in rendered


def test_refinement_progress_prints_forward_status(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    record = Record(kind="event", source="test", title="Synth jam", text="Open synth jam")
    refinement = Refinement(
        record_id=record.id,
        content_kind="event",
        relevant_from=datetime(2026, 6, 5, 16, 0, tzinfo=timezone.utc),
        summary="Open synth jam",
        refiner="test",
    )

    main.print_refinement_progress(RefinementProgress(status="selected", total=1))
    main.print_refinement_progress(
        RefinementProgress(status="refining", total=1, index=1, record=record),
    )
    main.print_refinement_progress(
        RefinementProgress(
            status="refined",
            total=1,
            index=1,
            record=record,
            refinements=[refinement],
        ),
    )

    rendered = output.getvalue()
    assert "Refining 1 record(s)..." in rendered
    assert "[1/1] Synth jam" in rendered
    assert "refined 1 item(s)" in rendered
    assert "2026-06-05T16:00:00+00:00 — Open synth jam" in rendered


def test_refinement_progress_prints_empty_selection(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))

    main.print_refinement_progress(RefinementProgress(status="selected", total=0))

    assert "No unrefined records found." in output.getvalue()


def test_refine_with_id_reruns_refinement_without_updating_store(tmp_path, monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=160))
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="Raw", text="Raw text"))
    existing = Refinement(
        record_id=inserted.record.id,
        content_kind="event",
        summary="Stored summary",
        refiner="test",
    )
    store.replace_refinements(inserted.record.id, [existing])
    config = PinoConfig(
        storage=StorageConfig(local={"type": "sqlite", "path": tmp_path / "pino.sqlite"})
    )
    client = StaticRefinementClient(
        '{"content_kind": "event", "summary": "Dry run summary", "category_scores": {}}',
        reasoning="calendar reasoning trace",
    )
    monkeypatch.setattr(main, "get_config", lambda config_path: config)
    monkeypatch.setattr(main, "get_store", lambda actual_config: store)
    monkeypatch.setattr(
        main,
        "build_llm_client",
        lambda llm_config, *, usage_recorder=None: client,
    )

    main._run_refine(config_path=None, limit=None, debug=False, selected_id=f"ID {existing.id}")

    rendered = output.getvalue()
    assert "Refinement dry run" in rendered
    assert "persisted" in rendered
    assert "False" in rendered
    assert "Prompt: system" in rendered
    assert "Prompt: user" in rendered
    assert "Reasoning" in rendered
    assert "calendar reasoning trace" in rendered
    assert "Raw response" in rendered
    assert "Parsed response" in rendered
    assert "Generated refinements" in rendered
    assert "Dry run summary" in rendered
    assert "Stored summary" in rendered
    assert [message.role for message in client.messages] == ["system", "user"]
    assert store.list_refinements(inserted.record.id)[0].summary == "Stored summary"


def test_resolve_refinement_debug_target_accepts_record_id(tmp_path, monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(main, "console", Console(file=output, force_terminal=False, width=120))
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="Raw", text="Raw text"))

    record, refinement, resolved_kind = main.resolve_refinement_debug_target(
        store,
        inserted.record.id,
    )

    assert record.id == inserted.record.id
    assert refinement is None
    assert resolved_kind == "record"
