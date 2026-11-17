from pathlib import Path

import pytest

from pino_integration.vilnius_events import parse_vilnius_events_records


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
    assert record.payload["location"] == "MO muziejus"
    assert record.payload["display_time"] == "2026-05-23 15:00"
    assert (
        record.payload["image_url"]
        == "https://www.vilnius-events.lt/wp-content/uploads/2026/05/mo.jpg"
    )
    assert record.provenance["adapter"] == "vilnius_events"


def test_meta_rows_preserve_localized_schedule_and_exclude_location() -> None:
    html = (Path(__file__).parent / "fixtures" / "vilnius_events_meta_rows.html").read_text(
        encoding="utf-8"
    )
    records = parse_vilnius_events_records(
        html, source_name="vilnius-events", page_url="https://www.vilnius-events.lt/en/"
    )
    assert len(records) == 3
    localized, missing_time, location_only = records
    assert localized.payload["display_time"] == "Pirmadienis, lapkričio 16, 2026 17:30–19:00"
    assert localized.payload["location"] == "Various venues"
    assert missing_time.payload["display_time"] == "Sunday, November 15, 2026"
    assert missing_time.payload["location"] == "”Nordika”"
    assert location_only.payload["display_time"] is None
    assert location_only.payload["location"] == "Cathedral Square"
    assert "Various venues" not in localized.payload["display_time"]


def test_parse_2026_listing_markup() -> None:
    html = (Path(__file__).parent / "fixtures" / "vilnius_events_listing_2026.html").read_text(
        encoding="utf-8"
    )
    records = parse_vilnius_events_records(
        html, source_name="vilnius-events", page_url="https://www.vilnius-events.lt/en/"
    )
    assert len(records) == 2
    first, second = records
    assert first.external_id == "marble-pop-swap-free-toy-swapping-for-kids"
    assert first.title == "MARBLE Pop Swap – Free Toy Swapping for Kids"
    assert first.url == (
        "https://www.vilnius-events.lt/en/event/marble-pop-swap-free-toy-swapping-for-kids/"
    )
    assert first.payload["category"] == "Free Admission, For Families"
    assert first.payload["location"] == "”Nordika”"
    assert first.payload["display_time"] == "Sunday, November 15, 2026 09:30"
    assert first.payload["image_url"] == (
        "https://www.vilnius-events.lt/wp-content/uploads/2026/11/"
        "900005203_122112649695514000_4629933037147170990_n.jpg"
    )
    assert second.external_id == "vilnius-challenge"
    assert second.payload["category"] == "For Families, Open Air"
    assert second.payload["location"] == "Various venues"
    assert second.payload["display_time"] == "Saturday, November 21, 2026"
    assert all("Christmas in Vilnius" not in record.title for record in records)


@pytest.mark.parametrize(
    "html, reason",
    [
        ("<html><body>Just a moment...</body></html>", "no event cards found"),
        (
            '<div class="ve-list-container"><div class="ve-cards-grid"></div></div>',
            "no event cards found",
        ),
        (
            '<div class="ve-list-item"><a class="oe-card" href="/event/broken"></a></div>',
            "none of 1 event cards could be parsed",
        ),
    ],
)
def test_extraction_failure_raises_with_source_and_url(html: str, reason: str) -> None:
    url = "https://www.vilnius-events.lt/en/"
    with pytest.raises(ValueError, match=reason) as error:
        parse_vilnius_events_records(html, source_name="vilnius-events", page_url=url)
    assert "vilnius-events" in str(error.value)
    assert url in str(error.value)
