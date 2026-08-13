from pathlib import Path

from pino_llm import LLMMessage

from pino_core.config import RefinementConfig
from pino_core.models import Record
from pino_core.refinement import (
    RefinementService,
    _parse_json_object,
    build_refinement_llm_config,
    render_refinement_system_prompt,
)
from pino_core.storage import SQLiteStore


class StaticClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0
        self.messages: list[list[LLMMessage]] = []

    def complete(self, messages: list[LLMMessage]) -> str:
        self.calls += 1
        self.messages.append(messages)
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


def test_refinement_messages_keep_static_prompt_before_dynamic_record_data(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    first = store.add_record(Record(kind="event", source="test", title="One", text="First event"))
    second = store.add_record(
        Record(kind="event", source="test", title="Two", text="Different event")
    )
    client = StaticClient('{"items": [{"content_kind": "event", "category_scores": {}}]}')
    service = RefinementService(store, client, RefinementConfig())

    service.refine_record(first.record)
    service.refine_record(second.record)

    assert len(client.messages) == 2
    assert [message.role for message in client.messages[0]] == ["system", "user"]
    assert [message.role for message in client.messages[1]] == ["system", "user"]
    assert client.messages[0][0].content == client.messages[1][0].content
    assert client.messages[0][1].content != client.messages[1][1].content


def test_refinement_record_prompt_omits_storage_ids_and_source_telemetry(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(
            kind="telegram_message",
            source="afisha-vilnius",
            title="Swing dancing",
            text="Social swing dancing at Kitas Krantas, 20:00-23:00.",
            url="https://t.me/afishavilnius/12041",
            payload={
                "channel": "https://t.me/afishavilnius",
                "message_id": 12041,
                "posted_at_utc": "2026-06-09T07:52:38+00:00",
                "sender_id": -1001567131822,
                "views": 703,
                "forwards": 7,
                "post_author": None,
                "location_scopes": ["LT/vilnius"],
            },
        )
    )
    client = StaticClient('{"items": [{"content_kind": "event", "category_scores": {}}]}')

    RefinementService(store, client, RefinementConfig()).refine_record(inserted.record)

    record_prompt = client.messages[0][1].content
    assert inserted.record.id not in record_prompt
    assert "message_id" not in record_prompt
    assert "posted_at_utc" not in record_prompt
    assert "sender_id" not in record_prompt
    assert "views" not in record_prompt
    assert "forwards" not in record_prompt
    assert "post_author" not in record_prompt
    assert '"location_scopes": [' in record_prompt


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


def test_refinement_service_stores_valid_schedule_without_frequency(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="event", source="test", title="Tuesday", text="Every Tuesday at 19:00")
    )
    client = StaticClient(
        """
        {"items": [{
          "content_kind": "event",
          "summary": "Tuesday event",
          "schedule": {
            "timezone": "Europe/Vilnius",
            "kind": "recurrence",
            "rules": [{"days": ["TU"], "start": "19:00", "end": null}],
            "exceptions": [],
            "source_text": "Every Tuesday at 19:00"
          },
          "category_scores": {}
        }]}
        """,
    )

    RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    assert store.list_refinements(inserted.record.id)[0].schedule == {
        "timezone": "Europe/Vilnius",
        "kind": "recurrence",
        "rules": [{"days": ["TU"], "start": "19:00", "end": None}],
        "exceptions": [],
        "source_text": "Every Tuesday at 19:00",
    }


def test_refinement_service_coalesces_expanded_weekly_occurrences(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Swing outdoors",
            text="Swing dance party every Thursday in June at 20:00.",
        )
    )
    client = StaticClient(
        """
        {"items": [
          {
            "content_kind": "event",
            "summary": "Outdoor social swing dancing with a free basics lesson.",
            "relevant_from": "2026-06-11T20:00:00+03:00",
            "relevant_to": "2026-06-11T23:00:00+03:00",
            "schedule": null,
            "location": "Kitas Krantas, Vilnius",
            "category_scores": {"social": 0.9, "workshop": 0.3}
          },
          {
            "content_kind": "event",
            "summary": "Outdoor social swing dancing with a free basics lesson.",
            "relevant_from": "2026-06-18T20:00:00+03:00",
            "relevant_to": "2026-06-18T23:00:00+03:00",
            "schedule": null,
            "location": "Kitas Krantas, Vilnius",
            "category_scores": {"social": 0.9, "workshop": 0.3}
          },
          {
            "content_kind": "event",
            "summary": "Outdoor social swing dancing with a free basics lesson.",
            "relevant_from": "2026-06-25T20:00:00+03:00",
            "relevant_to": "2026-06-25T23:00:00+03:00",
            "schedule": null,
            "location": "Kitas Krantas, Vilnius",
            "category_scores": {"social": 0.9, "workshop": 0.3}
          }
        ]}
        """,
    )

    RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    refinements = store.list_refinements(inserted.record.id)
    assert len(refinements) == 1
    assert refinements[0].relevant_from is not None
    assert refinements[0].relevant_from.isoformat() == "2026-06-11T17:00:00+00:00"
    assert refinements[0].relevant_to is not None
    assert refinements[0].relevant_to.isoformat() == "2026-06-25T20:00:00+00:00"
    assert refinements[0].schedule == {
        "timezone": "Europe/Vilnius",
        "kind": "recurrence",
        "rules": [{"days": ["TH"], "start": "20:00", "end": "23:00"}],
        "exceptions": [],
    }


def test_refinement_service_drops_schedule_rules_with_frequency(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="event", source="test", title="Tuesday", text="Every Tuesday at 19:00")
    )
    client = StaticClient(
        """
        {"items": [{
          "content_kind": "event",
          "summary": "Tuesday event",
          "schedule": {
            "timezone": "Europe/Vilnius",
            "kind": "recurrence",
            "rules": [{"frequency": "weekly", "days": ["TU"], "start": "19:00"}],
            "exceptions": []
          },
          "category_scores": {}
        }]}
        """,
    )

    RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    assert store.list_refinements(inserted.record.id)[0].schedule is None


def test_refinement_prompt_prefers_schedule_for_repeated_instances() -> None:
    prompt = render_refinement_system_prompt(RefinementConfig())

    assert "Prefer one item with a recurrence schedule" in prompt
    assert "Only return multiple items when the source describes genuinely different events" in prompt
    assert "not as duplicate individual occurrences" in prompt
    assert '"schedule": null | {' in prompt
    assert '"kind": "opening_hours|recurrence"' in prompt
    assert '"rules": [' in prompt
    assert '"days": ["MO|TU|WE|TH|FR|SA|SU"]' in prompt


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


def test_parse_json_object_reads_markdown_fenced_model_json() -> None:
    parsed = _parse_json_object(
        """
        ```json
        {"items": [{"content_kind": "event", "category_scores": {}}]}
        ```
        """,
    )

    assert parsed["items"][0]["content_kind"] == "event"


def test_parse_json_object_skips_invalid_brace_blocks_before_valid_json() -> None:
    parsed = _parse_json_object(
        """
        Here is the response shape: {items: [...]}

        {
          "items": [
            {
              "content_kind": "event",
              "summary": "Valid object",
              "category_scores": {}
            }
          ]
        }
        """,
    )

    assert parsed["items"][0]["summary"] == "Valid object"


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
