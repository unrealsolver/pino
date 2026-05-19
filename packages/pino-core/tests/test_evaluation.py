from pathlib import Path

from pino_llm import LLMMessage

from pino_core.config import EvaluationConfig
from pino_core.evaluation import EvaluationService, build_evaluation_llm_config
from pino_core.models import Record
from pino_core.storage import SQLiteStore


class StaticClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def complete(self, messages: list[LLMMessage]) -> str:
        self.calls += 1
        return self.response


def test_evaluation_service_evaluates_pending_records(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_record(
        Record(
            kind="event",
            source="test",
            title="Synth jam",
            text="Open synth jam in Vilnius.",
        ),
    )
    client = StaticClient(
        """
        {
          "relevance": 0.9,
          "goal_matches": ["open_synth_jam", "electronic_music"],
          "language": "en",
          "summary": "Open synth jam in Vilnius.",
          "reasons": ["Participatory synth event."],
          "risks": []
        }
        """,
    )

    result = EvaluationService(store, client, EvaluationConfig()).evaluate_pending(limit=5)

    records = store.list_records()
    evaluation = store.get_evaluation(records[0].id)
    assert result.evaluated == 1
    assert evaluation is not None
    assert evaluation.score == 0.9
    assert evaluation.goal_matches == ["open_synth_jam", "electronic_music"]


def test_evaluation_service_uses_cached_evaluations(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="Metal", text="Metal gig"))
    client = StaticClient('{"relevance": 0.8, "goal_matches": ["metal_music"]}')
    service = EvaluationService(store, client, EvaluationConfig())

    service.evaluate_pending(limit=5)
    second = service.evaluate_pending(limit=5)

    assert second.requested == 0
    assert client.calls == 1
    assert store.get_evaluation(inserted.record.id) is not None


def test_evaluation_service_skips_unusable_model_response(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="Noise", text="Noise"))
    client = StaticClient('{"final": "echo provider is configured"}')

    result = EvaluationService(store, client, EvaluationConfig()).evaluate_pending(limit=5)

    assert result.requested == 1
    assert result.evaluated == 0
    assert result.skipped == 1
    assert store.get_evaluation(inserted.record.id) is None


def test_evaluation_service_filters_unknown_goal_matches(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_record(Record(kind="event", source="test", title="Metal", text="Metal gig"))
    client = StaticClient(
        '{"relevance": 0.8, "goal_matches": ["metal_music", "unknown", "metal_music"]}',
    )

    EvaluationService(store, client, EvaluationConfig()).evaluate_pending(limit=5)

    evaluation = store.list_records_with_evaluations()[0][1]
    assert evaluation is not None
    assert evaluation.goal_matches == ["metal_music"]


def test_build_evaluation_llm_config_selects_simple_model() -> None:
    from pino_llm import LLMConfig

    llm_config = build_evaluation_llm_config(
        LLMConfig(default_provider="infercom", model="smart"),
        EvaluationConfig(model="simple"),
    )

    assert llm_config.temperature == 0.0
    assert llm_config.selected_model() == "gpt-oss-120b"
