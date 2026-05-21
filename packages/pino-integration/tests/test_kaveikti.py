from pathlib import Path

from pino_integration.kaveikti import parse_kaveikti_records


def test_parse_kaveikti_records_from_listing_fixture() -> None:
    html = (Path(__file__).parent / "fixtures" / "kaveikti_listing.html").read_text(encoding="utf-8")

    records = parse_kaveikti_records(
        html,
        source_name="kaveikti-vilnius",
        page_url="https://www.kaveikti.lt/renginiai/vilniuje",
    )

    assert len(records) == 1
    record = records[0]
    assert record.kind == "event"
    assert record.source == "kaveikti-vilnius"
    assert record.external_id == "400811"
    assert record.title == "Gravity Beach Festival - Vilnius 2026"
    assert record.url == "https://www.kaveikti.lt/renginys/gravity-beach-festival-vilnius-2026"
    assert record.payload["category"] == "Festivaliai"
    assert record.payload["display_time"] == "Liepos 18 15:00"
    assert record.payload["start_at"] == "2026-07-18 15:00:00"
    assert record.payload["start_at_utc"] == "2026-07-18T12:00:00+00:00"
    assert record.payload["end_at_utc"] == "2026-07-18T19:00:00+00:00"
    assert record.payload["timezone"] == "Europe/Vilnius"
    assert record.relevant_from is not None
    assert record.relevant_from.isoformat() == "2026-07-18T12:00:00+00:00"
    assert record.relevant_to is not None
    assert record.relevant_to.isoformat() == "2026-07-18T19:00:00+00:00"
    assert record.provenance["adapter"] == "kaveikti"
