"""
A simple cache for our datamodel.

Works at the file level, caching the pydantic model based on the file path.

Keeping this really simple. Our goal is to really be "disk-backed" data model, so using disk primitives.

 - Use disk mtime to determine if the cached model is stale.
 - Still using glob for iterating over projects, just caching at the file level
 - Use path as the cache key
 - Cache always populated from a disk read, so we know it reflects what's on disk. Even if we had a memory-constructed version, we don't cache that.
 - Cache the parsed model, not the raw file contents. Parsing and validating is what's expensive. >99% speedup when measured.
 - Bounded by the total size of the cached files, evicting the least recently used entries. A parsed model
   takes about 3x its file size in memory, and a large task can hold gigabytes of runs, so an unbounded
   cache grows until the process runs out of memory.
"""

import os
import sys
import threading
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple, Type, TypeVar

if TYPE_CHECKING:
    from kiln_ai.datamodel.basemodel import KilnBaseModel

    T = TypeVar("T", bound="KilnBaseModel")
else:
    T = TypeVar("T")

DEFAULT_MAX_CACHED_FILE_BYTES = 256 * 1024 * 1024


class ModelCache:
    _shared_instance = None

    def __init__(self, max_bytes: int = DEFAULT_MAX_CACHED_FILE_BYTES):
        """
        Args:
            max_bytes: Limit on the summed on-disk size of the cached files. Memory use is a
                few times this, since parsed models are larger than their JSON.
        """
        # Each entry holds the model, the file's mtime when read, and the file's size in bytes.
        # Ordered from least to most recently used.
        self.model_cache: OrderedDict[Path, Tuple[KilnBaseModel, int, int]] = (
            OrderedDict()
        )
        self.max_bytes = max_bytes
        self._total_bytes = 0
        # Used from the event loop and from worker threads at once. A threading lock, not an
        # asyncio one: it is never held across an await.
        self._lock = threading.Lock()
        self._enabled = self._check_timestamp_granularity()
        if not self._enabled:
            warnings.warn(
                "File system does not support fine-grained timestamps. "
                "Model caching has been disabled to ensure consistency."
            )

    @classmethod
    def shared(cls):
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    def _is_cache_valid(self, path: Path, cached_mtime_ns: int) -> bool:
        try:
            current_mtime_ns = path.stat().st_mtime_ns
        except Exception:
            return False
        return cached_mtime_ns == current_mtime_ns

    def _get_model(self, path: Path, model_type: Type[T]) -> Optional[T]:
        with self._lock:
            entry = self.model_cache.get(path)
            if entry is None:
                return None
            self.model_cache.move_to_end(path)
        model, cached_mtime_ns, _ = entry
        if not self._is_cache_valid(path, cached_mtime_ns):
            self.invalidate(path)
            return None

        if not isinstance(model, model_type):
            self.invalidate(path)
            raise ValueError(f"Model at {path} is not of type {model_type.__name__}")
        return model

    def get_model(
        self, path: Path, model_type: Type[T], readonly: bool = False
    ) -> Optional[T]:
        # We return a copy by default, so in-memory edits don't impact the cache until they are saved
        # Benchmark shows about 2x slower, but much more foolproof
        model = self._get_model(path, model_type)
        if model:
            if readonly:
                return model
            else:
                return model.mutable_copy()
        return None

    def get_model_id(
        self, path: Path, model_type: Type["KilnBaseModel"]
    ) -> Optional[str]:
        model = self._get_model(path, model_type)
        if model and hasattr(model, "id"):
            id = model.id  # type: ignore
            if isinstance(id, str):
                return id
        return None

    def set_model(
        self, path: Path, model: "KilnBaseModel", mtime_ns: int, size_bytes: int
    ):
        """Cache a readonly model read from `path`.

        `size_bytes` is the size of the file it was parsed from, and counts toward `max_bytes`.
        A file larger than `max_bytes` is not cached.
        """
        # disable caching if the filesystem doesn't support fine-grained timestamps
        if not self._enabled:
            return

        if not model._readonly:
            raise RuntimeError(
                "Mutable models are not allowed to be cached. Model should be readonly."
            )
        with self._lock:
            self._remove(path)
            if size_bytes > self.max_bytes:
                return
            self.model_cache[path] = (model, mtime_ns, size_bytes)
            self._total_bytes += size_bytes
            while self._total_bytes > self.max_bytes:
                _, (_, _, evicted_size) = self.model_cache.popitem(last=False)
                self._total_bytes -= evicted_size

    def invalidate(self, path: Path):
        with self._lock:
            self._remove(path)

    def clear(self):
        with self._lock:
            self.model_cache.clear()
            self._total_bytes = 0

    @property
    def total_bytes(self) -> int:
        """The summed on-disk size of the files currently cached."""
        return self._total_bytes

    def _remove(self, path: Path):
        # Callers hold self._lock.
        entry = self.model_cache.pop(path, None)
        if entry is not None:
            self._total_bytes -= entry[2]

    def _check_timestamp_granularity(self) -> bool:
        """Check if filesystem supports fine-grained timestamps (microseconds or better)."""

        # MacOS and Windows support fine-grained timestamps
        if sys.platform in ["darwin", "win32"]:
            return True

        # Linux supports fine-grained timestamps SOMETIMES. ext4 should work.
        try:
            # Get filesystem stats for the current directory
            stats = os.statvfs(Path(__file__).parent)

            # f_timespec was added in Linux 5.6 (2020)
            # Returns nanoseconds precision as a power of 10
            # e.g., 1 = decisecond, 2 = centisecond, 3 = millisecond, etc.
            timespec = getattr(stats, "f_timespec", 0)

            # Consider microsecond precision (6) or better as "fine-grained"
            return timespec >= 6
        except (AttributeError, OSError):
            # If f_timespec isn't available or other errors occur,
            # assume poor granularity to be safe
            return False
