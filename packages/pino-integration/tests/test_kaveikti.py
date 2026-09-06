from pathlib import Path

import pytest

from pino_integration.kaveikti import parse_kaveikti_records


def test_parse_kaveikti_records_from_listing_fixture() -> None:
    html = (Path(__file__).parent / "fixtures" / "kaveikti_listing.html").read_text(
        encoding="utf-8"
    )

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
    assert record.payload["end_at"] == "2026-07-18 22:00:00"
    assert record.provenance["adapter"] == "kaveikti"


def test_parse_current_listing_without_microdata() -> None:
    html = (Path(__file__).parent / "fixtures" / "kaveikti_listing_current.html").read_text()
    records = parse_kaveikti_records(
        html, source_name="kaveikti-vilnius", page_url="https://www.kaveikti.lt/renginiai/vilniuje"
    )
    assert len(records) == 1
    record = records[0]
    assert record.title == "Nemokamos Sahadža Jogos meditacijos Vilniuje"
    assert record.external_id == "407336"
    assert record.url == "https://www.kaveikti.lt/renginys/xcv"
    assert record.payload["location"] == "A. Smetonos g. 2, Vilnius"
    assert record.payload["image_url"] == "https://www.kaveikti.lt/thumbs/events/14/74/10/xcv.webp"
    assert record.payload["display_time"] == "Trečiadienį 18:30"
    assert record.payload["start_at"] is None
    assert record.payload["end_at"] is None
    assert "Time: Trečiadienį 18:30" in record.text


@pytest.mark.parametrize(
    "html, reason",
    [
        ("<html><body>Unexpected page</body></html>", "no event cards found"),
        ('<div id="block-list"></div>', "no event cards found"),
        (
            '<div class="block event-block"><div class="title">Broken card</div></div>',
            "none of 1 event cards could be parsed",
        ),
    ],
)
def test_extraction_failure_raises_with_source_and_url(html: str, reason: str) -> None:
    url = "https://www.kaveikti.lt/renginiai/vilniuje"
    with pytest.raises(ValueError, match=reason) as error:
        parse_kaveikti_records(html, source_name="kaveikti-vilnius", page_url=url)
    assert "kaveikti-vilnius" in str(error.value)
    assert url in str(error.value)
