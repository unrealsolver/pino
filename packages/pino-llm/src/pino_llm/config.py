from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator


ProviderName = Literal["echo", "infercom", "minimax", "ollama"]
ThinkMode = bool | Literal["low", "medium", "high"]
_PROVIDER_NAMES = {"echo", "infercom", "minimax", "ollama"}


class ModelProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    temperature: float = Field(default=0.1, ge=0)
    top_p: float = Field(default=0.1, ge=0, le=1)
    think: ThinkMode | None = None
    num_ctx: int | None = Field(default=None, ge=1)
    num_predict: int | None = Field(default=None, ge=1)


class ResolvedModelProfile(ModelProfileConfig):
    provider: ProviderName

    @model_validator(mode="after")
    def validate_provider_options(self) -> ResolvedModelProfile:
        if self.provider != "ollama" and any(
            value is not None for value in (self.think, self.num_ctx, self.num_predict)
        ):
            raise ValueError("think, num_ctx, and num_predict are Ollama-only model options")
        return self


class ModelRegistryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    echo: dict[str, ModelProfileConfig] = Field(
        default_factory=lambda: {"default": ModelProfileConfig(model="echo")}
    )
    infercom: dict[str, ModelProfileConfig] = Field(default_factory=dict)
    minimax: dict[str, ModelProfileConfig] = Field(default_factory=dict)
    ollama: dict[str, ModelProfileConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_profiles(self) -> ModelRegistryConfig:
        for provider in _PROVIDER_NAMES:
            for name in getattr(self, provider):
                if not name or ":" in name:
                    raise ValueError(f"model definition name must be plain: {name!r}")
                self.resolve(cast(ProviderName, provider), name)
        return self

    def resolve(self, provider: ProviderName, name: str) -> ResolvedModelProfile:
        try:
            profile = getattr(self, provider)[name]
        except KeyError as exc:
            raise ValueError(f"unknown LLM model profile: {provider}:{name}") from exc
        return ResolvedModelProfile(provider=provider, **profile.model_dump())


class InfercomConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.infercom.ai/v1"
    api_key: str | None = None


class MinimaxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "https://api.minimax.io/v1"
    api_key: str | None = None


class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://localhost:11434"


class ProviderConfigs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    infercom: InfercomConfig = Field(default_factory=InfercomConfig)
    minimax: MinimaxConfig = Field(default_factory=MinimaxConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "echo:default"
    models: ModelRegistryConfig = Field(default_factory=ModelRegistryConfig)
    providers: ProviderConfigs = Field(default_factory=ProviderConfigs)

    @model_validator(mode="after")
    def validate_selected_profile(self) -> LLMConfig:
        self.profile(self.model)
        return self

    def profile(self, reference: str) -> ResolvedModelProfile:
        provider, separator, name = reference.partition(":")
        if not separator or provider not in _PROVIDER_NAMES or not name or ":" in name:
            raise ValueError(
                f"LLM model reference must be fully qualified as provider:name: {reference!r}"
            )
        return self.models.resolve(cast(ProviderName, provider), name)

    def selected_profile(self) -> ResolvedModelProfile:
        return self.profile(self.model)

    def selected_provider(self) -> ProviderName:
        return self.selected_profile().provider

    def selected_model(self) -> str:
        return self.selected_profile().model

    def with_model(self, reference: str) -> LLMConfig:
        self.profile(reference)
        return self.model_copy(update={"model": reference})
