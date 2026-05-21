import pytest

from pino_core.config import SourceConfig
from pino_integration.kaveikti import KaveiktiSource
from pino_integration.registry import build_sources
from pino_integration.telegram import TelegramChannelSource
from pino_integration.vilnius_events import VilniusEventsSource


def test_build_sources_registers_current_integrations() -> None:
    sources = build_sources(
        [
            SourceConfig(
                name="kaveikti-vilnius",
                type="kaveikti",
                url="https://www.kaveikti.lt/renginiai/vilniuje",
            ),
            SourceConfig(
                name="vilnius-events",
                type="vilnius_events",
                url="https://www.vilnius-events.lt/en/",
            ),
            SourceConfig(
                name="afisha-vilnius",
                type="telegram_channel",
                url="https://t.me/afishavilnius",
                settings={
                    "api_id": 12345,
                    "api_hash": "hash",
                    "limit": 25,
                },
            ),
        ],
    )

    assert [type(source) for source in sources] == [
        KaveiktiSource,
        VilniusEventsSource,
        TelegramChannelSource,
    ]


def test_integration_factories_validate_required_url() -> None:
    with pytest.raises(ValueError, match="kaveikti source requires url"):
        build_sources([SourceConfig(name="kaveikti-vilnius", type="kaveikti")])


def test_telegram_factory_validates_required_credentials() -> None:
    with pytest.raises(ValueError, match="settings.api_id"):
        build_sources(
            [
                SourceConfig(
                    name="afisha-vilnius",
                    type="telegram_channel",
                    url="https://t.me/afishavilnius",
                ),
            ],
        )
