from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from ipaddress import ip_address
from typing import Any, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from pino_core.dates import DEFAULT_SOURCE_TIMEZONE
from pino_core.models import MemoryEntry, Record, Refinement, utc_now
from pino_core.pipeline import CheckPipeline, DigestService
from pino_core.sources import SourceAdapter
from pino_core.storage import DatabaseStore, RecordRefinementStatus


DEFAULT_WEB_OPEN_MAX_CHARS = 5000
WEB_OPEN_USER_AGENT = "Pino/0.1 (+local personal assistant)"


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class WebPage:
    url: str
    status_code: int
    content_type: str
    text: str


WebFetcher = Callable[[str], WebPage]


def build_tools(
    store: DatabaseStore,
    sources: list[SourceAdapter],
    *,
    web_fetcher: WebFetcher | None = None,
) -> dict[str, Tool]:
    def memory_add(arguments: dict[str, Any]) -> str:
        content = str(arguments.get("content", "")).strip()
        if not content:
            return "memory.add failed: content is required."
        tags = arguments.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        memory = MemoryEntry(content=content, tags=[str(tag) for tag in tags])
        store.add_memory(memory)
        return f"Added active memory: {memory.content}"

    def memory_list(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 20))
        memories = store.list_memory(limit=limit)
        if not memories:
            return "No active memory entries."
        return "\n".join(f"- {memory.content}" for memory in memories)

    def records_list(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 10))
        rows = store.list_records_with_refinement_status(limit=limit)
        if not rows:
            return "No records captured yet."
        return "\n".join(_format_record_with_status(row) for row in rows)

    def records_relevant(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 20))
        window_days = int(arguments.get("days", arguments.get("window_days", 14)))
        min_score = float(arguments.get("min_score", 0.0))
        categories = _coerce_categories(arguments.get("categories", []))
        query = str(arguments.get("query", arguments.get("q", ""))).strip()
        scan_limit = _coerce_int(arguments.get("scan_limit"), default=1000)
        scan_limit = max(limit, min(scan_limit, 5000))
        window = _resolve_relevant_window(arguments, default_days=window_days)
        if isinstance(window, str):
            return f"records.relevant failed: {window}"
        window_start, window_end, window_label = window
        records = store.list_relevant_refinements(
            window_start=window_start,
            window_end=window_end,
            limit=scan_limit,
            scan_limit=scan_limit,
        )
        filtered = [
            (record, refinement)
            for record, refinement in records
            if _matches_relevant_filters(refinement, min_score=min_score, categories=categories)
            and _matches_text_query(record, refinement, query)
        ]
        if query or categories or min_score > 0:
            filtered.sort(
                key=lambda item: (
                    -_text_query_score(item[0], item[1], query),
                    -_relevant_filter_score(
                        item[1],
                        min_score=min_score,
                        categories=categories,
                    ),
                    item[1].relevant_from or datetime.max,
                ),
            )
        filtered = filtered[:limit]
        if not filtered:
            return f"No relevant records found for {window_label}."
        lines = [f"Relevant records for {window_label}:"]
        lines.extend(
            _format_relevant_record(record, refinement) for record, refinement in filtered
        )
        return "\n".join(lines)

    def digest_create(arguments: dict[str, Any]) -> str:
        limit = int(arguments.get("limit", 20))
        window_days = int(arguments.get("days", arguments.get("window_days", 14)))
        return DigestService(store).create_digest(limit=limit, window_days=window_days).body

    def sources_check(arguments: dict[str, Any]) -> str:
        result = CheckPipeline(store=store, sources=sources).run()
        return (
            f"Fetched {result.fetched}; inserted {result.inserted}; "
            f"duplicates {result.duplicates}. "
            f"Refinement pending: {result.pending_refinement_total} total, "
            f"{result.pending_refinement_new} new."
        )

    def web_open(arguments: dict[str, Any]) -> str:
        url = str(arguments.get("url", "")).strip()
        if not url:
            return "web.open failed: url is required."
        limit = _coerce_int(arguments.get("max_chars"), default=DEFAULT_WEB_OPEN_MAX_CHARS)
        limit = max(500, min(limit, DEFAULT_WEB_OPEN_MAX_CHARS))
        error = _validate_public_http_url(url)
        if error is not None:
            return f"web.open failed: {error}"
        try:
            page = (web_fetcher or _fetch_web_page)(url)
        except httpx.HTTPError as exc:
            return f"web.open failed: request error: {exc}"
        except UnicodeError as exc:
            return f"web.open failed: could not decode response: {exc}"

        extracted = _extract_page_text(page.text)
        body = _truncate_text(extracted.body, limit)
        lines = [
            f"URL: {page.url}",
            f"Status: {page.status_code}",
            f"Content-Type: {page.content_type or 'unknown'}",
        ]
        if extracted.title:
            lines.append(f"Title: {extracted.title}")
        if extracted.description:
            lines.append(f"Description: {extracted.description}")
        if body:
            lines.append(f"Text:\n{body}")
        else:
            lines.append("Text: No readable page text found.")
        return "\n".join(lines)

    tools = [
        Tool(
            "memory.add",
            'Add an active memory entry. Arguments JSON example: {"content": "text", "tags": ["tag"]}.',
            memory_add,
        ),
        Tool(
            "memory.list",
            'List active memory entries. Arguments JSON example: {"limit": 20}.',
            memory_list,
        ),
        Tool(
            "records.relevant",
            'Preferred for event recommendations and upcoming/current plans. Returns refinement-backed records with taxonomy scores, local time, location, URL, and summary. For calendar-specific queries, pass local inclusive ISO dates in "date_from" and "date_to"; use the same date for a single day such as next Friday. For follow-up questions about a named event, pass "query". Arguments JSON example: {"limit": 20, "date_from": "2026-06-05", "date_to": "2026-06-05", "min_score": 0.3, "categories": ["metal_music"], "query": "Morning coffee tour", "scan_limit": 1000}.',
            records_relevant,
        ),
        Tool(
            "records.list",
            'Raw recent records for inspection/debug only. Arguments JSON example: {"limit": 50}.',
            records_list,
        ),
        Tool(
            "digest.create",
            'Create a digest from relevant current/upcoming records. Arguments JSON example: {"limit": 20, "days": 14}.',
            digest_create,
        ),
        Tool(
            "sources.check",
            "Fetch configured sources and store records. Arguments JSON example: {}.",
            sources_check,
        ),
        Tool(
            "web.open",
            'Open one public http(s) URL and return compact readable page text for event/detail checks. Arguments JSON example: {"url": "https://example.com/event", "max_chars": 3000}.',
            web_open,
        ),
    ]
    return {tool.name: tool for tool in tools}


def describe_tools(tools: dict[str, Tool]) -> str:
    return "\n".join(f"- {tool.name}: {tool.description}" for tool in tools.values())


def _coerce_categories(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _coerce_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_relevant_window(
    arguments: dict[str, Any],
    *,
    default_days: int,
) -> tuple[datetime, datetime, str] | str:
    local_timezone = ZoneInfo(DEFAULT_SOURCE_TIMEZONE)
    date_from = _parse_iso_date(arguments.get("date_from") or arguments.get("start_date"))
    date_to = _parse_iso_date(arguments.get("date_to") or arguments.get("end_date"))
    if date_from is False or date_to is False:
        return "date_from and date_to must be ISO dates like 2026-06-05."
    if date_from is not None or date_to is not None:
        if date_from is None or date_to is None:
            return "date ranges require both date_from and date_to."
        if date_to < date_from:
            return "date_to must be on or after date_from."
        start = datetime.combine(date_from, time.min, tzinfo=local_timezone).astimezone(
            ZoneInfo("UTC")
        )
        end = datetime.combine(date_to, time.max, tzinfo=local_timezone).astimezone(
            ZoneInfo("UTC")
        )
        if date_from == date_to:
            label = f"{date_from:%Y-%m-%d} ({DEFAULT_SOURCE_TIMEZONE})"
        else:
            label = f"{date_from:%Y-%m-%d} to {date_to:%Y-%m-%d} ({DEFAULT_SOURCE_TIMEZONE})"
        return start, end, label

    start = utc_now()
    end = start + timedelta(days=default_days)
    local_start = start.astimezone(local_timezone)
    local_end = end.astimezone(local_timezone)
    label = (
        f"the next {default_days} day(s), "
        f"{local_start:%Y-%m-%d %H:%M} to {local_end:%Y-%m-%d %H:%M} "
        f"({DEFAULT_SOURCE_TIMEZONE})"
    )
    return start, end, label


def _parse_iso_date(value: object) -> date | None | bool:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return False


def _matches_relevant_filters(
    refinement: Refinement,
    *,
    min_score: float,
    categories: list[str],
) -> bool:
    if categories:
        return any(
            refinement.category_scores.get(category, -1.0) >= min_score for category in categories
        )
    if min_score > 0:
        return any(score >= min_score for score in refinement.category_scores.values())
    return True


def _matches_text_query(record: Record, refinement: Refinement, query: str) -> bool:
    if not query:
        return True
    terms = [term for term in query.lower().split() if term]
    if not terms:
        return True
    haystack = _record_search_text(record, refinement)
    return all(term in haystack for term in terms)


def _text_query_score(record: Record, refinement: Refinement, query: str) -> float:
    if not query:
        return 0.0
    normalized_query = query.lower().strip()
    if not normalized_query:
        return 0.0
    title = (record.title or "").lower()
    summary = (refinement.summary or "").lower()
    location = (refinement.location or "").lower()
    score = 0.0
    if normalized_query in title:
        score += 3.0
    if normalized_query in summary:
        score += 2.0
    if normalized_query in location:
        score += 1.0
    score += sum(1.0 for term in normalized_query.split() if term in title)
    return score


def _record_search_text(record: Record, refinement: Refinement) -> str:
    return " ".join(
        value.lower()
        for value in [
            record.title or "",
            record.text,
            record.url or "",
            refinement.summary or "",
            refinement.location or "",
        ]
        if value
    )


def _relevant_filter_score(
    refinement: Refinement,
    *,
    min_score: float,
    categories: list[str],
) -> float:
    if categories:
        return max(
            (refinement.category_scores.get(category, 0.0) for category in categories),
            default=0.0,
        )
    if min_score > 0:
        return max(refinement.category_scores.values(), default=0.0)
    return 0.0


def _format_relevant_record(record: Record, refinement: Refinement) -> str:
    label = record.title or record.kind
    source = f" ({record.source})" if record.source else ""
    category_text = _format_category_scores(refinement)
    relevance_text = _format_relevance_window(refinement)
    location_text = _format_location(refinement)
    url_text = f" [url: {record.url}]" if record.url else ""
    summary = refinement.summary or record.text
    return f"- {label}{source}{category_text}{relevance_text}{location_text}{url_text}: {summary}"


def _format_category_scores(refinement: Refinement) -> str:
    scores = ", ".join(
        f"{name}={score:.2f}"
        for name, score in sorted(
            refinement.category_scores.items(), key=lambda item: item[1], reverse=True
        )
        if score > 0
    )
    return f" [{scores}]" if scores else ""


def _format_record_with_status(row: RecordRefinementStatus) -> str:
    record = row.record
    label = record.title or record.kind
    source = f" ({record.source})" if record.source else ""
    status = f" [refined:{len(row.refinements)}]" if row.refinements else " [unrefined]"
    return f"- {label}{source}{status}: {record.text}"


def _format_relevance_window(refinement: Refinement) -> str:
    start = _local_datetime(refinement.relevant_from)
    end = _local_datetime(refinement.relevant_to)
    if start is None and end is None:
        return ""
    if start is not None and end is not None:
        if start == end:
            return f" [{start:%Y-%m-%d %H:%M}]"
        if start.date() == end.date():
            return f" [{start:%Y-%m-%d %H:%M}-{end:%H:%M}]"
        return f" [{start:%Y-%m-%d %H:%M} - {end:%Y-%m-%d %H:%M}]"
    if start is not None:
        return f" [from {start:%Y-%m-%d %H:%M}]"
    return f" [until {end:%Y-%m-%d %H:%M}]"


def _format_location(refinement: Refinement) -> str:
    if not refinement.location or not refinement.location.strip():
        return ""
    return f" @ {refinement.location.strip()}"


def _local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(ZoneInfo(DEFAULT_SOURCE_TIMEZONE))


def _validate_public_http_url(url: str) -> str | None:
    split = urlsplit(url)
    if split.scheme not in {"http", "https"}:
        return "only http and https URLs are supported."
    if not split.hostname:
        return "URL must include a hostname."
    host = split.hostname.lower()
    if host in {"localhost"} or host.endswith(".localhost") or host.endswith(".local"):
        return "local hostnames are not allowed."
    try:
        parsed_ip = ip_address(host)
    except ValueError:
        return None
    if parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local:
        return "private, loopback, and link-local addresses are not allowed."
    return None


def _fetch_web_page(url: str) -> WebPage:
    response = httpx.get(
        url,
        headers={"User-Agent": WEB_OPEN_USER_AGENT},
        follow_redirects=True,
        timeout=20,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if not _is_text_content_type(content_type):
        raise httpx.HTTPError(f"unsupported content type: {content_type or 'unknown'}")
    return WebPage(
        url=str(response.url),
        status_code=response.status_code,
        content_type=content_type,
        text=response.text,
    )


def _is_text_content_type(content_type: str) -> bool:
    normalized = content_type.lower()
    return any(
        item in normalized
        for item in (
            "text/html",
            "text/plain",
            "application/xhtml+xml",
            "application/xml",
            "text/xml",
        )
    )


@dataclass(frozen=True)
class ExtractedPageText:
    title: str
    description: str
    body: str


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description = ""
        self.body_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            values = {name.lower(): value or "" for name, value in attrs}
            if values.get("name", "").lower() == "description" and values.get("content"):
                self.description = values["content"]
            return
        if tag in {
            "p",
            "div",
            "section",
            "article",
            "header",
            "footer",
            "li",
            "br",
            "tr",
            "h1",
            "h2",
            "h3",
        }:
            self.body_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self.body_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self.body_parts.append(text)
            self.body_parts.append(" ")


def _extract_page_text(text: str) -> ExtractedPageText:
    stripped = text.lstrip()
    if not stripped.startswith("<"):
        body = _normalize_extracted_text(text)
        return ExtractedPageText(title="", description="", body=body)

    parser = _ReadableHTMLParser()
    parser.feed(text)
    return ExtractedPageText(
        title=_normalize_extracted_text(" ".join(parser.title_parts)),
        description=_normalize_extracted_text(parser.description),
        body=_normalize_extracted_text("".join(parser.body_parts)),
    )


def _normalize_extracted_text(value: str) -> str:
    lines = []
    for line in value.splitlines():
        line = " ".join(line.split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}\n[truncated to {limit} characters]"
