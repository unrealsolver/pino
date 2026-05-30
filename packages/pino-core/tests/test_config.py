import logging
from pathlib import Path

import pytest

from pino_core.config import load_config


def test_load_config_resolves_paths_relative_to_config_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "pino.yaml"
    config_path.write_text(
        """
storage:
  path: data/pino.sqlite
sources:
  - name: sample
    type: static_yaml
    path: sources/sample.yaml
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.storage.path == config_dir / "data/pino.sqlite"
    assert config.sources[0].path == config_dir / "sources/sample.yaml"


def test_load_config_accepts_kaveikti_source(tmp_path: Path) -> None:
    config_path = tmp_path / "pino.yaml"
    config_path.write_text(
        """
sources:
  - name: kaveikti-vilnius
    type: kaveikti
    url: https://www.kaveikti.lt/renginiai/vilniuje
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.sources[0].type == "kaveikti"
    assert config.sources[0].url == "https://www.kaveikti.lt/renginiai/vilniuje"


def test_load_config_accepts_vilnius_events_source(tmp_path: Path) -> None:
    config_path = tmp_path / "pino.yaml"
    config_path.write_text(
        """
sources:
  - name: vilnius-events
    type: vilnius_events
    url: https://www.vilnius-events.lt/en/
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.sources[0].type == "vilnius_events"
    assert config.sources[0].url == "https://www.vilnius-events.lt/en/"


def test_load_config_accepts_source_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    config_path = tmp_path / "pino.yaml"
    config_path.write_text(
        """
sources:
  - name: afisha-vilnius
    type: telegram_channel
    url: https://t.me/afishavilnius
    settings:
      api_id: env:TELEGRAM_API_ID
      api_hash: env:TELEGRAM_API_HASH
      session_path: .pino/telegram
      limit: 50
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        """
TELEGRAM_API_ID=12345
TELEGRAM_API_HASH=hash-from-env-file
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.sources[0].type == "telegram_channel"
    assert config.sources[0].settings["api_id"] == "12345"
    assert config.sources[0].settings["api_hash"] == "hash-from-env-file"
    assert config.sources[0].settings["limit"] == 50


def test_load_config_resolves_env_refs_from_process_env_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "pino.yaml"
    config_path.write_text(
        """
llm:
  providers:
    infercom:
      api_key: env:INFERCOM_API_KEY
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("INFERCOM_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("INFERCOM_API_KEY", "from-process")

    config = load_config(config_path)

    assert config.llm.providers.infercom.api_key == "from-process"


def test_load_config_resolves_env_refs_from_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INFERCOM_API_KEY", raising=False)
    config_path = tmp_path / "pino.yaml"
    config_path.write_text(
        """
llm:
  providers:
    infercom:
      api_key: env:INFERCOM_API_KEY
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("INFERCOM_API_KEY=from-dotenv\n", encoding="utf-8")

    config = load_config(config_path)

    assert config.llm.providers.infercom.api_key == "from-dotenv"


def test_load_config_sets_missing_env_refs_to_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("INFERCOM_API_KEY", raising=False)
    caplog.set_level(logging.WARNING, logger="pino_core.config")
    config_path = tmp_path / "pino.yaml"
    config_path.write_text(
        """
llm:
  providers:
    infercom:
      api_key: env:INFERCOM_API_KEY
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.llm.providers.infercom.api_key is None
    assert "INFERCOM_API_KEY" in caplog.text
    assert "llm.providers.infercom.api_key" in caplog.text
    assert "Set the config value to null to silence this warning" in caplog.text


def test_load_config_does_not_warn_for_explicit_null_secret(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="pino_core.config")
    config_path = tmp_path / "pino.yaml"
    config_path.write_text(
        """
llm:
  providers:
    infercom:
      api_key: null
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.llm.providers.infercom.api_key is None
    assert caplog.text == ""


def test_load_config_does_not_resolve_ordinary_strings(tmp_path: Path) -> None:
    config_path = tmp_path / "pino.yaml"
    config_path.write_text(
        """
sources:
  - name: sample
    type: static_yaml
    path: env:NOT_A_SECRET.yaml
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.sources[0].path == tmp_path / "env:NOT_A_SECRET.yaml"
