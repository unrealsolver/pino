from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from pino_integration.telegram import TelegramChannelSource, parse_telegram_message


def test_parse_telegram_message_builds_generic_record() -> None:
    message = SimpleNamespace(
        id=123,
        message="Vilnius synth meetup\nTonight at 19:00",
        date=datetime(2026, 5, 22, 9, 30, tzinfo=timezone.utc),
        sender_id=456,
        views=99,
        forwards=3,
        post_author="Afisha Vilnius",
    )

    record = parse_telegram_message(
        message,
        source_name="afisha-vilnius",
        channel="https://t.me/afishavilnius",
    )

    assert record is not None
    assert record.kind == "telegram_message"
    assert record.source == "afisha-vilnius"
    assert record.external_id == "afishavilnius:123"
    assert record.title == "Vilnius synth meetup Tonight at 19:00"
    assert record.url == "https://t.me/afishavilnius/123"
    assert record.published_at == datetime(2026, 5, 22, 9, 30, tzinfo=timezone.utc)
    assert record.payload["message_id"] == 123
    assert record.payload["posted_at_utc"] == "2026-05-22T09:30:00+00:00"
    assert record.payload["views"] == 99
    assert "location_scopes" not in record.payload
    assert record.provenance["adapter"] == "telegram_channel"


def test_parse_telegram_message_skips_empty_text() -> None:
    assert (
        parse_telegram_message(SimpleNamespace(id=1), source_name="telegram", channel="@x") is None
    )


def test_telegram_channel_source_fetch_uses_client_factory() -> None:
    messages = [
        SimpleNamespace(
            id=1,
            text="First post",
            date=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(id=2, text="", date=datetime(2026, 5, 22, 11, 0, tzinfo=timezone.utc)),
    ]
    factory = FakeTelegramClientFactory(messages)
    source = TelegramChannelSource(
        "@afishavilnius",
        api_id=12345,
        api_hash="hash",
        session_path=".pino/test-telegram",
        name="afisha-vilnius",
        limit=10,
        location_scopes=["LT/vilnius"],
        client_factory=factory,
    )

    records = source.fetch()

    assert len(records) == 1
    assert records[0].external_id == "afishavilnius:1"
    assert records[0].payload["location_scopes"] == ["LT/vilnius"]
    assert records[0].provenance["location_scope_source"] == "channel_config"
    assert factory.calls == [(".pino/test-telegram", 12345, "hash")]
    assert factory.clients[0].iter_calls == [("@afishavilnius", 10, None)]


def test_telegram_channel_source_fetch_since_uses_message_cursor() -> None:
    messages = [
        SimpleNamespace(
            id=43, text="New post", date=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)
        ),
        SimpleNamespace(id=44, text="", date=datetime(2026, 5, 22, 11, 0, tzinfo=timezone.utc)),
    ]
    factory = FakeTelegramClientFactory(messages)
    source = TelegramChannelSource(
        "@afishavilnius",
        api_id=12345,
        api_hash="hash",
        session_path=".pino/test-telegram",
        client_factory=factory,
    )

    result = source.fetch_since("42")

    assert [record.external_id for record in result.records] == ["afishavilnius:43"]
    assert result.cursor == "44"
    assert factory.clients[0].iter_calls == [("@afishavilnius", None, 42)]


class FakeTelegramClientFactory:
    def __init__(self, messages):
        self.messages = messages
        self.calls = []
        self.clients = []

    def __call__(self, session: str, api_id: int, api_hash: str):
        self.calls.append((session, api_id, api_hash))
        client = FakeTelegramClient(self.messages)
        self.clients.append(client)
        return client


class FakeTelegramClient:
    def __init__(self, messages):
        self.messages = messages
        self.iter_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def iter_messages(self, channel: str, limit: int | None, min_id: int | None = None):
        self.iter_calls.append((channel, limit, min_id))
        for message in self.messages:
            yield message


@pytest.mark.parametrize(
    ("channel", "expected"),
    [
        ("@afishavilnius", "afishavilnius"),
        ("https://t.me/afishavilnius", "afishavilnius"),
        ("afishavilnius", "afishavilnius"),
    ],
)
def test_telegram_channel_refs(channel: str, expected: str) -> None:
    record = parse_telegram_message(
        SimpleNamespace(id=42, text="Post", date=None),
        source_name="telegram",
        channel=channel,
    )

    assert record is not None
    assert record.external_id == f"{expected}:42"
