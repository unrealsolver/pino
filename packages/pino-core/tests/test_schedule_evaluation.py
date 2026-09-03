import json
from pathlib import Path

import pytest
import yaml
from pino_llm import LLMError, LLMUsage

from pino_core.config import PinoConfig
from pino_core.schedule_evaluation import (
    ScheduleEvalCase,
    _summarize,
    evaluate_schedule_model,
    load_schedule_eval_corpus,
    schedule_semantics,
)


FIXTURES = Path(__file__).parent / "integration/golden/afisha_vilnius"


def eval_config(alias: str, model: str | None = None) -> PinoConfig:
    provider, name = alias.split(":", 1)
    profile = {
        "model": model or alias,
        "temperature": 0,
    }
    if provider == "ollama":
        profile["think"] = False
    return PinoConfig(
        llm={
            "model": alias,
            "models": {provider: {name: profile}},
        },
        refinement={"model": alias},
    )


class StaticClient:
    def __init__(
        self,
        response: str,
        *,
        reasoning: str | None = None,
        output_tokens: int | None = None,
        generation_duration_ms: float | None = None,
        tokens_per_second: float | None = None,
    ) -> None:
        self.response = response
        self.last_reasoning = reasoning
        self.last_output_tokens = output_tokens
        self.last_generation_duration_ms = generation_duration_ms
        self.last_tokens_per_second = tokens_per_second
        self.calls = 0
        self.operations: list[str] = []

    def complete(self, messages, *, operation: str = "unknown") -> str:
        self.calls += 1
        self.operations.append(operation)
        return self.response


class ErrorClient:
    def complete(self, messages, *, operation: str = "unknown") -> str:
        raise LLMError(
            "ollama request timed out",
            provider="ollama",
            model="slow-model",
            url="http://localhost:11434/api/chat",
        )


def test_load_schedule_eval_corpus_uses_only_human_accepted_fixtures() -> None:
    corpus = load_schedule_eval_corpus(FIXTURES)

    assert len(corpus.fixtures) == 87
    assert corpus.excluded == 13
    assert sum(item.expected_kind == "occurrences" for item in corpus.fixtures) == 79
    assert sum(item.expected_kind == "recurrence" for item in corpus.fixtures) == 5
    assert sum(item.expected_kind == "null" for item in corpus.fixtures) == 3


@pytest.mark.parametrize("marker", [None, "true", 1])
def test_load_schedule_eval_corpus_rejects_missing_or_invalid_ok(
    tmp_path: Path,
    marker,
) -> None:
    content = "publication_date: '2026-01-01'\ntext: Example\nschedule: null\n"
    if marker is not None:
        content += f"ok: {json.dumps(marker)}\n"
    (tmp_path / "001.yaml").write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="ok"):
        load_schedule_eval_corpus(tmp_path)


def test_schedule_semantics_ignores_rule_grouping_and_overnight_notation() -> None:
    grouped = {
        "version": 1,
        "timezone": "Europe/Vilnius",
        "kind": "recurrence",
        "frequency": "weekly",
        "from": "2026-08-01",
        "until": None,
        "rules": [{"weekdays": ["friday", "monday"], "start": "23:30", "end": "01:00"}],
    }
    split = {
        **grouped,
        "rules": [
            {"weekdays": ["monday"], "start": "23:30", "end": "01:00"},
            {"weekdays": ["friday"], "start": "23:30", "end": "01:00"},
        ],
    }

    assert schedule_semantics(grouped) == schedule_semantics(split)


def test_schedule_eval_summary_includes_basic_duration_statistics() -> None:
    cases = [
        ScheduleEvalCase(
            fixture=str(index),
            kind="occurrences",
            passed=True,
            status="pass",
            duration_ms=duration,
            expected=None,
            actual=None,
            raw_response=None,
            reasoning=None,
            output_tokens=10 * (index + 1),
            generation_duration_ms=100 * (index + 1),
            tokens_per_second=100.0,
        )
        for index, duration in enumerate([100, 200, 900, 1_000])
    ]

    summary = _summarize("model", cases)

    assert summary.total_duration_ms == 2_200
    assert summary.min_duration_ms == 100
    assert summary.p50_duration_ms == 550
    assert summary.mean_duration_ms == 550
    assert summary.max_duration_ms == 1_000
    assert summary.output_tokens == 100
    assert summary.generation_duration_ms == 1_000
    assert summary.tokens_per_second == 100.0


def test_schedule_eval_counts_provider_timeout_and_continues(tmp_path: Path) -> None:
    corpus = load_schedule_eval_corpus(FIXTURES)

    report = evaluate_schedule_model(
        config=eval_config("ollama:slow", "slow-model"),
        model="ollama:slow",
        corpus=corpus,
        output_dir=tmp_path,
        limit=1,
        client=ErrorClient(),
    )

    assert report.summary.total == report.summary.invalid == 1
    assert report.cases[0].status == "invalid_response"
    assert report.cases[0].error == "ollama request timed out"
    stored = yaml.safe_load(report.summary_path.read_text(encoding="utf-8"))
    assert stored["cases"] == [
        {
            "name": report.cases[0].fixture,
            "error": "ollama request timed out",
            "duration_ms": report.cases[0].duration_ms,
        }
    ]


def test_schedule_eval_accepts_registered_non_ollama_profile(tmp_path: Path) -> None:
    report = evaluate_schedule_model(
        config=eval_config("minimax:test", "MiniMax-M3"),
        model="minimax:test",
        corpus=load_schedule_eval_corpus(FIXTURES),
        output_dir=tmp_path,
        limit=1,
        client=StaticClient("{}"),
    )

    assert report.summary.total == report.summary.invalid == 1


def test_schedule_eval_rejects_unknown_profile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown LLM model profile"):
        evaluate_schedule_model(
            config=PinoConfig(),
            model="minimax:missing",
            corpus=load_schedule_eval_corpus(FIXTURES),
            output_dir=tmp_path,
            limit=1,
            client=StaticClient("{}"),
        )


def test_schedule_eval_builds_provider_client_and_captures_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[LLMUsage] = []

    class UsageClient:
        def __init__(self, usage_recorder) -> None:
            self.usage_recorder = usage_recorder

        def complete(self, messages, *, operation: str = "unknown") -> str:
            self.usage_recorder(
                LLMUsage(
                    provider="minimax",
                    model="MiniMax-M3",
                    operation=operation,
                    input_tokens=100,
                    output_tokens=7,
                    cached_input_tokens=25,
                    duration_ms=50,
                )
            )
            return "{}"

    def fake_build_llm_client(config, *, usage_recorder, timeout_seconds):
        assert config.selected_provider() == "minimax"
        assert timeout_seconds == 15
        return UsageClient(usage_recorder)

    monkeypatch.setattr(
        "pino_core.schedule_evaluation.build_llm_client",
        fake_build_llm_client,
    )

    report = evaluate_schedule_model(
        config=eval_config("minimax:test", "MiniMax-M3"),
        model="minimax:test",
        corpus=load_schedule_eval_corpus(FIXTURES),
        output_dir=tmp_path,
        limit=1,
        usage_recorder=recorded.append,
    )

    assert report.summary.output_tokens == 7
    assert report.summary.tokens_per_second is None
    assert recorded[0].operation == "evaluation.schedule"


def test_evaluate_schedule_model_always_runs_fresh_and_writes_report(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "001.yaml").write_text(
        """publication_date: '2026-05-31'
text: Concert on 1 June from 18:30 to 20:10.
schedule:
  kind: occurrence
  timezone: Europe/Vilnius
  occurrences:
    - date: '2026-06-01'
      start: '18:30'
      end: '20:10'
ok: true
""",
        encoding="utf-8",
    )
    response = json.dumps(
        {
            "content_kind": "event",
            "summary": "Concert",
            "schedule": {
                "version": 1,
                "timezone": "Europe/Vilnius",
                "kind": "occurrences",
                "occurrences": [
                    {
                        "start": "2026-06-01T18:30",
                        "end": "2026-06-01T20:10",
                    }
                ],
            },
            "location": None,
            "category_scores": {},
        }
    )
    client = StaticClient(
        response,
        reasoning="I matched the explicit date and time.",
        output_tokens=50,
        generation_duration_ms=250,
        tokens_per_second=200,
    )
    corpus = load_schedule_eval_corpus(fixture_dir)
    output_dir = tmp_path / "output"
    progress = []
    snapshots = []

    def capture_progress(item) -> None:
        progress.append(item)
        snapshots.append(yaml.safe_load(item.summary_path.read_text(encoding="utf-8")))

    first = evaluate_schedule_model(
        config=eval_config("ollama:test", "test-model"),
        model="ollama:test",
        corpus=corpus,
        output_dir=output_dir,
        client=client,
        on_progress=capture_progress,
    )
    second = evaluate_schedule_model(
        config=eval_config("ollama:test", "test-model"),
        model="ollama:test",
        corpus=corpus,
        output_dir=output_dir,
        client=client,
    )

    assert client.calls == 2
    assert client.operations == ["evaluation.schedule", "evaluation.schedule"]
    assert [item.status for item in progress] == ["started", "pass"]
    assert progress[1].fixture == "001"
    assert progress[1].completed == progress[1].total == progress[1].passed == 1
    assert [item["summary"]["completed"] for item in snapshots] == [0, 1]
    assert first.summary.passed == first.summary.total == 1
    assert first.cases[0].raw_response == response
    assert first.summary_path.name == "summary.yaml"
    stored = yaml.safe_load(second.summary_path.read_text(encoding="utf-8"))
    assert stored["summary"]["accuracy"] == 1.0
    assert stored["summary"]["output_tokens"] == 50
    assert stored["summary"]["generation_duration_ms"] == 250.0
    assert stored["summary"]["tokens_per_second"] == 200.0
    assert stored["profile"] == {
        "alias": "ollama:test",
        "provider": "ollama",
        "model": "test-model",
        "temperature": 0.0,
        "top_p": 0.1,
        "think": False,
    }
    assert stored["cases"] == [
        {
            "name": "001",
            "error": None,
            "duration_ms": second.cases[0].duration_ms,
        }
    ]
    assert (second.summary_path.parent / "responses/001.json").read_text(
        encoding="utf-8"
    ).strip() == response
    assert (second.summary_path.parent / "reasoning/001.txt").read_text(
        encoding="utf-8"
    ).strip() == "I matched the explicit date and time."


def test_schedule_eval_report_keeps_raw_response_for_mismatch(tmp_path: Path) -> None:
    response = json.dumps(
        {
            "content_kind": "event",
            "schedule": None,
            "category_scores": {},
        }
    )

    report = evaluate_schedule_model(
        config=eval_config("ollama:wrong", "wrong-model"),
        model="ollama:wrong",
        corpus=load_schedule_eval_corpus(FIXTURES),
        output_dir=tmp_path,
        limit=1,
        client=StaticClient(response),
    )

    assert report.cases[0].status == "mismatch"
    assert report.cases[0].raw_response == response
    stored = yaml.safe_load(report.summary_path.read_text(encoding="utf-8"))
    assert stored["cases"] == [
        {
            "name": report.cases[0].fixture,
            "error": "mismatch",
            "duration_ms": report.cases[0].duration_ms,
        }
    ]
    response_path = report.summary_path.parent / "responses/001.json"
    assert response_path.read_text(encoding="utf-8").strip() == response
