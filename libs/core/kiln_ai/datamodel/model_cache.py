"""
A process-wide cache of parsed, validated datamodel records, keyed by file path.

- Off by default. Hosts that want it (the desktop app, kiln_server, kiln_mcp) turn it on
  with `set_model_cache_enabled(True)`, and library users can do the same.
- Only readonly loads add to it, always straight from a disk read, so each cached record
  matches the file it was parsed from. A record built in memory is never cached.
- Before serving a record, the cache stats its file. If the modified time, size or file id
  changed, or the file is gone, the entry is dropped and the caller reloads the file.
- It caches the parsed model, not the raw file contents: parsing and validating is what's
  expensive, and a cache hit is over 99% faster than a load.
- Its memory is bounded by a budget of min(2 GiB, 20% of physical RAM). Each record counts
  an estimate based on its file size. When an add takes the total over budget, the least
  recently used records are dropped until the total is at 90% of the budget. A record
  larger than the whole budget is returned to its caller but not kept.
"""

import logging
import os
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Type, TypeVar

if TYPE_CHECKING:
    from kiln_ai.datamodel.basemodel import KilnBaseModel

    T = TypeVar("T", bound="KilnBaseModel")
else:
    T = TypeVar("T")

logger = logging.getLogger(__name__)

# A parsed record takes 1.15-1.5x its file size in memory, measured on task runs.
MEMORY_FACTOR = 1.3
MAX_BUDGET_BYTES = 2 * 1024**3
RAM_FRACTION = 0.2
FALLBACK_BUDGET_BYTES = 1 * 1024**3
EVICTION_TARGET_FRACTION = 0.9


@dataclass(frozen=True, slots=True)
class FileIdentity:
    """The facts about a file that tell the cache whether a cached record is stale."""

    mtime_ns: int
    size: int
    inode: int

    @classmethod
    def from_stat(cls, st: os.stat_result) -> "FileIdentity":
        return cls(mtime_ns=st.st_mtime_ns, size=st.st_size, inode=st.st_ino)

    @classmethod
    def from_path(cls, path: Path) -> "FileIdentity | None":
        """The file's current identity, or None if it can't be stat'ed."""
        try:
            return cls.from_stat(path.stat())
        except (OSError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class CacheStats:
    """The cache's accounting at one moment. Byte counts are estimates from file sizes."""

    records: int
    total_bytes: int
    budget_bytes: int


@dataclass(frozen=True, slots=True)
class _Entry:
    model: "KilnBaseModel"
    identity: FileIdentity
    estimated_bytes: int


class ModelCache:
    _shared_instance: "ModelCache | None" = None

    def __init__(
        self, *, enabled: bool = False, budget_bytes: int | None = None
    ) -> None:
        """`budget_bytes` defaults to `default_cache_budget_bytes()`."""
        self._enabled = enabled
        self._budget_bytes = (
            default_cache_budget_bytes() if budget_bytes is None else budget_bytes
        )
        # Least recently used first. Guarded by _lock, which is never held during file I/O.
        self._records: OrderedDict[Path, _Entry] = OrderedDict()
        self._total_bytes = 0
        self._lock = threading.RLock()

    @classmethod
    def shared(cls) -> "ModelCache":
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        """Turn caching on or off. Turning it off also drops every cached record."""
        self._enabled = value
        if not value:
            self.clear()

    def _get_model(self, path: Path, model_type: Type[T]) -> Optional[T]:
        if not self._enabled:
            return None
        with self._lock:
            entry = self._records.get(path)
        if entry is None:
            return None
        identity = FileIdentity.from_path(path)

        with self._lock:
            # Another thread removed or replaced the entry during the stat. A
            # replacement is a newer load, so leave it for the next read to check.
            if self._records.get(path) is not entry:
                return None
            if identity != entry.identity:
                self._remove(path)
                return None
            if not isinstance(entry.model, model_type):
                self._remove(path)
                raise ValueError(
                    f"Model at {path} is not of type {model_type.__name__}"
                )
            self._records.move_to_end(path)
            return entry.model

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
        self, path: Path, model: "KilnBaseModel", identity: FileIdentity
    ) -> None:
        """Cache a readonly record parsed from `path`.

        `identity` must describe the exact bytes the record was parsed from, so take
        it from the open file descriptor (`os.fstat`), not from a later stat.
        """
        if not self._enabled:
            return

        if not model._readonly:
            raise RuntimeError(
                "Mutable models are not allowed to be cached. Model should be readonly."
            )
        entry = _Entry(
            model=model,
            identity=identity,
            estimated_bytes=int(identity.size * MEMORY_FACTOR),
        )
        with self._lock:
            self._remove(path)
            if entry.estimated_bytes > self._budget_bytes:
                return
            self._records[path] = entry
            self._total_bytes += entry.estimated_bytes
            if self._total_bytes <= self._budget_bytes:
                return
            evicted = self._evict()
            stats = self.stats()
        logger.debug(
            "Evicted %d cached records; %d records and %d of %d budget bytes remain",
            evicted,
            stats.records,
            stats.total_bytes,
            stats.budget_bytes,
        )

    def _evict(self) -> int:
        """Drop least recently used records down to the eviction target; return how many.

        Call with the lock held. Code already holding an evicted record keeps it: only
        the cache's reference goes.
        """
        target = int(self._budget_bytes * EVICTION_TARGET_FRACTION)
        evicted = 0
        while self._total_bytes > target and self._records:
            _, entry = self._records.popitem(last=False)
            self._total_bytes -= entry.estimated_bytes
            evicted += 1
        return evicted

    def _remove(self, path: Path) -> None:
        """Call with the lock held."""
        entry = self._records.pop(path, None)
        if entry is not None:
            self._total_bytes -= entry.estimated_bytes

    def invalidate(self, path: Path) -> None:
        with self._lock:
            self._remove(path)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._total_bytes = 0

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                records=len(self._records),
                total_bytes=self._total_bytes,
                budget_bytes=self._budget_bytes,
            )


def set_model_cache_enabled(value: bool) -> None:
    """Turn the process-wide datamodel cache on or off.

    Off by default in the library. With it on, readonly loads
    (`load_from_file(..., readonly=True)`, `task.runs(readonly=True)`, ...) keep each
    parsed record in memory and serve it again until its file changes, within a memory
    budget of min(2 GiB, 20% of physical RAM). Turning it off drops every cached record.
    """
    ModelCache.shared().set_enabled(value)


def model_cache_enabled() -> bool:
    """Whether the process-wide datamodel cache is on."""
    return ModelCache.shared().enabled


def default_cache_budget_bytes() -> int:
    """min(2 GiB, 20% of physical RAM), or 1 GiB if physical RAM can't be read."""
    ram = physical_memory_bytes()
    if ram is None:
        return FALLBACK_BUDGET_BYTES
    return min(MAX_BUDGET_BYTES, int(ram * RAM_FRACTION))


def physical_memory_bytes() -> int | None:
    """The machine's total physical RAM, or None if the platform doesn't report it."""
    try:
        if sys.platform == "win32":
            ram = _windows_physical_memory_bytes()
        else:
            page_size = os.sysconf("SC_PAGE_SIZE")
            pages = os.sysconf("SC_PHYS_PAGES")
            # sysconf returns -1 for a value the system can't determine.
            ram = page_size * pages if page_size > 0 and pages > 0 else 0
    except Exception:
        return None
    return ram if ram > 0 else None


# Defined only on Windows: ctypes.windll exists nowhere else.
if sys.platform == "win32":
    import ctypes

    class _MemoryStatusEx(ctypes.Structure):
        """Win32 MEMORYSTATUSEX."""

        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    def _windows_physical_memory_bytes() -> int:
        """Total physical RAM, or 0 if the call fails."""
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return 0
        return int(status.ullTotalPhys)
