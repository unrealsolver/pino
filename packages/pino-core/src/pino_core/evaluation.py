from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pino_llm import LLMClient, LLMMessage

from pino_core.config import EvaluationConfig
from pino_core.models import Evaluation, Record
from pino_core.storage import SQLiteStore


@dataclass(frozen=True)
class EvaluationRunResult:
    requested: int
    evaluated: int
    skipped: int


class EvaluationResponseError(RuntimeError):
    """Raised when the model does not return a usable evaluation payload."""


class EvaluationService:
    """Evaluate records against configured goals with a bounded LLM classifier."""

    def __init__(
        self,
        store: SQLiteStore,
        client: LLMClient,
        config: EvaluationConfig,
    ) -> None:
        self.store = store
        self.client = client
        self.config = config

    def evaluate_pending(self, limit: int | None = None) -> EvaluationRunResult:
        self.store.init_schema()
        records = self.store.list_unevaluated_records(limit=limit or self.config.batch_size)
        evaluated = 0
        skipped = 0

        for record in records:
            if self.store.get_evaluation(record.id) is not None:
                skipped += 1
                continue
            try:
                evaluation = self.evaluate_record(record)
            except EvaluationResponseError:
                skipped += 1
                continue
            self.store.add_evaluation(evaluation)
            evaluated += 1

        return EvaluationRunResult(requested=len(records), evaluated=evaluated, skipped=skipped)

    def evaluate_record(self, record: Record) -> Evaluation:
        raw_response = self.client.complete(
            [
                LLMMessage(role="system", content=self._system_prompt()),
                LLMMessage(role="user", content=self._record_prompt(record)),
            ],
        )
        data = _parse_json_object(raw_response)
        if "relevance" not in data and "score" not in data:
            raise EvaluationResponseError("evaluation response is missing relevance score")
        return Evaluation(
            record_id=record.id,
            score=_clamp_score(data.get("relevance", data.get("score", 0))),
            goal_matches=_goal_matches(data.get("goal_matches"), self.config),
            language=_optional_string(data.get("language")),
            summary=_optional_string(data.get("summary")),
            reasons=_string_list(data.get("reasons")),
            risks=_string_list(data.get("risks")),
            payload={
                "model_task": "record_evaluation",
                "raw": data,
            },
        )

    def _system_prompt(self) -> str:
        goals = "\n".join(f"- {goal.name}: {goal.description}" for goal in self.config.goals)
        return (
            "You evaluate event/source records for Pino, a local personal assistant.\n"
            "The user is Boss/Ruslan in Vilnius. He wants only useful, actionable items.\n"
            "Evaluate multilingual text. Lithuanian, Russian, and English may appear.\n"
            "Return strict JSON only. No markdown, no prose outside JSON.\n\n"
            "Goals:\n"
            f"{goals}\n\n"
            "JSON schema:\n"
            "{\n"
            '  "relevance": 0.0,\n'
            '  "goal_matches": ["goal_name"],\n'
            '  "language": "lt|ru|en|mixed|unknown",\n'
            '  "summary": "one concise English sentence",\n'
            '  "reasons": ["short reason"],\n'
            '  "risks": ["short caveat"]\n'
            "}\n"
            "Use relevance 0 for irrelevant records and 1 for highly actionable records."
        )

    def _record_prompt(self, record: Record) -> str:
        payload = {
            "id": record.id,
            "kind": record.kind,
            "source": record.source,
            "title": record.title,
            "text": record.text,
            "url": record.url,
            "payload": record.payload,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


def build_evaluation_llm_config(config, evaluation_config: EvaluationConfig):
    return config.model_copy(
        update={
            "model": evaluation_config.model,
            "temperature": 0.0,
        },
    )


def _parse_json_object(raw_response: str) -> dict[str, Any]:
    stripped = raw_response.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _goal_matches(value: Any, config: EvaluationConfig) -> list[str]:
    allowed = {goal.name for goal in config.goals}
    matches: list[str] = []
    for item in _string_list(value):
        if item in allowed and item not in matches:
            matches.append(item)
    return matches


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
