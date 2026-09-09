"""Instance providers: where a fixture's copy lives for the duration of an eval run.

`LocalCopyProvider` is V1: a directory copy under Kiln's cache. The `Protocol` is the
seam for a hosted provider later; nothing else in Kiln knows how an instance is made.

Retention follows the trace, not a clock. The trace index reuses one generation across
every judge, indefinitely, so an instance must stay readable as long as the trace that
records it exists. Storage stays bounded because most runs leave the copy byte-identical
to the fixture (they only read), and those copies are dropped at `finalize`; a size cap
evicts the rest oldest-first.
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
from typing import Iterable, Protocol

from kiln_ai.datamodel.synthetic_world import (
    SyntheticFixture,
    SyntheticInstance,
    SyntheticWorld,
)
from kiln_ai.run_context import generate_synthetic_instance_id
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

ACTIVE_MARKER = ".active"
ACTIVE_GRACE_SECONDS = 60 * 60
"""How long a fresh `.active` marker protects an instance from pruning.

The marker is touched at create and removed at finalize. A concurrent runner in the
same process (or a crashed one) is the only reason an unreferenced instance would still
be live; an hour covers a long generation."""

_CACHE_DIRNAME = "synthetic_instances"


class SyntheticInstanceProvider(Protocol):
    async def create(
        self,
        world: SyntheticWorld,
        fixture: SyntheticFixture,
        *,
        frozen_time: datetime | None,
    ) -> SyntheticInstance: ...

    async def finalize(self, instance: SyntheticInstance) -> SyntheticInstance: ...

    async def destroy(self, instance: SyntheticInstance) -> None: ...

    async def prune(self, live: Iterable[SyntheticInstance]) -> None: ...


def default_cache_root() -> Path:
    return Path(Config.settings_dir()) / "cache" / _CACHE_DIRNAME


class LocalCopyProvider:
    """Copies a fixture's data directory per instance under the Kiln cache."""

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

    async def create(
        self,
        world: SyntheticWorld,
        fixture: SyntheticFixture,
        *,
        frozen_time: datetime | None,
    ) -> SyntheticInstance:
        if world.id is None or fixture.id is None:
            raise ValueError(
                "World and fixture must be saved before creating an instance"
            )
        data_dir = fixture.require_data_dir()
        instance_id = generate_synthetic_instance_id()
        dest = self._root / instance_id
        lib_dir = world.lib_dir()

        def _copy() -> None:
            self._root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(data_dir, dest)
            (dest / ACTIVE_MARKER).touch()

        await asyncio.to_thread(_copy)
        return SyntheticInstance(
            instance_id=instance_id,
            world_id=world.id,
            fixture_id=fixture.id,
            path=str(dest),
            fixture_data_path=str(data_dir),
            world_lib_path=str(lib_dir) if lib_dir.is_dir() else None,
            frozen_time=frozen_time,
            framework_content_hash=world.framework_content_hash,
        )

    async def finalize(self, instance: SyntheticInstance) -> SyntheticInstance:
        """Drop the copy if the run left it byte-identical to the fixture."""
        if instance.unchanged:
            return instance
        dest = Path(instance.path)
        if not dest.is_dir():
            return instance

        def _compare_and_settle() -> bool:
            marker = dest / ACTIVE_MARKER
            if marker.exists():
                marker.unlink()
            if _tree_digest(dest) == _tree_digest(Path(instance.fixture_data_path)):
                shutil.rmtree(dest, ignore_errors=True)
                return True
            return False

        unchanged = await asyncio.to_thread(_compare_and_settle)
        if unchanged:
            return instance.model_copy(update={"unchanged": True})
        return instance

    async def destroy(self, instance: SyntheticInstance) -> None:
        dest = Path(instance.path)
        if dest.is_dir():
            await asyncio.to_thread(shutil.rmtree, dest, True)

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


def _tree_digest(root: Path) -> str:
    """A content hash of every file under *root*, by relative path; ignores the marker."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel == ACTIVE_MARKER:
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
