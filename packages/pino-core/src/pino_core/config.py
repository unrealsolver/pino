from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pino_llm import LLMConfig


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path = Path(".pino/pino.sqlite")


class ChatConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    history_limit: int = 20
    max_tool_rounds: int = 2


class GoalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "simple"
    batch_size: int = 10
    goals: list[GoalConfig] = Field(
        default_factory=lambda: [
            GoalConfig(
                name="meet_people",
                description="Social occasions in Vilnius where Boss could meet women or new people.",
            ),
            GoalConfig(name="metal_music", description="Metal music concerts, festivals, or meetups."),
            GoalConfig(
                name="electronic_music",
                description="Electronic music events, especially synth-related events.",
            ),
            GoalConfig(
                name="open_synth_jam",
                description="Open synth jam, participatory music jam, or similar events.",
            ),
            GoalConfig(
                name="volunteering_community",
                description="Volunteering, community work, initiatives, workshops, or gatherings.",
            ),
        ],
    )


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    path: Path | None = None
    url: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_source_target(self) -> SourceConfig:
        if self.type == "static_yaml" and self.path is None:
            raise ValueError("static_yaml source requires path")
        return self


class PinoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage: StorageConfig = Field(default_factory=StorageConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
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
        if source.get("path") is not None:
            source["path"] = _resolve_path(source["path"], base_dir)
    return PinoConfig.model_validate(data)


def _resolve_path(path: Path, base_dir: Path) -> Path:
    return path if path.is_absolute() else base_dir / path


def _default_config_path() -> Path:
    for path in (Path("config.local.yaml"), Path("config.yaml"), Path("config.example.yaml")):
        if path.exists():
            return path
    return Path("config.example.yaml")
