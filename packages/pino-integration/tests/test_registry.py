import pytest

from pino_core.config import SourceConfig
from pino_integration.kaveikti import KaveiktiSource
from pino_integration.registry import build_sources
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
        ],
    )

    assert [type(source) for source in sources] == [KaveiktiSource, VilniusEventsSource]


def test_integration_factories_validate_required_url() -> None:
    with pytest.raises(ValueError, match="kaveikti source requires url"):
        build_sources([SourceConfig(name="kaveikti-vilnius", type="kaveikti")])
