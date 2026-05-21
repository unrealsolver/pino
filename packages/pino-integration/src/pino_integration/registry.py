from __future__ import annotations

from pino_core.config import SourceConfig
from pino_core.registry import default_source_registry
from pino_core.sources import SourceAdapter, SourceRegistry

from pino_integration.kaveikti import build_kaveikti_source
from pino_integration.telegram import build_telegram_channel_source
from pino_integration.vilnius_events import build_vilnius_events_source


def register_integrations(registry: SourceRegistry) -> SourceRegistry:
    registry.register("kaveikti", build_kaveikti_source)
    registry.register("telegram_channel", build_telegram_channel_source)
    registry.register("vilnius_events", build_vilnius_events_source)
    return registry


def integration_source_registry() -> SourceRegistry:
    return register_integrations(default_source_registry())


def build_sources(configs: list[SourceConfig]) -> list[SourceAdapter]:
    return integration_source_registry().build_many(configs)
