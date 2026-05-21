from __future__ import annotations

from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from pino_core.config import SourceConfig
from pino_core.dates import DEFAULT_SOURCE_TIMEZONE, parse_source_date_range, to_utc, utc_iso
from pino_core.models import Record
from pino_core.sources import SourceAdapter


class VilniusEventsSource:
    """Fetch and parse event records from vilnius-events.lt listing pages."""

    def __init__(self, url: str, name: str = "vilnius-events") -> None:
        self.url = url
        self.name = name

    def fetch(self) -> list[Record]:
        response = httpx.get(
            self.url,
            headers={"User-Agent": "Pino/0.1 (+local personal assistant)"},
            timeout=30,
        )
        response.raise_for_status()
        return parse_vilnius_events_records(response.text, source_name=self.name, page_url=self.url)


def parse_vilnius_events_records(html: str, *, source_name: str, page_url: str) -> list[Record]:
    """Parse event cards from a vilnius-events.lt listing page."""
    soup = BeautifulSoup(html, "html.parser")
    records: list[Record] = []
    for index, card in enumerate(soup.select(".o-card.ve")):
        record = _parse_event_card(card, source_name=source_name, page_url=page_url, index=index)
        if record is not None:
            records.append(record)
    return records


def _parse_event_card(
    card: Tag,
    *,
    source_name: str,
    page_url: str,
    index: int,
) -> Record | None:
    title = _text_or_none(card.select_one(".m-card__description-title"))
    link = card.select_one("a.u-text-decoration-none[href]") or card.select_one("a[href]")
    if title is None or link is None:
        return None

    href = link.get("href")
    url = urljoin(page_url, str(href)) if href else None
    display_time = _text_or_none(card.select_one(".m-card__description-date"))
    relevant_from_local, relevant_to_local = parse_source_date_range(display_time)
    relevant_from_utc = to_utc(relevant_from_local)
    relevant_to_utc = to_utc(relevant_to_local)
    location = _text_or_none(card.select_one("p.m-card__location a")) or _text_or_none(
        card.select_one("p.m-card__location"),
    )
    category = _text_or_none(card.select_one(".m-card__category"))
    categories = _split_categories(category)
    image_url = _image_url(card, page_url)

    details = [title]
    if category:
        details.append(f"Categories: {category}")
    if location:
        details.append(f"Location: {location}")
    if display_time:
        details.append(f"Time: {display_time}")

    return Record(
        kind="event",
        source=source_name,
        external_id=_external_id(url),
        title=title,
        text=". ".join(details),
        url=url,
        relevant_from=relevant_from_utc,
        relevant_to=relevant_to_utc,
        payload={
            "category": category,
            "categories": categories,
            "location": location,
            "display_time": display_time,
            "start_at_utc": utc_iso(relevant_from_local),
            "end_at_utc": utc_iso(relevant_to_local),
            "timezone": DEFAULT_SOURCE_TIMEZONE,
            "image_url": image_url,
        },
        provenance={
            "adapter": "vilnius_events",
            "page_url": page_url,
            "index": index,
        },
    )


def _text_or_none(element: Tag | None) -> str | None:
    if element is None:
        return None
    text = _clean_text(element.get_text(" ", strip=True))
    return text or None


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _split_categories(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _image_url(card: Tag, page_url: str) -> str | None:
    image = card.select_one("img.m-card__image")
    if image is None:
        return None
    src = image.get("data-wpfc-original-src") or image.get("src")
    return urljoin(page_url, str(src)) if src else None


def _external_id(url: str | None) -> str | None:
    if url is None:
        return None
    path = urlsplit(url).path.strip("/")
    if not path:
        return None
    return path.split("/")[-1] or None


def build_vilnius_events_source(config: SourceConfig) -> SourceAdapter:
    """Build the vilnius-events.lt source adapter from config."""
    if config.url is None:
        raise ValueError("vilnius_events source requires url")
    return VilniusEventsSource(config.url, name=config.name)
