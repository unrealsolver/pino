import tomllib
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).parents[3]
VERSION_OPERATORS = ("==", ">=", "<=", "~=", "!=", ">", "<")


def test_core_package_excludes_third_party_integration_dependencies() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    dependencies = set(data["project"]["dependencies"])

    assert "beautifulsoup4" not in dependencies
    assert "lxml" not in dependencies
    assert "telethon" not in dependencies


def test_workspace_dependency_versions_are_exact_constraints() -> None:
    root_data = tomllib.loads((WORKSPACE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    workspace_packages = {"pino-cli", "pino-core", "pino-integration", "pino-llm", "pino-workspace"}
    constrained_packages = {
        dependency.split("==", maxsplit=1)[0]
        for dependency in root_data["tool"]["uv"]["constraint-dependencies"]
    }
    external_dependencies: set[str] = set()

    for dependency in root_data["dependency-groups"]["dev"]:
        assert not _has_version_operator(dependency)
        external_dependencies.add(_dependency_name(dependency))

    for pyproject in sorted((WORKSPACE_ROOT / "packages").glob("*/pyproject.toml")) + sorted(
        (WORKSPACE_ROOT / "apps").glob("*/pyproject.toml"),
    ):
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        for dependency in data["project"].get("dependencies", []):
            assert not _has_version_operator(dependency)
            name = _dependency_name(dependency)
            if name not in workspace_packages:
                external_dependencies.add(name)

    for dependency in root_data["tool"]["uv"]["constraint-dependencies"]:
        assert "==" in dependency

    assert external_dependencies <= constrained_packages


def _has_version_operator(dependency: str) -> bool:
    return any(operator in dependency for operator in VERSION_OPERATORS)


def _dependency_name(dependency: str) -> str:
    return dependency.split("[", maxsplit=1)[0]
