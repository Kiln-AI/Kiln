"""Frozen data: one tenant's records, captured so every episode starts from the same bytes.

A fixture is a directory holding a read-only `state.sqlite` and a `fixture.yaml` sidecar
that records what it was frozen from and the hash it must still have. Freezing goes through
a pending directory and one `os.rename`, so a fixture directory is either absent or
complete — a half-written fixture is the kind of thing that costs a week of confused
debugging.

Build artifacts that belong to a fixture but are not database state (an export, a facts
file, a judge baseline) are added afterwards by `seal`, which records their hashes in the
sidecar. `verify` then checks them alongside the state file.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, Mapping

import yaml
from pydantic import BaseModel

from . import conformance
from .clock import Clock
from .errors import WorldBug

if TYPE_CHECKING:
    from .instances import Instance
    from .world import World

STATE_NAME = "state.sqlite"
SIDECAR_NAME = "fixture.yaml"

_HASH_CACHE: dict[Path, tuple[int, int, str]] = {}


class FixtureMeta(BaseModel, frozen=True, extra="forbid"):
    format_version: Literal[1]
    id: str
    world: str
    world_version: str
    schema_hash: str
    now: str
    parent_id: str | None
    file_sha256: str
    created_at: str
    description: str
    artifacts_sha256: dict[str, str] = {}


@dataclass(frozen=True)
class Fixture:
    meta: FixtureMeta
    dir: Path

    @property
    def id(self) -> str:
        return self.meta.id

    @property
    def now(self) -> str:
        return self.meta.now

    @property
    def description(self) -> str:
        return self.meta.description

    @property
    def parent_id(self) -> str | None:
        return self.meta.parent_id

    @property
    def state_path(self) -> Path:
        return self.dir / STATE_NAME


def check_id(fixture_id: str) -> str:
    """A fixture id is one path segment. Checked before any filesystem access, so a
    traversal attempt never reaches `open`."""
    if (
        not isinstance(fixture_id, str)
        or not fixture_id
        or fixture_id != Path(fixture_id).name
        or fixture_id.startswith(".")
    ):
        raise WorldBug(
            f"fixture id {fixture_id!r} must be a single directory name that does not "
            "start with a dot"
        )
    return fixture_id


def file_sha256(path: Path) -> str:
    stat = path.stat()
    cached = _HASH_CACHE.get(path)
    if (
        cached is not None
        and cached[0] == stat.st_mtime_ns
        and cached[1] == stat.st_size
    ):
        return cached[2]
    running = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            running.update(block)
    digest = running.hexdigest()
    _HASH_CACHE[path] = (stat.st_mtime_ns, stat.st_size, digest)
    return digest


def load(fixture_dir: Path) -> Fixture:
    sidecar = Path(fixture_dir) / SIDECAR_NAME
    try:
        raw = yaml.safe_load(sidecar.read_text())
    except FileNotFoundError as e:
        raise WorldBug(f"{sidecar} is missing; this is not a fixture directory") from e
    except yaml.YAMLError as e:
        raise WorldBug(f"{sidecar} is not valid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise WorldBug(f"{sidecar} does not hold a fixture sidecar mapping")
    if raw.get("format_version") != 1:
        raise WorldBug(
            f"{sidecar} has format_version {raw.get('format_version')!r}; this runtime "
            "reads version 1"
        )
    try:
        meta = FixtureMeta.model_validate(raw)
    except Exception as e:
        raise WorldBug(f"{sidecar} is not a valid fixture sidecar: {e}") from e
    return Fixture(meta=meta, dir=Path(fixture_dir))


def load_all(fixtures_dir: Path) -> dict[str, Fixture]:
    directory = Path(fixtures_dir)
    if not directory.is_dir():
        return {}
    found: dict[str, Fixture] = {}
    for child in sorted(directory.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        fixture = load(child)
        if fixture.id in found:
            raise WorldBug(
                f"two fixture directories claim the id {fixture.id!r}: "
                f"{found[fixture.id].dir} and {child}"
            )
        found[fixture.id] = fixture
    return found


def verify(fixture: Fixture) -> None:
    """Confirm the fixture's bytes are the bytes it was frozen with."""
    actual = file_sha256(fixture.state_path)
    if actual != fixture.meta.file_sha256:
        raise WorldBug(
            f"{fixture.state_path} has changed since it was frozen "
            f"(expected {fixture.meta.file_sha256}, found {actual})"
        )
    for name, expected in sorted(fixture.meta.artifacts_sha256.items()):
        path = fixture.dir / name
        if not path.is_file():
            raise WorldBug(f"{path} is recorded in the sidecar but missing")
        found = file_sha256(path)
        if found != expected:
            raise WorldBug(
                f"{path} has changed since it was sealed "
                f"(expected {expected}, found {found})"
            )


def freeze(
    instance: "Instance", id: str, description: str, *, fixtures_dir: Path
) -> Fixture:
    check_id(id)
    world = instance.world
    fixtures_dir = Path(fixtures_dir)
    target = fixtures_dir / id
    if target.exists():
        raise WorldBug(f"a fixture already lives at {target}")
    if instance.db.in_transaction:
        raise WorldBug("cannot freeze inside a transaction; commit the writes first")
    conformance.check(instance.db.conn, world)

    pending = fixtures_dir / f".pending-{id}"
    try:
        pending.mkdir(parents=True)
    except FileExistsError as e:
        raise WorldBug(
            f"{pending} already exists, so either another freeze of '{id}' is running or an "
            "earlier one was killed mid-write; remove it once you are sure nothing else is "
            "writing there"
        ) from e
    try:
        state = pending / STATE_NAME
        instance.db.conn.execute("VACUUM INTO ?", (str(state),))
        meta = FixtureMeta(
            format_version=1,
            id=id,
            world=world.name,
            world_version=world.version,
            schema_hash=world.schema_hash,
            now=instance.clock.iso(),
            parent_id=instance.fixture,
            file_sha256=file_sha256(state),
            created_at=Clock.wall().iso(),
            description=description,
            artifacts_sha256={},
        )
        _write_sidecar(pending / SIDECAR_NAME, meta)
        os.chmod(state, 0o444)
        os.rename(pending, target)
    except BaseException:
        shutil.rmtree(pending, ignore_errors=True)
        raise
    return load(target)


def seal(fixture_dir: Path, artifacts: Mapping[str, Path]) -> FixtureMeta:
    """Record build artifacts beside a frozen fixture, hashed into its sidecar.

    The state file and its hash are untouched: sealing is additive bookkeeping, run after
    the fixture exists, and re-running it replaces the whole map so a stale hash can never
    outlive a rebuilt artifact.
    """
    fixture_dir = Path(fixture_dir)
    meta = load(fixture_dir).meta
    sources: dict[str, Path] = {}
    for name, source in artifacts.items():
        if name != Path(name).name or name.startswith(".") or not name:
            raise WorldBug(f"artifact name {name!r} must be a plain file name")
        if name in (STATE_NAME, SIDECAR_NAME):
            raise WorldBug(f"artifact name {name!r} is the fixture's own file")
        source = Path(source)
        if not source.is_file():
            raise WorldBug(f"artifact {name!r} has no source file at {source}")
        sources[name] = source

    hashes: dict[str, str] = {}
    for name, source in sources.items():
        destination = fixture_dir / name
        if source.resolve() != destination.resolve():
            if destination.exists():
                os.chmod(destination, 0o644)
            shutil.copyfile(source, destination)
        os.chmod(destination, 0o444)
        hashes[name] = file_sha256(destination)

    sealed = meta.model_copy(update={"artifacts_sha256": hashes})
    sidecar = fixture_dir / SIDECAR_NAME
    if sidecar.exists():
        os.chmod(sidecar, 0o644)
    _write_sidecar(sidecar, sealed)
    os.chmod(sidecar, 0o444)
    return sealed


def fork(
    world: "World",
    parent: str,
    id: str,
    generator: Callable[["Instance"], None],
    *,
    description: str,
) -> Fixture:
    """A new fixture from an existing one plus a mutation. A generator that raises leaves
    nothing behind."""
    instance = world.instance(parent)
    try:
        generator(instance)
        return instance.freeze(id, description)
    finally:
        instance.destroy()


def _write_sidecar(path: Path, meta: FixtureMeta) -> None:
    payload: dict[str, Any] = meta.model_dump()
    path.write_text(yaml.safe_dump(payload, sort_keys=True))
