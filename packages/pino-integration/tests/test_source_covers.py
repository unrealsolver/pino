from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from pino_core.config import MediaConfig
from pino_core.pipeline import CheckPipeline
from pino_core.sources import StaticYamlSource
from pino_core.storage import SQLiteStore
from pino_integration.kaveikti import KaveiktiSource
from pino_integration.vilnius_events import VilniusEventsSource


@pytest.mark.parametrize("source_type", ["kaveikti", "vilnius_events", "static_yaml"])
def test_each_url_source_caches_and_persists_cover(tmp_path, monkeypatch, source_type):
    if source_type == "static_yaml":
        path = tmp_path / "records.yaml"
        path.write_text(
            "records:\n  - text: event\n    payload:\n      image_urls: [https://example.com/one, https://example.com/two]\n"
        )
        source = StaticYamlSource(path)
    else:
        fixture = (
            "kaveikti_listing_current.html"
            if source_type == "kaveikti"
            else "vilnius_events_listing.html"
        )
        html = (Path(__file__).parent / "fixtures" / fixture).read_text()
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **kwargs: httpx.Response(200, text=html, request=httpx.Request("GET", url)),
        )
        source = (
            KaveiktiSource("https://www.kaveikti.lt/renginiai/vilniuje")
            if source_type == "kaveikti"
            else VilniusEventsSource("https://www.vilnius-events.lt/en/")
        )
    output = BytesIO()
    Image.new("RGB", (8, 8)).save(output, "PNG")
    calls = []

    def download(url):
        calls.append(url)
        return output.getvalue()

    monkeypatch.setattr("pino_core.media.download_image", download)
    store = SQLiteStore(tmp_path / "db.sqlite")
    pipeline = CheckPipeline(store, [source], media=MediaConfig(directory=tmp_path / "media"))
    result = pipeline.run()
    expected = 2 if source_type == "static_yaml" else 1
    assert len(result.records[0].images) == expected
    assert len(store.list_records()[0].images) == expected
    assert all((tmp_path / "media" / image.path).is_file() for image in result.records[0].images)
    pipeline.run()
    assert len(calls) == expected
