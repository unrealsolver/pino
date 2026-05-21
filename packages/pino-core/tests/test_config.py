from pathlib import Path

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


def test_load_config_accepts_source_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "pino.yaml"
    config_path.write_text(
        """
sources:
  - name: afisha-vilnius
    type: telegram_channel
    url: https://t.me/afishavilnius
    settings:
      api_id_env: TELEGRAM_API_ID
      api_hash_env: TELEGRAM_API_HASH
      session_path: .pino/telegram
      limit: 50
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.sources[0].type == "telegram_channel"
    assert config.sources[0].settings["api_id_env"] == "TELEGRAM_API_ID"
    assert config.sources[0].settings["limit"] == 50
