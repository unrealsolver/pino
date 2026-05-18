from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pino_llm import LLMConfig


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path = Path(".pino/pino.sqlite")


class ChatConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    history_limit: int = 20
    max_tool_rounds: int = 2


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["static_yaml"]
    path: Path
    enabled: bool = True


class PinoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage: StorageConfig = Field(default_factory=StorageConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    sources: list[SourceConfig] = Field(default_factory=list)


def load_config(path: Path | str | None = None) -> PinoConfig:
    if path is None:
        path = _default_config_path()

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config = PinoConfig.model_validate(raw)
    return _resolve_paths(config, config_path.parent)


def _resolve_paths(config: PinoConfig, base_dir: Path) -> PinoConfig:
    data = config.model_dump(mode="python")
    data["storage"]["path"] = _resolve_path(config.storage.path, base_dir)
    data["llm"]["providers"]["infercom"]["api_key_file"] = _resolve_path(
        config.llm.providers.infercom.api_key_file,
        base_dir,
    )
    for source in data["sources"]:
        source["path"] = _resolve_path(source["path"], base_dir)
    return PinoConfig.model_validate(data)


def _resolve_path(path: Path, base_dir: Path) -> Path:
    return path if path.is_absolute() else base_dir / path


def _default_config_path() -> Path:
    for path in (Path("config.local.yaml"), Path("config.yaml"), Path("config.example.yaml")):
        if path.exists():
            return path
    return Path("config.example.yaml")
