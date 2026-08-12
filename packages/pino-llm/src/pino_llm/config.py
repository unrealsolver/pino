from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InfercomConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.infercom.ai/v1"
    api_key: str | None = None
    models: dict[str, str] = Field(
        default_factory=lambda: {
            "smart": "MiniMax-M2.5",
            "simple": "gpt-oss-120b",
        },
    )
    default_model: str = "smart"


class MinimaxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.minimax.io/v1"
    api_key: str | None = None
    models: dict[str, str] = Field(
        default_factory=lambda: {
            "smart": "MiniMax-M3",
            "simple": "MiniMax-M3",
        },
    )
    default_model: str = "smart"


class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://localhost:11434"
    models: dict[str, str] = Field(
        default_factory=lambda: {
            "smart": "gpt-oss-20b",
            "simple": "gpt-oss-20b",
        },
    )
    default_model: str = "smart"


class EchoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    default_model: str = "echo"


class ProviderConfigs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    infercom: InfercomConfig = Field(default_factory=InfercomConfig)
    minimax: MinimaxConfig = Field(default_factory=MinimaxConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    echo: EchoConfig = Field(default_factory=EchoConfig)


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_provider: Literal["echo", "infercom", "minimax", "ollama"] = "echo"
    model: str | None = None
    temperature: float = 0.1
    top_p: float = 0.1
    providers: ProviderConfigs = Field(default_factory=ProviderConfigs)

    def selected_model(self) -> str:
        if self.default_provider == "infercom":
            return _resolve_model_alias(
                self.providers.infercom.models,
                self.model or self.providers.infercom.default_model,
            )
        if self.default_provider == "minimax":
            return _resolve_model_alias(
                self.providers.minimax.models,
                self.model or self.providers.minimax.default_model,
            )
        if self.default_provider == "ollama":
            return _resolve_model_alias(
                self.providers.ollama.models,
                self.model or self.providers.ollama.default_model,
            )
        return self.providers.echo.default_model


def _resolve_model_alias(models: dict[str, str], value: str) -> str:
    return models.get(value, value)
