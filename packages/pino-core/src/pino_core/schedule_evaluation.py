from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import yaml
from pino_llm import (
    LLMClient,
    LLMError,
    LLMMessage,
    LLMUsage,
    UsageRecorder,
    build_llm_client,
)

from pino_core.config import PinoConfig
from pino_core.models import Record
from pino_core.quality import QCReport, RefinementQC, no_refinement_qc
from pino_core.refinement import RefinementService
from pino_core.schedules import normalize_schedule
from pino_core.storage import DatabaseStore


@dataclass(frozen=True)
class ScheduleEvalFixture:
    name: str
    record: Record
    expected_schedule: dict[str, Any] | None
    expected_kind: str


@dataclass(frozen=True)
class ScheduleEvalCorpus:
    fixtures: list[ScheduleEvalFixture]
    excluded: int


@dataclass(frozen=True)
class ScheduleEvalCase:
    fixture: str
    kind: str
    passed: bool
    status: str
    duration_ms: int
    expected: dict[str, Any] | None
    actual: dict[str, Any] | None
    raw_response: str | None
    reasoning: str | None
    qc: QCReport = QCReport()
    output_tokens: int | None = None
    generation_duration_ms: float | None = None
    tokens_per_second: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class ScheduleKindScore:
    passed: int
    total: int

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


@dataclass(frozen=True)
class ScheduleEvalSummary:
    model: str
    passed: int
    total: int
    invalid: int
    total_duration_ms: int
    min_duration_ms: int
    p50_duration_ms: int
    mean_duration_ms: int
    max_duration_ms: int
    output_tokens: int
    generation_duration_ms: float
    tokens_per_second: float | None
    by_kind: dict[str, ScheduleKindScore]

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


@dataclass(frozen=True)
class ScheduleEvalReport:
    summary: ScheduleEvalSummary
    cases: list[ScheduleEvalCase]
    excluded: int
    summary_path: Path


@dataclass(frozen=True)
class ScheduleEvalProgress:
    model: str
    completed: int
    total: int
    fixture: str
    status: str
    passed: int
    invalid: int
    elapsed_ms: int
    summary_path: Path
    case: ScheduleEvalCase | None = None
    response_path: Path | None = None
    reasoning_path: Path | None = None


def load_schedule_eval_corpus(path: Path) -> ScheduleEvalCorpus:
    fixtures: list[ScheduleEvalFixture] = []
    excluded = 0
    for fixture_path in sorted(path.glob("*.yaml"), key=lambda item: int(item.stem)):
        value = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{fixture_path}: fixture must be a mapping")
        if "ok" not in value:
            raise ValueError(f"{fixture_path}: missing ok marker")
        if value["ok"] is False:
            excluded += 1
            continue
        if value["ok"] is not True:
            raise ValueError(f"{fixture_path}: ok marker must be true or false")
        expected = _normalize_gold_schedule(value.get("schedule"), fixture_path)
        fixtures.append(
            ScheduleEvalFixture(
                name=fixture_path.stem,
                record=_fixture_record(value, fixture_path),
                expected_schedule=expected,
                expected_kind=expected["kind"] if expected is not None else "null",
            )
        )
    return ScheduleEvalCorpus(fixtures=fixtures, excluded=excluded)


def evaluate_schedule_model(
    *,
    config: PinoConfig,
    model: str,
    corpus: ScheduleEvalCorpus,
    output_dir: Path,
    limit: int | None = None,
    client: LLMClient | None = None,
    usage_recorder: UsageRecorder | None = None,
    on_progress: Callable[[ScheduleEvalProgress], None] | None = None,
    timeout_seconds: float = 15,
    quality_check: RefinementQC = no_refinement_qc,
) -> ScheduleEvalReport:
    selected = corpus.fixtures[:limit] if limit is not None else corpus.fixtures
    llm_config = config.llm.with_model(model)
    profile = llm_config.selected_profile()
    resolved_profile = profile.model_dump(mode="json", exclude_none=True)
    usage_capture = _UsageCapture(usage_recorder)
    delegate = client or build_llm_client(
        llm_config,
        usage_recorder=usage_capture,
        timeout_seconds=timeout_seconds,
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    model_dir = output_dir / _model_output_name(model) / run_id
    response_dir = model_dir / "responses"
    reasoning_dir = model_dir / "reasoning"
    summary_path = model_dir / "summary.yaml"
    model_dir.mkdir(parents=True, exist_ok=True)
    timed_client = _TimedClient(
        delegate,
        usage_capture=usage_capture if client is None else None,
    )
    service = RefinementService(
        store=DatabaseStore("sqlite:///:memory:"),
        client=timed_client,
        config=config.refinement,
        quality_check=quality_check,
        model=model,
    )
    cases: list[ScheduleEvalCase] = []
    started = perf_counter()
    _write_live_summary(
        path=summary_path,
        model=model,
        resolved_profile=resolved_profile,
        cases=cases,
        target_total=len(selected),
        excluded=corpus.excluded,
    )
    if on_progress is not None:
        on_progress(
            ScheduleEvalProgress(
                model=model,
                completed=0,
                total=len(selected),
                fixture="",
                status="started",
                passed=0,
                invalid=0,
                elapsed_ms=0,
                summary_path=summary_path,
            )
        )
    for fixture in selected:
        case = _evaluate_fixture(service, timed_client, fixture)
        cases.append(case)
        response_path = _write_response(response_dir, fixture.name, case.raw_response)
        reasoning_path = _write_reasoning(reasoning_dir, fixture.name, case.reasoning)
        _write_live_summary(
            path=summary_path,
            model=model,
            resolved_profile=resolved_profile,
            cases=cases,
            target_total=len(selected),
            excluded=corpus.excluded,
        )
        if on_progress is not None:
            on_progress(
                ScheduleEvalProgress(
                    model=model,
                    completed=len(cases),
                    total=len(selected),
                    fixture=fixture.name,
                    status=case.status,
                    passed=sum(item.passed for item in cases),
                    invalid=sum(item.status.startswith("invalid") for item in cases),
                    elapsed_ms=round((perf_counter() - started) * 1000),
                    summary_path=summary_path,
                    case=case,
                    response_path=response_path,
                    reasoning_path=reasoning_path,
                )
            )
    summary = _summarize(model, cases)
    return ScheduleEvalReport(
        summary=summary,
        cases=cases,
        excluded=corpus.excluded,
        summary_path=summary_path,
    )


def _evaluate_fixture(
    service: RefinementService,
    client: _TimedClient,
    fixture: ScheduleEvalFixture,
) -> ScheduleEvalCase:
    client.prepare(fixture.name)
    try:
        result = service.debug_refine_record(fixture.record)
    except LLMError as exc:
        return _case(fixture, client, status="invalid_response", error=str(exc))
    except Exception as exc:
        return _case(fixture, client, status="invalid_response", error=str(exc))
    if result.error is not None:
        return _case(
            fixture,
            client,
            status="invalid_response",
            error=result.error,
            qc=result.qc,
        )
    if len(result.refinements) != 1:
        return _case(
            fixture,
            client,
            status="item_count",
            error=f"expected one item, got {len(result.refinements)}",
        )
    refinement = result.refinements[0]
    raw_schedule = refinement.debug.get("raw", {}).get("schedule")
    if raw_schedule is not None and refinement.schedule is None:
        return _case(fixture, client, status="invalid_schedule", error="unusable schedule")
    expected = schedule_semantics(fixture.expected_schedule)
    actual = schedule_semantics(refinement.schedule)
    passed = actual == expected
    return ScheduleEvalCase(
        fixture=fixture.name,
        kind=fixture.expected_kind,
        passed=passed,
        status="pass" if passed else "mismatch",
        duration_ms=client.last_duration_ms,
        expected=expected,
        actual=actual,
        raw_response=client.last_response,
        reasoning=client.last_reasoning,
        qc=result.qc,
        output_tokens=client.last_output_tokens,
        generation_duration_ms=client.last_generation_duration_ms,
        tokens_per_second=client.last_tokens_per_second,
    )


def _case(
    fixture: ScheduleEvalFixture,
    client: _TimedClient,
    *,
    status: str,
    error: str,
    qc: QCReport = QCReport(),
) -> ScheduleEvalCase:
    return ScheduleEvalCase(
        fixture=fixture.name,
        kind=fixture.expected_kind,
        passed=False,
        status=status,
        duration_ms=client.last_duration_ms,
        expected=schedule_semantics(fixture.expected_schedule),
        actual=None,
        raw_response=client.last_response,
        reasoning=client.last_reasoning,
        qc=qc,
        output_tokens=client.last_output_tokens,
        generation_duration_ms=client.last_generation_duration_ms,
        tokens_per_second=client.last_tokens_per_second,
        error=error,
    )


def schedule_semantics(schedule: dict[str, Any] | None) -> dict[str, Any] | None:
    if schedule is None:
        return None
    normalized = normalize_schedule(schedule)
    if normalized is None:
        raise ValueError("invalid canonical schedule")
    if normalized["kind"] == "occurrences":
        occurrences = []
        for item in normalized["occurrences"]:
            start = datetime.fromisoformat(item["start"])
            end = datetime.fromisoformat(item["end"]) if item["end"] is not None else None
            if end is not None and end <= start:
                end += timedelta(days=1)
            occurrences.append(
                {
                    "start": start.isoformat(timespec="minutes"),
                    "end": end.isoformat(timespec="minutes") if end is not None else None,
                }
            )
        occurrences.sort(key=lambda item: (item["start"], item["end"] or ""))
        return {
            "kind": "occurrences",
            "timezone": normalized["timezone"],
            "occurrences": occurrences,
        }
    rules = [
        {
            "weekday": weekday,
            "start": rule["start"],
            "end": rule["end"],
        }
        for rule in normalized["rules"]
        for weekday in rule["weekdays"]
    ]
    rules.sort(key=lambda item: (item["weekday"], item["start"], item["end"] or ""))
    return {
        "kind": "recurrence",
        "timezone": normalized["timezone"],
        "frequency": "weekly",
        "from": normalized["from"],
        "until": normalized["until"],
        "rules": rules,
    }


def _normalize_gold_schedule(value: Any, path: Path) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{path}: schedule must be a mapping or null")
    kind = value.get("kind")
    if kind == "occurrence":
        candidate = {
            "version": 1,
            "timezone": value.get("timezone"),
            "kind": "occurrences",
            "occurrences": [
                {
                    "start": f"{item['date']}T{item['start']}",
                    "end": f"{item['date']}T{item['end']}" if item.get("end") else None,
                }
                for item in value.get("occurrences", [])
            ],
        }
    elif kind == "recurrence":
        candidate = {
            "version": 1,
            "timezone": value.get("timezone"),
            "kind": "recurrence",
            "frequency": "weekly",
            "from": value.get("from"),
            "until": value.get("until"),
            "rules": [
                {
                    "weekdays": value.get("weekdays", []),
                    "start": item.get("start"),
                    "end": item.get("end"),
                }
                for item in value.get("times", [])
            ],
        }
    else:
        raise ValueError(f"{path}: unsupported gold schedule kind {kind!r}")
    normalized = normalize_schedule(candidate)
    if normalized is None:
        raise ValueError(f"{path}: invalid gold schedule")
    return normalized


def _fixture_record(value: dict[str, Any], path: Path) -> Record:
    publication_date = value.get("publication_date")
    if not isinstance(publication_date, str):
        raise ValueError(f"{path}: publication_date must be an ISO date")
    posted_at = datetime.fromisoformat(publication_date).replace(
        hour=12,
        tzinfo=timezone.utc,
    )
    return Record(
        kind="event",
        source="afisha-vilnius",
        external_id=str(value.get("source_id") or path.stem),
        text=str(value.get("text") or ""),
        url=value.get("url"),
        payload={"posted_at_utc": posted_at.isoformat()},
    )


def _summarize(model: str, cases: list[ScheduleEvalCase]) -> ScheduleEvalSummary:
    by_kind: dict[str, ScheduleKindScore] = {}
    for kind in ("occurrences", "recurrence", "null"):
        selected = [case for case in cases if case.kind == kind]
        by_kind[kind] = ScheduleKindScore(
            passed=sum(case.passed for case in selected),
            total=len(selected),
        )
    durations = sorted(case.duration_ms for case in cases)
    measured_generation = [
        case
        for case in cases
        if case.output_tokens is not None and case.generation_duration_ms is not None
    ]
    output_tokens = sum(case.output_tokens or 0 for case in cases)
    generated_output_tokens = sum(case.output_tokens or 0 for case in measured_generation)
    generation_duration_ms = sum(case.generation_duration_ms or 0 for case in measured_generation)
    return ScheduleEvalSummary(
        model=model,
        passed=sum(case.passed for case in cases),
        total=len(cases),
        invalid=sum(case.status.startswith("invalid") for case in cases),
        total_duration_ms=sum(durations),
        min_duration_ms=durations[0] if durations else 0,
        p50_duration_ms=_median(durations),
        mean_duration_ms=round(sum(durations) / len(durations)) if durations else 0,
        max_duration_ms=durations[-1] if durations else 0,
        output_tokens=output_tokens,
        generation_duration_ms=generation_duration_ms,
        tokens_per_second=round(generated_output_tokens * 1000 / generation_duration_ms, 2)
        if generation_duration_ms > 0
        else None,
        by_kind=by_kind,
    )


def _summary_dict(summary: ScheduleEvalSummary) -> dict[str, Any]:
    return {
        "model": summary.model,
        "passed": summary.passed,
        "total": summary.total,
        "accuracy": summary.accuracy,
        "invalid": summary.invalid,
        "total_duration_ms": summary.total_duration_ms,
        "min_duration_ms": summary.min_duration_ms,
        "p50_duration_ms": summary.p50_duration_ms,
        "mean_duration_ms": summary.mean_duration_ms,
        "max_duration_ms": summary.max_duration_ms,
        "output_tokens": summary.output_tokens,
        "generation_duration_ms": summary.generation_duration_ms,
        "tokens_per_second": summary.tokens_per_second,
        "by_kind": {
            kind: {
                "passed": score.passed,
                "total": score.total,
                "accuracy": score.accuracy,
            }
            for kind, score in summary.by_kind.items()
        },
    }


def _write_live_summary(
    *,
    path: Path,
    model: str,
    resolved_profile: dict[str, Any],
    cases: list[ScheduleEvalCase],
    target_total: int,
    excluded: int,
) -> None:
    summary = _summarize(model, cases)
    value = {
        "profile": {"alias": model, **resolved_profile},
        "summary": {
            **_summary_dict(summary),
            "completed": len(cases),
            "target_total": target_total,
        },
        "excluded": excluded,
        "cases": [
            {
                "name": case.fixture,
                "error": None if case.passed else case.error or case.status,
                "duration_ms": case.duration_ms,
            }
            for case in cases
        ],
    }
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _write_response(path: Path, fixture: str, response: str | None) -> Path | None:
    if response is None:
        return None
    try:
        json.loads(response)
    except json.JSONDecodeError:
        suffix = ".txt"
    else:
        suffix = ".json"
    response_path = path / f"{fixture}{suffix}"
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(response.rstrip() + "\n", encoding="utf-8")
    return response_path


def _write_reasoning(path: Path, fixture: str, reasoning: str | None) -> Path | None:
    if reasoning is None:
        return None
    reasoning_path = path / f"{fixture}.txt"
    reasoning_path.parent.mkdir(parents=True, exist_ok=True)
    reasoning_path.write_text(reasoning.rstrip() + "\n", encoding="utf-8")
    return reasoning_path


def _median(values: list[int]) -> int:
    if not values:
        return 0
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return round((values[middle - 1] + values[middle]) / 2)


class _UsageCapture:
    def __init__(self, delegate: UsageRecorder | None) -> None:
        self.delegate = delegate
        self.last_usage: LLMUsage | None = None

    def prepare(self) -> None:
        self.last_usage = None

    def __call__(self, usage: LLMUsage) -> None:
        self.last_usage = usage
        if self.delegate is not None:
            self.delegate(usage)


class _TimedClient:
    def __init__(
        self,
        delegate: LLMClient,
        *,
        usage_capture: _UsageCapture | None = None,
    ) -> None:
        self.delegate = delegate
        self.usage_capture = usage_capture
        self.last_duration_ms = 0
        self.last_response: str | None = None
        self.last_reasoning: str | None = None
        self.last_output_tokens: int | None = None
        self.last_generation_duration_ms: float | None = None
        self.last_tokens_per_second: float | None = None

    def prepare(self, _fixture_name: str) -> None:
        if self.usage_capture is not None:
            self.usage_capture.prepare()
        self.last_duration_ms = 0
        self.last_response = None
        self.last_reasoning = None
        self.last_output_tokens = None
        self.last_generation_duration_ms = None
        self.last_tokens_per_second = None

    def complete(self, messages: list[LLMMessage], *, operation: str = "unknown") -> str:
        started = perf_counter()
        try:
            response = self.delegate.complete(messages, operation="evaluation.schedule")
        finally:
            self.last_duration_ms = round((perf_counter() - started) * 1000)
        reasoning = getattr(self.delegate, "last_reasoning", None)
        self.last_reasoning = reasoning if isinstance(reasoning, str) else None
        captured_usage = self.usage_capture.last_usage if self.usage_capture is not None else None
        output_tokens = (
            captured_usage.output_tokens
            if captured_usage is not None
            else getattr(self.delegate, "last_output_tokens", None)
        )
        self.last_output_tokens = output_tokens if isinstance(output_tokens, int) else None
        generation_duration_ms = getattr(self.delegate, "last_generation_duration_ms", None)
        self.last_generation_duration_ms = (
            float(generation_duration_ms)
            if isinstance(generation_duration_ms, int | float)
            else None
        )
        tokens_per_second = getattr(self.delegate, "last_tokens_per_second", None)
        self.last_tokens_per_second = (
            float(tokens_per_second) if isinstance(tokens_per_second, int | float) else None
        )
        self.last_response = response
        return response


def _model_output_name(model: str) -> str:
    readable = re.sub(r"[^a-zA-Z0-9._-]+", "_", model).strip("_") or "model"
    return readable
