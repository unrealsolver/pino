"""Build/verify Pino artifacts and unpack them for CI smoke tests (stdlib only)."""

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile


def version(value: str) -> str:
    if not re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError("version must be vMAJOR.MINOR.PATCH (no leading zeroes)")
    return value


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def included(path: PurePosixPath) -> bool:
    if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
        return False
    return (
        str(path) in {"pyproject.toml", "uv.lock", "README.md"}
        or (
            len(path.parts) == 3
            and path.parts[0] in {"apps", "packages"}
            and path.name == "pyproject.toml"
        )
        or (
            len(path.parts) > 3
            and path.parts[0] in {"apps", "packages"}
            and path.parts[2] == "src"
            and path.suffix not in {".pyc", ".pyo"}
        )
    )


def pack(root: Path, tag: str, output: Path) -> Path:
    version(tag)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    paths = [Path(name) for name in tracked if name and included(PurePosixPath(name))]
    paths += [path.relative_to(root) for path in (root / "web/dist").rglob("*") if path.is_file()]
    if not (root / "web/dist/index.html").is_file():
        raise ValueError("build web/dist before packaging")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"pino-{tag}.tar.gz"
    with tarfile.open(archive, "x:gz") as tar:
        for path in sorted(paths):
            if (root / path).is_symlink():
                raise ValueError(f"symlinks are not allowed: {path}")
            tar.add(root / path, arcname=str(path), recursive=False)
        manifest = json.dumps({"version": tag, "commit": commit}).encode()
        info = tarfile.TarInfo("release.json")
        info.size = len(manifest)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(manifest))
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{digest(archive)}  {archive.name}\n"
    )
    return archive


def unpack(
    archive: Path,
    checksum: str,
    destination: Path | None,
    tag: str,
    expected_commit: str | None = None,
) -> None:
    version(tag)
    if not re.fullmatch(r"[0-9a-f]{64}", checksum) or digest(archive) != checksum:
        raise ValueError("archive checksum mismatch")
    if destination is not None and (destination.exists() or destination.is_symlink()):
        raise ValueError("release destination already exists")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        names = set()
        total = 0
        for member in members:
            path = PurePosixPath(member.name)
            if (
                not member.isfile()
                or path.is_absolute()
                or ".." in path.parts
                or str(path) != member.name
                or member.name in names
                or not (
                    included(path)
                    or member.name == "release.json"
                    or (
                        path.parts[:2] == ("web", "dist")
                        and not any(part.startswith(".") for part in path.parts)
                    )
                )
            ):
                raise ValueError(f"unsafe archive entry: {member.name}")
            names.add(member.name)
            total += member.size
        if total > 2 * 1024 * 1024 * 1024 or len(members) > 100000:
            raise ValueError("release exceeds extraction limits")
        if not {"pyproject.toml", "uv.lock", "release.json", "web/dist/index.html"} <= names:
            raise ValueError("incomplete release")
        manifest = json.load(tar.extractfile("release.json"))
        if manifest.get("version") != tag or not re.fullmatch(
            r"[0-9a-f]{40}", manifest.get("commit", "")
        ):
            raise ValueError("invalid release identity")
        if expected_commit is not None and manifest["commit"] != expected_commit:
            raise ValueError("release commit does not match the published tag")
        if destination is None:
            return
        destination.mkdir(parents=True)
        # No links or special entries; normalize permissions rather than trusting archive modes.
        for member in members:
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o644)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("pack")
    build.add_argument("version", type=version)
    build.add_argument("--output", type=Path, default=Path("dist"))
    extract = commands.add_parser("unpack")
    extract.add_argument("archive", type=Path)
    extract.add_argument("checksum")
    extract.add_argument("destination", type=Path)
    extract.add_argument("version", type=version)
    verify = commands.add_parser("verify")
    verify.add_argument("archive", type=Path)
    verify.add_argument("checksum")
    verify.add_argument("version", type=version)
    verify.add_argument("commit")
    args = parser.parse_args()
    if args.command == "pack":
        print(pack(Path.cwd(), args.version, args.output))
    elif args.command == "unpack":
        unpack(args.archive, args.checksum, args.destination, args.version)
    else:
        unpack(args.archive, args.checksum, None, args.version, args.commit)


if __name__ == "__main__":
    main()
