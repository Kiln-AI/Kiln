"""What version of a world produced a trace.

Kiln keys traces on the environment's reported version, so the string has to move whenever
behaviour moves and stay put when nothing has. An authored version number does neither
reliably. This composes one from content: a hash of the package's source files, plus a hash
of the fixtures it ships, rendered `eng1:<16 hex>+g<12 hex>`.

A `VERSION` file beside `pyproject.toml` pins it for a built package; `resolve` prefers that
file and falls back to composing, so a checkout with uncommitted edits reports honestly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .fixtures import load_all

ENGINE_HASH_VERSION = "eng1"
ENGINE_SHORT_LEN = 16
FIXTURES_SHORT_LEN = 12
VERSION_FILE = "VERSION"
_SOURCE_SUFFIXES = (".py", ".sql")


def compose(package_dir: Path) -> str:
    package_dir = Path(package_dir)
    engine = hashlib.sha256()
    source_root = package_dir / "src"
    sources = [
        path
        for path in sorted(
            (p for p in source_root.rglob("*") if p.is_file()),
            key=lambda p: p.relative_to(package_dir).as_posix(),
        )
        if path.suffix in _SOURCE_SUFFIXES and "__pycache__" not in path.parts
    ]
    for path in sources:
        engine.update(path.relative_to(package_dir).as_posix().encode("utf-8"))
        engine.update(b"\0")
        engine.update(path.read_bytes())
        engine.update(b"\0")

    fixtures = hashlib.sha256()
    for fixture_id, fixture in sorted(load_all(package_dir / "fixtures").items()):
        fixtures.update(f"{fixture_id}\0{fixture.meta.file_sha256}\n".encode("utf-8"))

    return (
        f"{ENGINE_HASH_VERSION}:{engine.hexdigest()[:ENGINE_SHORT_LEN]}"
        f"+g{fixtures.hexdigest()[:FIXTURES_SHORT_LEN]}"
    )


def read_version(package_dir: Path) -> str | None:
    path = Path(package_dir) / VERSION_FILE
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def write_version(package_dir: Path) -> str:
    composed = compose(package_dir)
    (Path(package_dir) / VERSION_FILE).write_text(composed + "\n", encoding="utf-8")
    return composed


def resolve(package_dir: Path) -> str:
    return read_version(package_dir) or compose(package_dir)
