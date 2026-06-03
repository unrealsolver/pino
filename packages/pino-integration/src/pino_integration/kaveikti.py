from __future__ import annotations

from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from pino_core.config import SourceConfig
from pino_core.models import Record
from pino_core.sources import SourceAdapter


class KaveiktiSource:
    """Fetch and parse event records from kaveikti.lt listing pages."""

    source_kind = "web"

    def __init__(self, url: str, name: str = "kaveikti") -> None:
        self.url = url
        self.name = name

    def fetch(self) -> list[Record]:
        response = httpx.get(
            self.url,
            headers={"User-Agent": "Pino/0.1 (+local personal assistant)"},
            timeout=30,
        )
        response.raise_for_status()
        return parse_kaveikti_records(response.text, source_name=self.name, page_url=self.url)


def parse_kaveikti_records(html: str, *, source_name: str, page_url: str) -> list[Record]:
    """Parse event cards from a kaveikti.lt listing page."""
    soup = BeautifulSoup(html, "html.parser")
    records: list[Record] = []
    for index, block in enumerate(soup.select(".block.event-block")):
        record = _parse_event_block(block, source_name=source_name, page_url=page_url, index=index)
        if record is not None:
            records.append(record)
    return records


def _parse_event_block(
    block: Tag,
    *,
    source_name: str,
    page_url: str,
    index: int,
) -> Record | None:
    title_el = block.select_one(".title [itemprop='name']") or block.select_one(".title a")
    link_el = block.select_one(".title a[itemprop='url']") or block.select_one(
        ".block-head a[itemprop='url']",
    )
    if title_el is None or link_el is None:
        return None

    title = _clean_text(title_el.get_text(" ", strip=True))
    href = link_el.get("href")
    url = urljoin(page_url, str(href)) if href else None
    category = _text_or_none(block.select_one(".type-label"))
    location = _text_or_none(block.select_one(".location a"))
    display_time = _display_time(block)
    start_at = _meta_content(block, "startDate")
    end_at = _meta_content(block, "endDate")
    image_url = _image_url(block, page_url)
    event_time_id = link_el.get("data-event-time-id")

    details = [title]
    if category:
        details.append(f"Category: {category}")
    if location:
        details.append(f"Location: {location}")
    if display_time:
        details.append(f"Time: {display_time}")

    return Record(
        kind="event",
        source=source_name,
        external_id=str(event_time_id) if event_time_id else None,
        title=title,
        text=". ".join(details),
        url=url,
        payload={
            "category": category,
            "location": location,
            "display_time": display_time,
            "start_at": start_at,
            "end_at": end_at,
            "image_url": image_url,
        },
        provenance={
            "adapter": "kaveikti",
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


def _meta_content(block: Tag, itemprop: str) -> str | None:
    meta = block.select_one(f"meta[itemprop='{itemprop}']")
    if meta is None:
        return None
    content = meta.get("content")
    return str(content) if content else None


def _display_time(block: Tag) -> str | None:
    date = _text_or_none(block.select_one(".date-time .time-date"))
    hour = _text_or_none(block.select_one(".date-time .time-h"))
    if date and hour:
        return f"{date} {hour}"
    return date or hour or None


def _image_url(block: Tag, page_url: str) -> str | None:
    image = block.select_one("img[itemprop='image']")
    if image is None:
        return None
    src = image.get("src")
    return urljoin(page_url, str(src)) if src else None


def build_kaveikti_source(config: SourceConfig) -> SourceAdapter:
    """Build the kaveikti source adapter from config."""
    if config.url is None:
        raise ValueError("kaveikti source requires url")
    return KaveiktiSource(config.url, name=config.name)
