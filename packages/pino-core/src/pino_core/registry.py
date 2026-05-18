from __future__ import annotations

from pino_core.config import SourceConfig
from pino_core.integrations.kaveikti import build_kaveikti_source
from pino_core.sources import SourceAdapter, SourceRegistry, build_static_yaml_source


def default_source_registry() -> SourceRegistry:
    registry = SourceRegistry()
    registry.register("static_yaml", build_static_yaml_source)
    registry.register("kaveikti", build_kaveikti_source)
    return registry


def build_sources(configs: list[SourceConfig]) -> list[SourceAdapter]:
    return default_source_registry().build_many(configs)
