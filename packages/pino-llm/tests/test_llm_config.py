import pytest
from pydantic import ValidationError

from pino_llm.config import LLMConfig


def test_llm_config_resolves_opaque_profile() -> None:
    config = LLMConfig(
        model="infercom:fast",
        models={
            "infercom": {
                "fast": {
                    "model": "gpt-oss-120b",
                    "temperature": 0,
                }
            }
        },
    )

    assert config.selected_provider() == "infercom"
    assert config.selected_model() == "gpt-oss-120b"
    assert config.selected_profile().temperature == 0


def test_llm_config_rejects_unknown_selected_profile() -> None:
    with pytest.raises(ValidationError, match="fully qualified"):
        LLMConfig(model="raw-provider-model")


def test_llm_config_with_model_requires_registered_alias() -> None:
    config = LLMConfig(
        models={
            "ollama": {"chat": {"model": "gemma4:e4b"}},
        }
    )

    selected = config.with_model("ollama:chat")

    assert selected.model == "ollama:chat"
    assert selected.selected_model() == "gemma4:e4b"
    with pytest.raises(ValueError, match="unknown LLM model profile"):
        config.with_model("ollama:missing")


def test_model_profile_rejects_ollama_options_for_other_providers() -> None:
    with pytest.raises(ValidationError, match="Ollama-only"):
        LLMConfig(
            models={
                "minimax": {
                    "chat": {"model": "MiniMax-M3", "think": False},
                }
            }
        )


def test_model_definition_names_must_be_plain() -> None:
    with pytest.raises(ValidationError, match="definition name must be plain"):
        LLMConfig(models={"ollama": {"ollama:chat": {"model": "gemma4:e4b"}}})
