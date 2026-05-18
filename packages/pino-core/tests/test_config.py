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
