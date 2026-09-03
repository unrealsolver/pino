import json
from pathlib import Path

from pino_llm import LLMMessage

from pino_core.config import RefinementConfig
from pino_core.models import Record
from pino_core.quality import QCFlag, QCReport
from pino_core.refinement import (
    QC_REJECTED_REFINER,
    RefinementService,
    _parse_json_object,
    build_refinement_llm_config,
    render_refinement_system_prompt,
)
from pino_core.storage import SQLiteStore


class StaticClient:
    def __init__(self, response: str, *, reasoning: str | None = None) -> None:
        self.response = response
        self.last_reasoning = reasoning
        self.calls = 0
        self.messages: list[list[LLMMessage]] = []

    def complete(self, messages: list[LLMMessage], *, operation: str = "unknown") -> str:
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
          "content_kind": "event",
          "summary": "Open synth jam in Vilnius.",
          "schedule": {
            "version": 1,
            "timezone": "Europe/Vilnius",
            "kind": "occurrences",
            "occurrences": [{
              "start": "2026-06-05T19:00",
              "end": "2026-06-05T23:00"
            }]
          },
          "location": "Example venue",
          "category_scores": {"open_synth_jam": 0.9, "electronic_music": 0.8}
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
    assert refinements[0].relevant_to is not None
    assert refinements[0].relevant_to.isoformat() == "2026-06-05T20:00:00+00:00"


def test_refinement_service_skips_model_error(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="telegram_message", source="test", text="Two weekend events")
    )
    client = StaticClient('{"error": "source contains multiple distinct events"}')

    result = RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    assert result.refined == 0
    assert result.skipped == 1
    assert store.list_refinements(inserted.record.id) == []
    assert [record.id for record in store.list_unrefined_records()] == [inserted.record.id]


def test_refinement_service_uses_cached_refinements(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_record(Record(kind="event", source="test", title="Metal", text="Metal gig"))
    client = StaticClient('{"content_kind": "event", "category_scores": {"metal_music": 0.8}}')
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
    client = StaticClient('{"content_kind": "event", "category_scores": {}}')
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
    client = StaticClient('{"content_kind": "event", "category_scores": {}}')

    RefinementService(store, client, RefinementConfig()).refine_record(inserted.record)

    record_prompt = client.messages[0][1].content
    prompt_payload = json.loads(record_prompt)
    assert prompt_payload["publication_date"] == "2026-06-09"
    assert prompt_payload["kind"] == "telegram_message"
    assert prompt_payload["source"] == "afisha-vilnius"
    assert inserted.record.id not in record_prompt
    assert "message_id" not in record_prompt
    assert "posted_at_utc" not in record_prompt
    assert "sender_id" not in record_prompt
    assert "views" not in record_prompt
    assert "forwards" not in record_prompt
    assert "post_author" not in record_prompt
    assert '"location_scopes": [' in record_prompt


def test_refinement_record_prompt_omits_publication_date_when_post_date_is_missing(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(
            kind="event",
            source="test",
            title="Today event",
            text="Happening today at 19:00.",
        )
    )
    client = StaticClient('{"content_kind": "event", "category_scores": {}}')

    RefinementService(store, client, RefinementConfig()).refine_record(inserted.record)

    prompt_payload = json.loads(client.messages[0][1].content)
    assert "publication_date" not in prompt_payload


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
        '{"content_kind": "event", "category_scores": {"metal_music": 0.8, "unknown": 1}}',
    )

    RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    assert store.list_refinements(inserted.record.id)[0].category_scores == {"metal_music": 0.8}


def test_refinement_service_stores_valid_occurrence_schedule(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="event", source="test", title="Tuesday", text="Every Tuesday at 19:00")
    )
    client = StaticClient(
        """
        {
          "content_kind": "event",
          "summary": "Tuesday event",
          "schedule": {
            "version": 1,
            "timezone": "Europe/Vilnius",
            "kind": "occurrences",
            "occurrences": [{"start": "2026-06-09T19:00", "end": null}]
          },
          "category_scores": {}
        }
        """,
    )

    RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    assert store.list_refinements(inserted.record.id)[0].schedule == {
        "version": 1,
        "timezone": "Europe/Vilnius",
        "kind": "occurrences",
        "occurrences": [{"start": "2026-06-09T19:00", "end": None}],
    }


def test_refinement_service_ignores_model_relevance_fields(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(
            kind="announcement",
            source="test",
            title="Venue notice",
            text="General venue notice without an event schedule.",
        )
    )
    client = StaticClient(
        """
        {
            "content_kind": "announcement",
            "summary": "General venue notice.",
            "relevant_from": "2026-06-11T20:00:00+03:00",
            "relevant_to": "2026-06-11T23:00:00+03:00",
            "schedule": null,
            "location": "Example venue",
            "category_scores": {}
        }
        """,
    )

    RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    refinement = store.list_refinements(inserted.record.id)[0]
    assert refinement.relevant_from is None
    assert refinement.relevant_to is None
    assert refinement.schedule is None


def test_refinement_service_drops_schedule_rules_with_frequency(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(
        Record(kind="event", source="test", title="Tuesday", text="Every Tuesday at 19:00")
    )
    client = StaticClient(
        """
        {
          "content_kind": "event",
          "summary": "Tuesday event",
          "schedule": {
            "timezone": "Europe/Vilnius",
            "kind": "recurrence",
            "rules": [{"frequency": "weekly", "days": ["TU"], "start": "19:00"}],
            "exceptions": []
          },
          "category_scores": {}
        }
        """,
    )

    RefinementService(store, client, RefinementConfig()).refine_pending(limit=5)

    assert store.list_refinements(inserted.record.id)[0].schedule is None


def test_refinement_prompt_prefers_schedule_for_repeated_instances() -> None:
    prompt = render_refinement_system_prompt(RefinementConfig())

    assert "Prefer one item with a recurrence schedule" in prompt
    assert "Return exactly one normalized item object" in prompt
    assert '{"error": "short reason"}' in prompt
    assert "When publication_date is present" in prompt
    assert "Do not calculate, verify, or correct weekdays from date lists" in prompt
    assert "Use schedule kind occurrences" in prompt
    assert "recurrence for a stated weekly pattern" in prompt
    assert "local to the schedule timezone" in prompt
    assert "omit zero-score categories" in prompt
    assert "relevant_from" not in prompt
    assert "relevant_to" not in prompt
    assert "source_text" not in prompt
    assert '"items"' not in prompt
    assert '"schedule": null | {' in prompt
    assert '"kind": "occurrences"' in prompt
    assert '"kind": "recurrence"' in prompt
    assert '"occurrences": [' in prompt
    assert '"rules": [' in prompt
    assert '"weekdays": ["monday|tuesday|wednesday|thursday|friday|saturday|sunday"]' in prompt
    assert "MO|TU|WE|TH|FR|SA|SU" not in prompt


def test_refinement_service_debug_refine_record_does_not_update_store(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="Debug", text="Debug me"))
    client = StaticClient(
        '{"content_kind": "event", "summary": "Debug result", "category_scores": {}}'
    )

    result = RefinementService(store, client, RefinementConfig()).debug_refine_record(
        inserted.record
    )

    assert result.record.id == inserted.record.id
    assert [message.role for message in result.messages] == ["system", "user"]
    assert result.parsed_response["summary"] == "Debug result"
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
    assert result.error == "refinement response is missing an item"


def test_refinement_service_debug_refine_record_includes_provider_reasoning(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", title="Debug", text="Debug me"))
    client = StaticClient(
        '{"content_kind": "event", "summary": "Dry run", "category_scores": {}}',
        reasoning="provider thinking trace",
    )

    result = RefinementService(store, client, RefinementConfig()).debug_refine_record(
        inserted.record
    )

    assert result.reasoning == "provider thinking trace"
    assert result.refinements[0].summary == "Dry run"


def test_refinement_qc_error_blocks_persistence(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", text="Event #4июня"))
    client = StaticClient('{"content_kind": "event", "summary": "Event", "category_scores": {}}')
    qc = QCReport(schedule=QCFlag("error", "tagged date is missing"))
    progress = []

    result = RefinementService(
        store,
        client,
        RefinementConfig(),
        quality_check=lambda record, refinement: qc,
    ).refine_pending(on_progress=progress.append)

    assert result.refined == 0
    assert result.skipped == 1
    stored = store.list_refinements(inserted.record.id)
    assert len(stored) == 1
    assert stored[0].refiner == QC_REJECTED_REFINER
    assert stored[0].content_kind == "unknown"
    assert stored[0].summary is None
    assert stored[0].schedule is None
    assert stored[0].category_scores == {}
    assert store.list_unrefined_records() == []
    assert progress[-1].qc == qc
    assert progress[-1].reason == "schedule QC error: tagged date is missing"


def test_refinement_qc_warning_is_carried_across_persistence_boundary(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    inserted = store.add_record(Record(kind="event", source="test", text="Event #4июня"))
    client = StaticClient('{"content_kind": "event", "summary": "Event", "category_scores": {}}')
    qc = QCReport(schedule=QCFlag("warning", "schedule has an extra date"))
    progress = []

    result = RefinementService(
        store,
        client,
        RefinementConfig(),
        quality_check=lambda record, refinement: qc,
    ).refine_pending(on_progress=progress.append)

    assert result.refined == 1
    assert len(store.list_refinements(inserted.record.id)) == 1
    assert progress[-1].qc == qc


def test_parse_json_object_reads_markdown_fenced_model_json() -> None:
    parsed = _parse_json_object(
        """
        ```json
        {"content_kind": "event", "category_scores": {}}
        ```
        """,
    )

    assert parsed["content_kind"] == "event"


def test_parse_json_object_skips_invalid_brace_blocks_before_valid_json() -> None:
    parsed = _parse_json_object(
        """
        Here is the response shape: {items: [...]}

        {
          "content_kind": "event",
          "summary": "Valid object",
          "category_scores": {}
        }
        """,
    )

    assert parsed["summary"] == "Valid object"


def test_parse_json_object_prefers_items_over_reasoning_json_fragments() -> None:
    parsed = _parse_json_object(
        """
        <think>
        Schedule should be:
        - rules: [{"days": ["TH"], "start": "20:00", "end": "23:00"}]
        </think>

        {
          "content_kind": "event",
          "summary": "Valid response",
          "category_scores": {}
        }
        """,
    )

    assert parsed["summary"] == "Valid response"


def test_build_refinement_llm_config_selects_registered_profile() -> None:
    from pino_llm import LLMConfig

    llm_config = build_refinement_llm_config(
        LLMConfig(
            roles={"chat": "infercom:general", "refine": "infercom:precise"},
            models={
                "infercom": {
                    "general": {
                        "model": "MiniMax-M2.5",
                    },
                    "precise": {
                        "model": "gpt-oss-120b",
                        "temperature": 0,
                    },
                },
            },
        ),
    )

    assert llm_config.model == "infercom:precise"
    assert llm_config.selected_profile().temperature == 0.0
    assert llm_config.selected_model() == "gpt-oss-120b"


def test_refinement_service_emits_progress_events(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "pino.sqlite")
    store.init_schema()
    store.add_record(Record(kind="event", source="test", title="Synth jam", text="Open synth jam"))
    client = StaticClient('{"content_kind": "event", "category_scores": {}}')
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
