"""World launchers: turn a launch config into an isolated instance, and release it.

The launcher is the boundary between Kiln and whatever owns a world's state. Kiln
calls five things and interprets nothing else:

    content_version(world, config) -> str | None   cheap, before launch; keys the trace
    launch(world, config)          -> SyntheticInstance   isolated state one job acts on
    finalize(instance)             -> SyntheticInstance   after generation, before grading
    release(instance)                                     drop it
    prune(live)                                           drop instances no trace references

`LocalFilesLauncher` is V1: a fixture is a directory under the world, and an instance
is a copy of it under Kiln's cache. A hosted framework or a gym-style environment is
another implementation of the same protocol, registered by name and selected by
`SyntheticWorld.launcher`.

Retention is the launcher's policy, bounded by what graders need. The trace index reuses
one generation across every judge, indefinitely, so a judge added later may ask for the
state a run left behind. The local launcher answers by keeping the copy as long as the
trace exists (marking copies a run left byte-identical to their source, which are
released after the run, and evicting oldest-first past a size cap). A launcher whose
instances are short-lived instead records what graders need on the instance at
`finalize` (`changes`, a frozen fixture id in `metadata`) and releases the live instance;
Kiln treats a missing live instance as "state unavailable" and skips only the scorers
that read it.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Protocol

import yaml
from pydantic import JsonValue

from kiln_ai.datamodel.synthetic_world import (
    LOCAL_FILES_LAUNCHER,
    SyntheticInstance,
    SyntheticWorld,
)
from kiln_ai.run_context import generate_synthetic_instance_id
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

ACTIVE_MARKER = ".active"
ACTIVE_GRACE_SECONDS = 60 * 60
"""How long a fresh `.active` marker protects an instance from pruning.

The marker is touched at launch and removed at finalize. A concurrent runner in the
same process (or a crashed one) is the only reason an unreferenced instance would still
be live; an hour covers a long generation."""

FIXTURES_DIRNAME = "fixtures"
FIXTURE_MANIFEST = "fixture.yaml"
"""Optional file inside a local fixture directory: a mapping of facts the launcher
reports on the instance (`frozen_time` in ISO 8601, and anything else the world's tools
want). It is not copied into the instance."""

_CACHE_DIRNAME = "synthetic_instances"


class SyntheticWorldLauncher(Protocol):
    async def content_version(
        self, world: SyntheticWorld, config: dict[str, JsonValue]
    ) -> str | None:
        """Identity of the content a launch of *config* would start from, without
        launching. Folded into the trace fingerprint: change it and traces regenerate."""
        ...

    async def launch(
        self, world: SyntheticWorld, config: dict[str, JsonValue]
    ) -> SyntheticInstance: ...

    async def finalize(self, instance: SyntheticInstance) -> SyntheticInstance: ...

    async def release(self, instance: SyntheticInstance) -> None: ...

    async def prune(self, live: Iterable[SyntheticInstance]) -> None: ...


class UnknownLauncherError(ValueError):
    pass


_LAUNCHERS: dict[str, Callable[[], SyntheticWorldLauncher]] = {}


def register_launcher(name: str, factory: Callable[[], SyntheticWorldLauncher]) -> None:
    _LAUNCHERS[name] = factory


def launcher_for_world(world: SyntheticWorld) -> SyntheticWorldLauncher:
    factory = _LAUNCHERS.get(world.launcher)
    if factory is None:
        raise UnknownLauncherError(
            f"Synthetic world '{world.name}' names launcher '{world.launcher}', "
            f"which is not registered (known: {sorted(_LAUNCHERS)})"
        )
    return factory()


def default_cache_root() -> Path:
    return Path(Config.settings_dir()) / "cache" / _CACHE_DIRNAME


def local_fixtures_dir(world: SyntheticWorld) -> Path:
    return world.world_dir() / FIXTURES_DIRNAME


def local_fixture_dir(world: SyntheticWorld, fixture_id: str) -> Path:
    """A fixture directory under the world, refusing anything that escapes it."""
    if not fixture_id or not fixture_id.strip():
        raise ValueError("fixture_id cannot be empty")
    base = local_fixtures_dir(world)
    target = base / fixture_id
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        raise ValueError(
            "fixture_id must not escape the world's fixtures directory"
        ) from None
    if target.resolve() == base.resolve():
        raise ValueError("fixture_id must name a directory inside fixtures/")
    return target


def read_fixture_manifest(fixture_dir: Path) -> dict[str, JsonValue]:
    manifest = fixture_dir / FIXTURE_MANIFEST
    if not manifest.is_file():
        return {}
    loaded = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{manifest} must hold a mapping")
    return {str(k): _jsonable(v) for k, v in loaded.items()}


def _jsonable(value: object) -> JsonValue:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value  # type: ignore[return-value]


class LocalFilesLauncher:
    """Fixtures are directories under the world; an instance is a copy under the Kiln cache.

    Launch config: `{"fixture_id": "<directory name>"}`, plus any keys the world's
    tools want echoed back (a `frozen_time` override, for one). Reported metadata is the
    fixture's manifest with the config's scalar keys layered on top, plus `fixture_id`.
    """

    def __init__(
        self, cache_root: Path | None = None, max_bytes: int | None = None
    ) -> None:
        self._root = cache_root or default_cache_root()
        if max_bytes is None:
            max_gb = float(Config.shared().synthetic_instance_cache_max_gb)
            max_bytes = int(max_gb * 1024**3)
        self._max_bytes = max_bytes

    @property
    def cache_root(self) -> Path:
        return self._root

    def list_fixtures(self, world: SyntheticWorld) -> list[str]:
        base = local_fixtures_dir(world)
        if not base.is_dir():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir())

    async def content_version(
        self, world: SyntheticWorld, config: dict[str, JsonValue]
    ) -> str | None:
        """The world's declared version plus a digest of the fixture's bytes, so a
        regenerated fixture never matches a trace made from the old one. Digests are
        cached per directory signature (paths, sizes, mtimes), so this is a stat walk
        per call, not a read."""
        fixture_id = config.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id:
            return world.content_version
        source = local_fixture_dir(world, fixture_id)
        if not source.is_dir():
            return world.content_version
        digest = await asyncio.to_thread(_cached_tree_digest, source)
        return _compose_content_version(world.content_version, digest)

    async def launch(
        self, world: SyntheticWorld, config: dict[str, JsonValue]
    ) -> SyntheticInstance:
        if world.id is None:
            raise ValueError("World must be saved before launching an instance")
        fixture_id = config.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id:
            raise ValueError(
                f"World '{world.name}' uses the local files launcher, which needs a "
                f"'fixture_id' string in the launch config; got {config!r}"
            )
        source = local_fixture_dir(world, fixture_id)
        if not source.is_dir():
            raise ValueError(
                f"Fixture '{fixture_id}' not found in world '{world.name}' at {source}"
            )
        if not any(
            p.is_file() and p.name != FIXTURE_MANIFEST for p in source.rglob("*")
        ):
            raise ValueError(f"Fixture '{fixture_id}' at {source} holds no data files")

        metadata: dict[str, JsonValue] = {"fixture_id": fixture_id}
        metadata.update(read_fixture_manifest(source))
        metadata.update(
            {k: v for k, v in config.items() if isinstance(v, (str, int, float, bool))}
        )

        instance_id = generate_synthetic_instance_id()
        dest = self._root / instance_id
        lib_dir = world.lib_dir()
        content_version = await self.content_version(world, config)

        def _copy() -> None:
            self._root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                source, dest, ignore=shutil.ignore_patterns(FIXTURE_MANIFEST)
            )
            (dest / ACTIVE_MARKER).touch()

        await asyncio.to_thread(_copy)
        return SyntheticInstance(
            instance_id=instance_id,
            world_id=world.id,
            config=config,
            path=str(dest),
            source_path=str(source),
            world_lib_path=str(lib_dir) if lib_dir.is_dir() else None,
            metadata=metadata,
            content_version=content_version,
        )

    async def finalize(self, instance: SyntheticInstance) -> SyntheticInstance:
        """Mark the copy `unchanged` if the run left it byte-identical to its source.

        Does not release the copy: grading is about to read it, and another job
        grading the same trace (a second judge that reused this generation) may be
        too. The runner releases unchanged copies once every job has finished, and
        `prune` catches the rest. Files are opaque here, so no `changes` are recorded.
        """
        if instance.unchanged or not instance.path or not instance.source_path:
            return instance
        dest = Path(instance.path)
        source = Path(instance.source_path)
        if not dest.is_dir():
            return instance

        def _compare_and_settle() -> bool:
            marker = dest / ACTIVE_MARKER
            if marker.exists():
                marker.unlink()
            return _tree_digest(dest) == _tree_digest(source)

        unchanged = await asyncio.to_thread(_compare_and_settle)
        if unchanged:
            return instance.model_copy(update={"unchanged": True})
        return instance

    async def release(self, instance: SyntheticInstance) -> None:
        if instance.path and Path(instance.path).is_dir():
            await asyncio.to_thread(shutil.rmtree, Path(instance.path), True)

    async def prune(self, live: Iterable[SyntheticInstance]) -> None:
        """Delete instance dirs no surviving trace references, then enforce the size cap.

        Never touches a directory whose `.active` marker is fresh: that is an instance
        another runner is still generating against.
        """
        live_paths = {
            Path(i.path).resolve() for i in live if not i.unchanged and i.path
        }
        await asyncio.to_thread(self._prune_sync, live_paths)

    def _prune_sync(self, live_paths: set[Path]) -> None:
        if not self._root.is_dir():
            return
        now = time.time()
        candidates: list[tuple[Path, float, int]] = []
        for entry in self._root.iterdir():
            if not entry.is_dir():
                continue
            marker = entry / ACTIVE_MARKER
            if marker.exists() and now - marker.stat().st_mtime < ACTIVE_GRACE_SECONDS:
                continue
            if entry.resolve() not in live_paths:
                logger.info("Pruning unreferenced synthetic instance %s", entry.name)
                shutil.rmtree(entry, ignore_errors=True)
                continue
            candidates.append((entry, entry.stat().st_mtime, _dir_size(entry)))

        total = sum(size for _, _, size in candidates)
        if total <= self._max_bytes:
            return
        for entry, _, size in sorted(candidates, key=lambda c: c[1]):
            if total <= self._max_bytes:
                break
            logger.info(
                "Evicting synthetic instance %s (%d bytes) to stay under the cache cap",
                entry.name,
                size,
            )
            shutil.rmtree(entry, ignore_errors=True)
            total -= size


register_launcher(LOCAL_FILES_LAUNCHER, LocalFilesLauncher)


def _compose_content_version(declared: str | None, fixture_digest: str) -> str:
    payload = f"{declared or ''}|{fixture_digest}"
    return "local:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


_DIGEST_CACHE: dict[Path, tuple[tuple[tuple[str, int, int], ...], str]] = {}


def _tree_signature(root: Path) -> tuple[tuple[str, int, int], ...]:
    entries: list[tuple[str, int, int]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel in (ACTIVE_MARKER, FIXTURE_MANIFEST):
            continue
        st = path.stat()
        entries.append((rel, st.st_size, st.st_mtime_ns))
    return tuple(entries)


def _cached_tree_digest(root: Path) -> str:
    key = root.resolve()
    signature = _tree_signature(key)
    cached = _DIGEST_CACHE.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    digest = _tree_digest(key)
    _DIGEST_CACHE[key] = (signature, digest)
    return digest


def _tree_digest(root: Path) -> str:
    """A content hash of every file under *root*, by relative path; ignores markers and
    the fixture manifest so a source and its copy compare equal."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel in (ACTIVE_MARKER, FIXTURE_MANIFEST):
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _dir_size(root: Path) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                continue
    return total
