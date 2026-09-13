import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("release", SCRIPTS / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def archive_at(path, extra=()):
    files = {
        "pyproject.toml": b"",
        "uv.lock": b"",
        "web/dist/index.html": b"hello",
        "release.json": json.dumps({"version": "v1.2.3", "commit": "a" * 40}).encode(),
    }
    with tarfile.open(path, "w:gz") as tar:
        for name, value in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(value)
            info.mode = 0o777
            tar.addfile(info, io.BytesIO(value))
        for info in extra:
            tar.addfile(info, io.BytesIO(b""))
    return release.digest(path)


def test_extract_and_refuse_overwrite(tmp_path):
    archive = tmp_path / "release.tar.gz"
    checksum = archive_at(archive)
    dest = tmp_path / "release"
    release.unpack(archive, checksum, dest, "v1.2.3")
    assert (dest / "web/dist/index.html").read_text() == "hello"
    assert (dest / "web/dist/index.html").stat().st_mode & 0o777 == 0o644
    with pytest.raises(ValueError, match="already exists"):
        release.unpack(archive, checksum, dest, "v1.2.3")


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../escape", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("web/dist/link", tarfile.SYMTYPE),
        ("web/dist/hardlink", tarfile.LNKTYPE),
        ("web/dist/fifo", tarfile.FIFOTYPE),
        ("web/dist/.env", tarfile.REGTYPE),
        ("web/dist/index.html", tarfile.REGTYPE),
        ("config.yaml", tarfile.REGTYPE),
    ],
)
def test_reject_unsafe_archive_before_extracting(tmp_path, name, kind):
    item = tarfile.TarInfo(name)
    item.type = kind
    item.linkname = "/etc/passwd"
    archive = tmp_path / "release.tar.gz"
    checksum = archive_at(archive, [item])
    dest = tmp_path / "release"
    with pytest.raises(ValueError, match="unsafe"):
        release.unpack(archive, checksum, dest, "v1.2.3")
    assert not dest.exists()


def test_bad_checksum_and_identity(tmp_path):
    archive = tmp_path / "release.tar.gz"
    checksum = archive_at(archive)
    with pytest.raises(ValueError, match="checksum"):
        release.unpack(archive, "0" * 64, tmp_path / "bad", "v1.2.3")
    with pytest.raises(ValueError, match="identity"):
        release.unpack(archive, checksum, tmp_path / "bad", "v1.2.4")


@pytest.mark.parametrize("value", ["../v1.2.3", "v01.2.3", "1.2.3", "v1.2.3;id", "v1.2.3\n"])
def test_invalid_versions(value):
    with pytest.raises(ValueError):
        release.version(value)


def test_package_allowlist_and_manifest(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init")
    files = {
        "pyproject.toml": "",
        "uv.lock": "",
        "README.md": "readme",
        "apps/pino-web/pyproject.toml": "",
        "apps/pino-web/src/pino_web/app.py": "",
        "packages/pino-core/src/pino_core/migrations/versions/0001.py": "",
        "packages/pino-core/tests/golden.yaml": "exclude",
        "config.yaml": "secret",
        ".env": "secret",
        "web/dist/index.html": "built",
    }
    for name, content in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "test")
    archive = release.pack(tmp_path, "v1.2.3", tmp_path / "out")
    dest = tmp_path / "unpacked"
    release.unpack(archive, release.digest(archive), dest, "v1.2.3")
    assert (dest / "apps/pino-web/src/pino_web/app.py").exists()
    assert not (dest / "config.yaml").exists()
    assert not (dest / ".env").exists()
    assert not (dest / "packages/pino-core/tests").exists()


def test_verify_commit_without_extracting(tmp_path):
    archive = tmp_path / "release.tar.gz"
    checksum = archive_at(archive)
    release.unpack(archive, checksum, None, "v1.2.3", "a" * 40)
    with pytest.raises(ValueError, match="commit"):
        release.unpack(archive, checksum, None, "v1.2.3", "b" * 40)
    assert list(tmp_path.iterdir()) == [archive]


def test_ci_invokes_canonical_infrastructure_helper(tmp_path):
    import yaml

    workflow = yaml.safe_load((SCRIPTS.parent / ".github/workflows/deploy.yml").read_text())
    assert workflow["concurrency"]["cancel-in-progress"] is False
    step = next(
        s for s in workflow["jobs"]["deploy"]["steps"] if s.get("name") == "Upload and activate"
    )
    assert step["env"]["DEPLOY_USER"] == "pino-deploy"
    log = tmp_path / "calls"
    stub = tmp_path / "stub"
    stub.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\n"
        "with open(os.environ['CALL_LOG'], 'a') as f:\n"
        "    f.write(json.dumps(sys.argv) + '\\n')\n"
    )
    stub.chmod(0o755)
    for name in ("ssh", "scp"):
        (tmp_path / name).symlink_to(stub)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "CALL_LOG": str(log),
        "DEPLOY_HOST": "example.test",
        "DEPLOY_USER": "pino-deploy",
        "DEPLOY_PORT": "2222",
        "DEPLOY_SSH_KEY": "test key",
        "DEPLOY_KNOWN_HOSTS": "test host",
        "VERSION": "v1.2.3",
        "RELEASE_CHECKSUM": "b" * 64,
        "RELEASE_COMMIT": "a" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
    }
    subprocess.run(["bash", "-c", step["run"]], env=env, cwd=tmp_path, check=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 3
    assert calls[-1][-1] == (
        "pino-release deploy 'v1.2.3' '/home/pino-deploy/incoming/123-2/pino-v1.2.3.tar.gz' "
        f"--sha256 '{'b' * 64}' --commit '{'a' * 40}'"
    )
    assert "pino-deploy@example.test" in calls[-1]
    assert "StrictHostKeyChecking=yes" in calls[-1]
    assert "sudo" not in calls[-1][-1]
