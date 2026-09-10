from io import BytesIO
import socket

import httpx
import pytest
from PIL import Image

from pino_core.config import MediaConfig
from pino_core.media import MediaStore, download_image
from pino_core.models import Record
from pino_core.pipeline import CheckPipeline
from pino_core.storage import SQLiteStore


def picture(size=(2400, 1200)):
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, "PNG")
    return output.getvalue()


def test_normalizes_deduplicates_and_does_not_upscale(tmp_path):
    media = MediaStore(MediaConfig(directory=tmp_path))
    first = media.save(picture(), source_url="https://example.com/one")
    second = media.save(picture(), source_url="https://example.com/two")
    assert first.path == second.path
    assert len(list(tmp_path.iterdir())) == 1
    with Image.open(tmp_path / first.path) as cover:
        assert cover.format == "WEBP"
        assert cover.size == (1200, 600)
    small = media.save(picture((30, 60)), source_url="https://example.com/small")
    with Image.open(tmp_path / small.path) as cover:
        assert cover.size == (30, 60)


def test_image_failure_then_retry_then_reuse(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "db.sqlite")

    class Source:
        name = "test"

        def fetch(self):
            return [
                Record(
                    kind="event",
                    source=self.name,
                    text="event",
                    payload={"image_url": "https://example.com/cover"},
                )
            ]

    pipeline = CheckPipeline(store, [Source()], media=MediaConfig(directory=tmp_path / "media"))
    calls = []

    def download(url):
        calls.append(url)
        if len(calls) == 1:
            raise ValueError("broken image")
        return picture()

    monkeypatch.setattr("pino_core.media.download_image", download)
    assert pipeline.run().inserted == 1
    assert store.list_records()[0].images == []
    assert pipeline.run().duplicates == 1
    assert len(store.list_records()[0].images) == 1
    pipeline.run()
    assert len(calls) == 2


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://user:pass@example.com/a", "http://127.0.0.1/a"]
)
def test_rejects_nonpublic_or_credentialed_urls(url):
    with pytest.raises(ValueError):
        download_image(url)


def test_pins_public_dns_and_revalidates_redirects(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1" if host == "internal.test" else "93.184.216.34", 443),
            )
        ],
    )
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(302, headers={"Location": "http://internal.test/cover"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("pino_core.media.httpx.Client", lambda **kwargs: client)
    with pytest.raises(ValueError, match="non-public"):
        download_image("https://example.com/cover")
    assert len(requests) == 1


def test_decode_limits_and_invalid_bytes(tmp_path, monkeypatch):
    media = MediaStore(MediaConfig(directory=tmp_path))
    with pytest.raises(Exception):
        media.save(b"not an image", source_url="https://example.com/a")
    monkeypatch.setattr("pino_core.media.MAX_PIXELS", 10)
    with pytest.raises(ValueError, match="pixel limit"):
        media.save(picture((4, 4)), source_url="https://example.com/a")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("declared", [True, False])
def test_download_size_limit_with_and_without_content_length(monkeypatch, declared):
    monkeypatch.setattr("pino_core.media.MAX_BYTES", 4)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                stream=httpx.ByteStream(b"12345"),
                headers={"content-length": "5"} if declared else {},
            )
        )
    )
    monkeypatch.setattr("pino_core.media.httpx.Client", lambda **kwargs: client)
    with pytest.raises(ValueError, match="size limit"):
        download_image("https://example.com/cover")


@pytest.mark.parametrize(
    "prefix",
    [
        "javascript:alert(1)",
        "//example.com",
        "/",
        "/media?x=1",
        "https://user:password@example.com",
    ],
)
def test_invalid_public_prefix(prefix):
    with pytest.raises(ValueError):
        MediaConfig(public_url=prefix)
