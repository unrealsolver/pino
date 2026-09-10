from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest

from pino_core.config import MediaConfig
from pino_core.models import Record
from pino_core.pipeline import CheckPipeline
from pino_core.storage import SQLiteStore
from pino_integration.telegram import TelegramChannelSource, _LimitedImageBuffer


def test_telegram_album_repair_is_explicit_after_cursor_advances(tmp_path):
    messages = [
        SimpleNamespace(
            id=10, text="Album caption", photo=True, grouped_id=123, date=datetime.now(timezone.utc)
        ),
        SimpleNamespace(
            id=11, text="", photo=True, grouped_id=123, date=datetime.now(timezone.utc)
        ),
        SimpleNamespace(
            id=12, text="Plain post", photo=None, grouped_id=None, date=datetime.now(timezone.utc)
        ),
    ]
    downloads = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def iter_messages(self, channel, limit, min_id=0):
            for message in messages:
                if message.id > min_id:
                    yield message

        async def get_messages(self, channel, ids):
            if isinstance(ids, list):
                return [message for message in messages if message.id in ids]
            return next((message for message in messages if message.id == ids), None)

        async def download_media(self, message, file):
            downloads.append(message.id)
            if downloads == [10]:
                raise OSError("temporary failure")
            buffer = BytesIO()
            Image.new("RGB", (32, 48), "red" if message.id == 10 else "blue").save(buffer, "PNG")
            file.write(buffer.getvalue())

    source = TelegramChannelSource(
        "@test",
        api_id=1,
        api_hash="test",
        session_path=tmp_path / "session",
        client_factory=lambda *args: Client(),
    )
    store = SQLiteStore(tmp_path / "db.sqlite")
    pipeline = CheckPipeline(store, [source], media=MediaConfig(directory=tmp_path / "media"))
    first = pipeline.run()
    assert first.inserted == 2
    assert store.get_source_cursor(source.name) == "12"
    album = next(record for record in store.list_records() if record.payload.get("grouped_id"))
    assert len(album.images) == 1
    assert album.payload["telegram_image_ids"] == [10, 11]
    second = pipeline.run()
    assert second.fetched == 0
    assert downloads == [10, 11]
    assert len(store.get_record(album.id).images) == 1
    from pino_core.media import MediaStore

    media = MediaStore(MediaConfig(directory=tmp_path / "media"))
    for repaired in source.enrich_media([store.get_record(album.id)], media):
        store.set_record_media(repaired)
    album = store.get_record(album.id)
    assert [image.source_url for image in album.images] == [
        "https://t.me/test/10",
        "https://t.me/test/11",
    ]
    pipeline.run()
    assert downloads == [10, 11, 10]
    (tmp_path / "media" / album.images[0].path).unlink()
    pipeline.run()
    assert downloads == [10, 11, 10]
    for repaired in source.enrich_media([store.get_record(album.id)], media):
        store.set_record_media(repaired)
    assert downloads == [10, 11, 10, 10]


@pytest.mark.parametrize("as_document", [False, True])
def test_backfills_legacy_record_and_retains_photo_only_messages(tmp_path, as_document):
    image = SimpleNamespace(
        id=1,
        text="",
        photo=None if as_document else True,
        grouped_id=None,
        date=None,
        document=SimpleNamespace(mime_type="image/png") if as_document else None,
    )

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def iter_messages(self, channel, limit, min_id=0):
            if min_id == 0:
                yield image

        async def get_messages(self, channel, ids):
            return image

        async def download_media(self, message, file):
            Image.new("RGB", (5, 5)).save(file, "PNG")

    source = TelegramChannelSource(
        "@test",
        api_id=1,
        api_hash="x",
        session_path=tmp_path / "session",
        client_factory=lambda *args: Client(),
    )
    store = SQLiteStore(tmp_path / "db.sqlite")
    pipeline = CheckPipeline(store, [source], media=MediaConfig(directory=tmp_path / "media"))
    first = pipeline.run()
    assert first.records[0].text == "Telegram photo"
    assert first.records[0].images
    legacy = store.add_record(
        Record(
            kind="telegram_message",
            source=source.name,
            text="old",
            external_id="old",
            payload={"message_id": 1},
        )
    ).record
    pipeline.run()
    assert not store.get_record(legacy.id).images
    from pino_core.media import MediaStore

    for repaired in source.enrich_media(
        [legacy], MediaStore(MediaConfig(directory=tmp_path / "media"))
    ):
        store.set_record_media(repaired)
    assert store.get_record(legacy.id).images


def test_telegram_download_is_bounded(monkeypatch):
    monkeypatch.setattr("pino_integration.telegram.MAX_BYTES", 4)
    buffer = _LimitedImageBuffer()
    buffer.write(b"1234")
    with pytest.raises(ValueError, match="size limit"):
        buffer.write(b"5")


def test_media_session_failure_does_not_lose_text_or_cursor(tmp_path):
    sessions = []

    class Client:
        async def __aenter__(self):
            sessions.append(self)
            if len(sessions) > 1:
                raise ConnectionError("offline")
            return self

        async def __aexit__(self, *args):
            pass

        async def iter_messages(self, channel, limit, min_id=0):
            yield SimpleNamespace(id=1, text="keep me", photo=True, date=None)

    source = TelegramChannelSource(
        "@test",
        api_id=1,
        api_hash="x",
        session_path=tmp_path / "session",
        client_factory=lambda *args: Client(),
    )
    store = SQLiteStore(tmp_path / "db.sqlite")
    result = CheckPipeline(store, [source], media=MediaConfig(directory=tmp_path / "media")).run()
    assert result.inserted == 1
    assert result.sources[0].error is None
    assert store.list_records()[0].text == "keep me"
    assert store.get_source_cursor(source.name) == "1"
