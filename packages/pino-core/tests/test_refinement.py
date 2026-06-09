from pathlib import Path

from pino_llm import LLMMessage

from pino_core.config import RefinementConfig
from pino_core.models import Record
from pino_core.refinement import RefinementService, build_refinement_llm_config
from pino_core.storage import SQLiteStore


class StaticClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def complete(self, messages: list[LLMMessage]) -> str:
        self.calls += 1
        return self.response


def test_refinement_service_refines_pending_records(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(
            kind="telegram_message",
            source="test",
            title="Synth jam",
            text="Open synth jam in Vilnius.",
        ),
    )
    client = StaticClient(
        """
        {
          "items": [{
            "content_kind": "event",
            "summary": "Open synth jam in Vilnius.",
            "relevant_from": "2026-06-05T16:00:00Z",
            "relevant_to": "2026-06-05T20:00:00Z",
            "location": "Example venue",
            "category_scores": {"open_synth_jam": 0.9, "electronic_music": 0.8}
          }]
        }
        """,
    )

    result = RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    refinements = store.list_refinements(inserted.record.id)
    assert result.refined == 1
    assert result.items == 1
    assert refinements[0].content_kind == "event"
    assert refinements[0].category_scores == {"open_synth_jam": 0.9, "electronic_music": 0.8}
    assert refinements[0].relevant_from is not None
    assert refinements[0].relevant_from.isoformat() == "2026-06-05T16:00:00+00:00"


def test_refinement_service_supports_multiple_items(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="telegram_message", source="test", text="Two weekend events")
    )
    client = StaticClient(
        """
        {"items": [
          {"content_kind": "event", "summary": "First event", "category_scores": {}},
          {"content_kind": "event", "summary": "Second event", "category_scores": {}}
        ]}
        """,
    )

    result = RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    refinements = store.list_refinements(inserted.record.id)
    assert result.items == 2
    assert [refinement.item_index for refinement in refinements] == [0, 1]
    assert [refinement.summary for refinement in refinements] == ["First event", "Second event"]


def test_refinement_service_uses_cached_refinements(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_record(Record(kind="event", source="test", title="Metal", text="Metal gig"))
    client = StaticClient(
        '{"items": [{"content_kind": "event", "category_scores": {"metal_music": 0.8}}]}'
    )
    service = RefinementService(store, client, RefinementConfig())

    service.refine_pending(limit=5)
    second = service.refine_pending(limit=5)

    assert second.requested == 0
    assert client.calls == 1


def test_refinement_service_skips_unusable_model_response(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="Noise", text="Noise"))
    client = StaticClient('{"final": "echo provider is configured"}')

    result = RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    assert result.requested == 1
    assert result.refined == 0
    assert result.skipped == 1
    assert store.list_refinements(inserted.record.id) == []


def test_refinement_service_filters_unknown_categories(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="event", source="test", title="Metal", text="Metal gig")
    )
    client = StaticClient(
        '{"items": [{"content_kind": "event", "category_scores": {"metal_music": 0.8, "unknown": 1}}]}',
    )

    RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    assert store.list_refinements(inserted.record.id)[0].category_scores == {"metal_music": 0.8}


def test_refinement_service_debug_refine_record_does_not_update_store(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="Debug", text="Debug me"))
    client = StaticClient(
        '{"items": [{"content_kind": "event", "summary": "Debug result", "category_scores": {}}]}'
    )

    result = RefinementService(store, client, RefinementConfig()).debug_refine_record(
        inserted.record
    )

    assert result.record.id == inserted.record.id
    assert [message.role for message in result.messages] == ["system", "user"]
    assert result.parsed_response["items"][0]["summary"] == "Debug result"
    assert result.refinements[0].summary == "Debug result"
    assert result.error is None
    assert store.list_refinements(inserted.record.id) == []


def test_refinement_service_debug_refine_record_returns_parse_error(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="Debug", text="Debug me"))
    client = StaticClient('{"final": "not refinement json"}')

    result = RefinementService(store, client, RefinementConfig()).debug_refine_record(
        inserted.record
    )

    assert result.raw_response == '{"final": "not refinement json"}'
    assert result.parsed_response == {"final": "not refinement json"}
    assert result.refinements == []
    assert result.error == "refinement response is missing items"


def test_build_refinement_llm_config_selects_simple_model() -> None:
    from pino_llm import LLMConfig

    llm_config = build_refinement_llm_config(
        LLMConfig(default_provider="infercom", model="smart"),
        RefinementConfig(model="simple"),
    )

    assert llm_config.temperature == 0.0
    assert llm_config.selected_model() == "gpt-oss-120b"


def test_refinement_service_emits_progress_events(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_record(Record(kind="event", source="test", title="Synth jam", text="Open synth jam"))
    client = StaticClient('{"items": [{"content_kind": "event", "category_scores": {}}]}')
    events = []

    result = RefinementService(store, client, RefinementConfig()).refine_pending(
        limit=5,
        on_progress=events.append,
    )

    assert result.refined == 1
    assert [event.status for event in events] == ["selected", "refining", "refined"]
    assert events[0].total == 1
    assert events[1].index == 1
    assert events[1].record is not None
    assert events[1].record.title == "Synth jam"
    assert events[2].refinements is not None
    assert len(events[2].refinements) == 1
