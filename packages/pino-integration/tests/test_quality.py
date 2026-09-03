from datetime import datetime, timezone

from pino_core.config import SourceConfig
from pino_core.models import Record, Refinement

from pino_integration.quality import build_refinement_qc, check_afisha_vilnius


def test_afisha_occurrences_must_contain_all_tagged_dates() -> None:
    report = check_afisha_vilnius(
        _record("Концерты #4июня и #7июня"),
        _refinement(
            {
                "version": 1,
                "timezone": "Europe/Vilnius",
                "kind": "occurrences",
                "occurrences": [{"start": "2026-06-04T19:00", "end": None}],
            }
        ),
    )

    assert report.schedule is not None
    assert report.schedule.level == "error"
    assert "2026-06-07" in (report.schedule.message or "")


def test_afisha_occurrences_warn_about_untagged_dates() -> None:
    report = check_afisha_vilnius(
        _record("Концерт #4июня"),
        _refinement(
            {
                "version": 1,
                "timezone": "Europe/Vilnius",
                "kind": "occurrences",
                "occurrences": [
                    {"start": "2026-06-04T19:00", "end": None},
                    {"start": "2026-06-05T19:00", "end": None},
                ],
            }
        ),
    )

    assert report.schedule is not None
    assert report.schedule.level == "warning"
    assert "2026-06-05" in (report.schedule.message or "")


def test_afisha_recurrence_only_probes_tagged_dates() -> None:
    report = check_afisha_vilnius(
        _record("Встречи #4июня и #11июня"),
        _refinement(
            {
                "version": 1,
                "timezone": "Europe/Vilnius",
                "kind": "recurrence",
                "frequency": "weekly",
                "from": "2026-06-01",
                "until": "2026-06-30",
                "rules": [{"weekdays": ["thursday"], "start": "19:00", "end": None}],
            }
        ),
    )

    assert report.schedule is None


def test_afisha_recurrence_rejects_a_tag_outside_the_schedule() -> None:
    report = check_afisha_vilnius(
        _record("Встреча #4июня"),
        _refinement(
            {
                "version": 1,
                "timezone": "Europe/Vilnius",
                "kind": "recurrence",
                "frequency": "weekly",
                "from": "2026-06-05",
                "until": None,
                "rules": [{"weekdays": ["thursday"], "start": "19:00", "end": None}],
            }
        ),
    )

    assert report.schedule is not None
    assert report.schedule.level == "error"


def test_refinement_qc_dispatches_by_configured_source() -> None:
    check = build_refinement_qc(
        [
            SourceConfig(
                name="afisha-vilnius",
                type="telegram_channel",
                settings={"qc": "afisha_vilnius"},
            )
        ]
    )
    refinement = _refinement(None)

    configured = check(_record("Концерт #4июня"), refinement)
    unrelated = check(_record("Концерт #4июня", source="another"), refinement)

    assert configured.schedule is not None
    assert configured.schedule.level == "error"
    assert unrelated.schedule is None


def _record(text: str, *, source: str = "afisha-vilnius") -> Record:
    return Record(
        kind="telegram_message",
        source=source,
        text=text,
        published_at=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
        payload={"posted_at_utc": "2026-06-01T12:00:00+00:00"},
    )


def _refinement(schedule: dict | None) -> Refinement:
    return Refinement(
        record_id="record",
        content_kind="event",
        schedule=schedule,
        refiner="test",
    )
