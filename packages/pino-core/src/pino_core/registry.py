from __future__ import annotations

from pino_core.config import SourceConfig
from pino_core.sources import SourceAdapter, StaticYamlSource


def build_sources(configs: list[SourceConfig]) -> list[SourceAdapter]:
    sources: list[SourceAdapter] = []
    for source_config in configs:
        if not source_config.enabled:
            continue
        if source_config.type == "static_yaml":
            sources.append(StaticYamlSource(source_config.path, name=source_config.name))
        else:
            raise ValueError(f"Unsupported source type: {source_config.type}")
    return sources

