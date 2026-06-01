from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pino_llm import LLMConfig

logger = logging.getLogger(__name__)


class StorageBackendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["sqlite", "postgres"]
    path: Path | None = None
    url: str | None = None

    def database_url(self, name: str) -> str:
        if self.type == "sqlite":
            if self.path is None:
                raise ValueError(f"storage backend {name!r} requires path for type sqlite")
            return f"sqlite:///{self.path}"
        if self.url is None:
            raise ValueError(f"storage backend {name!r} requires url for type postgres")
        return self.url


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    __pydantic_extra__: dict[str, StorageBackendConfig] = Field(init=False)

    use: str = "local"
    local: StorageBackendConfig = Field(
        default_factory=lambda: StorageBackendConfig(
            type="sqlite",
            path=Path(".pino/pino.sqlite"),
        ),
    )

    @model_validator(mode="after")
    def validate_selected_backend(self) -> StorageConfig:
        if self.use not in self.backends():
            raise ValueError(f"storage.use references unknown backend: {self.use!r}")
        return self

    def backends(self) -> dict[str, StorageBackendConfig]:
        return {"local": self.local, **(self.__pydantic_extra__ or {})}

    def database_url(self) -> str:
        return self.backends()[self.use].database_url(self.use)


class ChatConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    history_limit: int = 20
    active_memory_limit: int = 20
    max_tool_rounds: int = 2
    max_tools_per_round: int = Field(default=3, ge=1, le=10)


class GoalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str


class TaxonomyCategoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str


class RefinementConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "simple"
    batch_size: int = 10
    schema_version: int = 1
    taxonomy_version: int = 1
    categories: list[TaxonomyCategoryConfig] = Field(
        default_factory=lambda: [
            TaxonomyCategoryConfig(
                name="social",
                description="Social occasions with natural conversation or opportunities to meet people.",
            ),
            TaxonomyCategoryConfig(
                name="metal_music", description="Metal music concerts or festivals."
            ),
            TaxonomyCategoryConfig(
                name="electronic_music",
                description="Electronic music events, especially synth-related music.",
            ),
            TaxonomyCategoryConfig(
                name="open_synth_jam",
                description="Open synth jams, participatory music jams, or similar events.",
            ),
            TaxonomyCategoryConfig(name="live_music", description="Live music performances."),
            TaxonomyCategoryConfig(
                name="volunteering", description="Volunteering or community work."
            ),
            TaxonomyCategoryConfig(
                name="community", description="Community initiatives or gatherings."
            ),
            TaxonomyCategoryConfig(name="workshop", description="Participatory workshops."),
            TaxonomyCategoryConfig(name="theatre", description="Theatre performances."),
            TaxonomyCategoryConfig(name="pottery", description="Pottery workshops or gatherings."),
            TaxonomyCategoryConfig(
                name="dating",
                description="Events explicitly intended for dating or meeting potential partners.",
            ),
        ],
    )


class ProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goals: list[GoalConfig] = Field(
        default_factory=lambda: [
            GoalConfig(
                name="meet_people",
                description="Social occasions in Vilnius where Boss could meet women or new people.",
            ),
            GoalConfig(
                name="metal_music", description="Metal music concerts, festivals, or meetups."
            ),
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
    refinement: RefinementConfig = Field(default_factory=RefinementConfig)
    profile: ProfileConfig = Field(default_factory=ProfileConfig)
    sources: list[SourceConfig] = Field(default_factory=list)


def load_config(path: Path | str | None = None) -> PinoConfig:
    if path is None:
        path = _default_config_path()

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    env_values = _load_env_file(config_path.parent / ".env")
    raw = _resolve_env_refs(raw, env_values=env_values)
    config = PinoConfig.model_validate(raw)
    return _resolve_paths(config, config_path.parent)


def _resolve_paths(config: PinoConfig, base_dir: Path) -> PinoConfig:
    data = config.model_dump(mode="python")
    for name, backend in config.storage.backends().items():
        if backend.path is not None:
            data["storage"][name]["path"] = _resolve_path(backend.path, base_dir)
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


_ENV_REF_PATTERN = re.compile(r"^env:([A-Za-z_][A-Za-z0-9_]*)$")


def _resolve_env_refs(value: Any, *, env_values: dict[str, str], path: str = "") -> Any:
    if isinstance(value, dict):
        return {
            key: _resolve_env_refs(
                item,
                env_values=env_values,
                path=f"{path}.{key}" if path else str(key),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_env_refs(item, env_values=env_values, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        match = _ENV_REF_PATTERN.match(value.strip())
        if match is None:
            return value
        env_name = match.group(1)
        resolved = os.environ.get(env_name)
        if resolved is None:
            resolved = env_values.get(env_name)
        if resolved is None or resolved == "":
            logger.warning(
                "Environment variable %s referenced by config path %s is missing; "
                "using null. Set the config value to null to silence this warning.",
                env_name,
                path,
            )
            return None
        return resolved
    return value


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise ValueError(f"Invalid .env line {line_number}: expected NAME=value")
        name, raw_value = line.split("=", maxsplit=1)
        name = name.strip()
        if not _ENV_REF_PATTERN.match(f"env:{name}"):
            raise ValueError(f"Invalid .env variable name on line {line_number}: {name!r}")
        values[name] = _parse_env_value(raw_value.strip())
    return values


def _parse_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if " #" in value:
        value = value.split(" #", maxsplit=1)[0].rstrip()
    return value
