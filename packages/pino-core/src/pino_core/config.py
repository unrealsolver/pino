from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Path = Path(".pino/pino.sqlite")


class InfercomConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.infercom.ai/v1"
    api_key_file: Path = Path("INFERCOM_API_KEY")
    default_model: str = "MiniMax-M2.5"


class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://localhost:11434"
    default_model: str = "gpt-oss-20b"


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["echo", "infercom", "ollama"] = "echo"
    model: str | None = None
    temperature: float = 0.1
    top_p: float = 0.1
    infercom: InfercomConfig = Field(default_factory=InfercomConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)

    def selected_model(self) -> str:
        if self.model:
            return self.model
        if self.provider == "infercom":
            return self.infercom.default_model
        if self.provider == "ollama":
            return self.ollama.default_model
        return "echo"


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
        default_path = Path("config.local.yaml")
        path = default_path if default_path.exists() else Path("config.example.yaml")

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config = PinoConfig.model_validate(raw)
    return _resolve_paths(config, config_path.parent)


def _resolve_paths(config: PinoConfig, base_dir: Path) -> PinoConfig:
    data = config.model_dump(mode="python")
    data["storage"]["path"] = _resolve_path(config.storage.path, base_dir)
    data["llm"]["infercom"]["api_key_file"] = _resolve_path(
        config.llm.infercom.api_key_file,
        base_dir,
    )
    for source in data["sources"]:
        source["path"] = _resolve_path(source["path"], base_dir)
    return PinoConfig.model_validate(data)


def _resolve_path(path: Path, base_dir: Path) -> Path:
    return path if path.is_absolute() else base_dir / path

