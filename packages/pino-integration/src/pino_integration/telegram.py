from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from telethon import TelegramClient

from pino_core.config import SourceConfig
from pino_core.models import Record
from pino_core.sources import SourceAdapter


class TelegramClientFactory(Protocol):
    def __call__(self, session: str, api_id: int, api_hash: str) -> Any: ...


class TelegramChannelSource:
    """Fetch recent public-channel messages through Telethon."""

    def __init__(
        self,
        channel: str,
        *,
        api_id: int,
        api_hash: str,
        session_path: Path | str,
        name: str = "telegram-channel",
        limit: int = 50,
        client_factory: TelegramClientFactory = TelegramClient,
    ) -> None:
        self.channel = channel
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = Path(session_path)
        self.name = name
        self.limit = limit
        self._client_factory = client_factory

    def fetch(self) -> list[Record]:
        return asyncio.run(self._fetch())

    async def _fetch(self) -> list[Record]:
        records: list[Record] = []
        async with self._client_factory(
            str(self.session_path),
            self.api_id,
            self.api_hash,
        ) as client:
            async for message in client.iter_messages(self.channel, limit=self.limit):
                record = parse_telegram_message(
                    message,
                    source_name=self.name,
                    channel=self.channel,
                )
                if record is not None:
                    records.append(record)
        return records


def parse_telegram_message(message: Any, *, source_name: str, channel: str) -> Record | None:
    text = _message_text(message)
    if not text:
        return None

    message_id = getattr(message, "id", None)
    posted_at = _to_utc(getattr(message, "date", None))
    channel_ref = _channel_ref(channel)

    return Record(
        kind="telegram_message",
        source=source_name,
        external_id=_external_id(channel_ref, message_id),
        title=_title(text, message_id),
        text=text,
        url=_message_url(channel_ref, message_id),
        relevant_from=posted_at,
        relevant_to=posted_at,
        payload={
            "channel": channel,
            "message_id": message_id,
            "posted_at_utc": posted_at.isoformat() if posted_at is not None else None,
            "sender_id": getattr(message, "sender_id", None),
            "views": getattr(message, "views", None),
            "forwards": getattr(message, "forwards", None),
            "post_author": getattr(message, "post_author", None),
        },
        provenance={
            "adapter": "telegram_channel",
            "channel": channel,
        },
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


def _api_id(config: SourceConfig) -> int:
    value = _setting_or_env(config, key="api_id", env_key="api_id_env", default_env="TELEGRAM_API_ID")
    if value is None:
        raise ValueError("telegram_channel source requires settings.api_id or TELEGRAM_API_ID")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("telegram_channel settings.api_id must be an integer") from exc


def _api_hash(config: SourceConfig) -> str:
    value = _setting_or_env(
        config,
        key="api_hash",
        env_key="api_hash_env",
        default_env="TELEGRAM_API_HASH",
    )
    if value is None:
        value = _file_setting(config, "api_hash_file")
    if value is None:
        raise ValueError("telegram_channel source requires settings.api_hash or TELEGRAM_API_HASH")
    return str(value)


def _setting_or_env(
    config: SourceConfig,
    *,
    key: str,
    env_key: str,
    default_env: str,
) -> Any:
    value = config.settings.get(key)
    if value is not None:
        return value

    env_name = _string_setting(config, env_key) or default_env
    return os.environ.get(env_name)


def _file_setting(config: SourceConfig, key: str) -> str | None:
    value = _string_setting(config, key)
    if value is None:
        return None
    text = Path(value).read_text(encoding="utf-8").strip()
    return text or None


def _string_setting(config: SourceConfig, key: str) -> str | None:
    value = config.settings.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_setting(config: SourceConfig, key: str, *, default: int) -> int:
    value = config.settings.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"telegram_channel settings.{key} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"telegram_channel settings.{key} must be at least 1")
    return parsed
