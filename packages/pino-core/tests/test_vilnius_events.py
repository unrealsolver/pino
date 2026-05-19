from pathlib import Path

from pino_core.integrations.vilnius_events import parse_vilnius_events_records


def test_parse_vilnius_events_records_from_listing_fixture() -> None:
    html = (Path(__file__).parent / "fixtures" / "vilnius_events_listing.html").read_text(
        encoding="utf-8",
    )

    records = parse_vilnius_events_records(
        html,
        source_name="vilnius-events",
        page_url="https://www.vilnius-events.lt/en/",
    )

    assert len(records) == 1
    record = records[0]
    assert record.kind == "event"
    assert record.source == "vilnius-events"
    assert record.external_id == "draugai-draugams-x-mo-2"
    assert record.title == "Draugai draugams x MO"
    assert record.url == "https://www.vilnius-events.lt/en/event/draugai-draugams-x-mo-2/"
    assert record.payload["category"] == "Night Activities, Free Admission, Open Air, TOP Events"
    assert record.payload["categories"] == [
        "Night Activities",
        "Free Admission",
        "Open Air",
        "TOP Events",
    ]
    assert record.payload["location"] == "MO muziejus"
    assert record.payload["display_time"] == "2026-05-23 15:00"
    assert record.payload["image_url"] == "https://www.vilnius-events.lt/wp-content/uploads/2026/05/mo.jpg"
    assert record.provenance["adapter"] == "vilnius_events"
