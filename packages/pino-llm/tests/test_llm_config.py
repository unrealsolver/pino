from pino_llm.config import LLMConfig


def test_llm_config_resolves_infercom_model_aliases() -> None:
    config = LLMConfig(default_provider="infercom", model="simple")

    assert config.selected_model() == "gpt-oss-120b"


def test_llm_config_sets_ollama_smart_and_simple_to_local_model() -> None:
    config = LLMConfig(default_provider="ollama", model="smart")
    simple_config = LLMConfig(default_provider="ollama", model="simple")

    assert config.selected_model() == "gpt-oss-20b"
    assert simple_config.selected_model() == "gpt-oss-20b"

