from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from telethon import TelegramClient

from pino_core.config import SourceConfig
from pino_core.models import Record
from pino_core.sources import CursorFetchResult, SourceAdapter


class TelegramClientFactory(Protocol):
    def __call__(self, session: str, api_id: int, api_hash: str) -> Any: ...


class TelegramChannelSource:
    """Fetch recent public-channel messages through Telethon."""

    source_kind = "tg"

    def __init__(
        self,
        channel: str,
        *,
        api_id: int,
        api_hash: str,
        session_path: Path | str,
        name: str = "telegram-channel",
        limit: int = 50,
        location_scopes: list[str] | None = None,
        client_factory: TelegramClientFactory = TelegramClient,
    ) -> None:
        self.channel = channel
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = Path(session_path)
        self.name = name
        self.limit = limit
        self.location_scopes = location_scopes or []
        self._client_factory = client_factory

    def fetch(self) -> list[Record]:
        return self.fetch_since(None).records

    def fetch_since(self, cursor: str | None) -> CursorFetchResult:
        return asyncio.run(self._fetch_since(cursor))

    async def _fetch_since(self, cursor: str | None) -> CursorFetchResult:
        records: list[Record] = []
        previous_message_id = _message_id_cursor(cursor)
        next_message_id = None
        async with self._client_factory(
            str(self.session_path),
            self.api_id,
            self.api_hash,
        ) as client:
            request = {"limit": self.limit}
            if previous_message_id is not None:
                request = {"limit": None, "min_id": previous_message_id}
            async for message in client.iter_messages(self.channel, **request):
                message_id = getattr(message, "id", None)
                if isinstance(message_id, int):
                    next_message_id = max(next_message_id or message_id, message_id)
                record = parse_telegram_message(
                    message,
                    source_name=self.name,
                    channel=self.channel,
                    location_scopes=self.location_scopes,
                )
                if record is not None:
                    records.append(record)
        return CursorFetchResult(
            records=records,
            cursor=str(next_message_id) if next_message_id is not None else None,
        )


def parse_telegram_message(
    message: Any,
    *,
    source_name: str,
    channel: str,
    location_scopes: list[str] | None = None,
) -> Record | None:
    text = _message_text(message)
    if not text:
        return None

    message_id = getattr(message, "id", None)
    posted_at = _to_utc(getattr(message, "date", None))
    channel_ref = _channel_ref(channel)
    normalized_scopes = location_scopes or []
    payload = {
        "channel": channel,
        "message_id": message_id,
        "posted_at_utc": posted_at.isoformat() if posted_at is not None else None,
        "sender_id": getattr(message, "sender_id", None),
        "views": getattr(message, "views", None),
        "forwards": getattr(message, "forwards", None),
        "post_author": getattr(message, "post_author", None),
    }
    provenance = {
        "adapter": "telegram_channel",
        "channel": channel,
    }
    if normalized_scopes:
        payload["location_scopes"] = normalized_scopes
        provenance["location_scope_source"] = "channel_config"

    return Record(
        kind="telegram_message",
        source=source_name,
        external_id=_external_id(channel_ref, message_id),
        title=_title(text, message_id),
        text=text,
        url=_message_url(channel_ref, message_id),
        payload=payload,
        provenance=provenance,
    )


def build_telegram_channel_source(config: SourceConfig) -> SourceAdapter:
    channel = _string_setting(config, "channel") or config.url
    if channel is None:
        raise ValueError("telegram_channel source requires url or settings.channel")

    return TelegramChannelSource(
        channel,
        api_id=_api_id(config),
        api_hash=_api_hash(config),
        session_path=_string_setting(config, "session_path") or ".pino/telegram",
        name=config.name,
        limit=_int_setting(config, "limit", default=50),
        location_scopes=_string_list_setting(config, "location_scopes"),
    )


def _message_text(message: Any) -> str:
    value = getattr(message, "message", None) or getattr(message, "text", None) or ""
    return " ".join(str(value).split())


def _title(text: str, message_id: Any) -> str:
    first_line = text.splitlines()[0].strip() if "\n" in text else text
    if not first_line:
        return f"Telegram message {message_id}"
    return first_line[:100]


def _to_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _channel_ref(channel: str) -> str:
    text = channel.strip()
    if text.startswith("@"):
        return text[1:]

    split = urlsplit(text)
    if split.netloc in {"t.me", "telegram.me"}:
        return split.path.strip("/").split("/", maxsplit=1)[0]

    return text


def _external_id(channel_ref: str, message_id: Any) -> str | None:
    if message_id is None:
        return None
    return f"{channel_ref}:{message_id}"


def _message_url(channel_ref: str, message_id: Any) -> str | None:
    if message_id is None or not channel_ref or channel_ref.startswith("+"):
        return None
    return f"https://t.me/{channel_ref}/{message_id}"


def _message_id_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    try:
        message_id = int(cursor)
    except ValueError as exc:
        raise ValueError(f"telegram_channel cursor must be an integer: {cursor!r}") from exc
    if message_id < 1:
        raise ValueError("telegram_channel cursor must be at least 1")
    return message_id


def _api_id(config: SourceConfig) -> int:
    value = config.settings.get("api_id")
    if value is None:
        raise ValueError("telegram_channel source requires settings.api_id")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("telegram_channel settings.api_id must be an integer") from exc


def _api_hash(config: SourceConfig) -> str:
    value = config.settings.get("api_hash")
    if value is None:
        raise ValueError("telegram_channel source requires settings.api_hash")
    return str(value)


def _string_setting(config: SourceConfig, key: str) -> str | None:
    value = config.settings.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list_setting(config: SourceConfig, key: str) -> list[str]:
    value = config.settings.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"telegram_channel settings.{key} must be a list")
    return [str(item).strip() for item in value if str(item).strip()]


def _int_setting(config: SourceConfig, key: str, *, default: int) -> int:
    value = config.settings.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"telegram_channel settings.{key} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"telegram_channel settings.{key} must be at least 1")
    return parsed
