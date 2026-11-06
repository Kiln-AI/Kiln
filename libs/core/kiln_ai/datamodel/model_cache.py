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
- Records of a class with large fields (see `lazy_fields`) are kept in two parts: the
  record without its large values, and the large values, which code reads back through
  the record and which the cache can drop on their own.
- Its memory is bounded by a budget of min(2 GiB, 20% of physical RAM). Each record counts
  an estimate based on its file size, split between its two parts. When an add takes the
  total over budget, the cache drops large values, least recently used first, then whole
  records, least recently used first, until the total is at 90% of the budget. A record
  larger than the whole budget is returned to its caller but not kept; so are large
  values larger than the budget.
"""

import logging
import os
import sys
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Type, TypeVar

if TYPE_CHECKING:
    from kiln_ai.datamodel.basemodel import KilnBaseModel
    from kiln_ai.datamodel.lazy_fields import DetachedValues, FieldPath

    T = TypeVar("T", bound="KilnBaseModel")
else:
    T = TypeVar("T")

logger = logging.getLogger(__name__)

# A parsed record takes 1.15-1.5x its file size in memory, measured on task runs.
MEMORY_FACTOR = 1.3
# The least a record without its large values counts, whatever its file size says.
MIN_RECORD_BYTES = 1024
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
    records_with_large_values: int
    total_bytes: int
    budget_bytes: int


@dataclass(frozen=True, slots=True)
class _Eviction:
    large_values: int
    records: int
    stats: CacheStats

    def log(self) -> None:
        logger.debug(
            "Evicted the large values of %d cached records and %d whole records; "
            "%d records (%d with large values) and %d of %d budget bytes remain",
            self.large_values,
            self.records,
            self.stats.records,
            self.stats.records_with_large_values,
            self.stats.total_bytes,
            self.stats.budget_bytes,
        )


@dataclass(slots=True)
class _Entry:
    model: "KilnBaseModel"
    identity: FileIdentity
    normal_bytes: int
    large_bytes: int = 0
    # The `DetachedValues.owner` of the record, when it has large values; None otherwise.
    large_owner: object | None = None
    # None when the record has no large values, or they were evicted.
    large_values: "Mapping[FieldPath, Any] | None" = None


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
        # The entries whose large values are in memory, least recently used first.
        self._loaded: OrderedDict[Path, None] = OrderedDict()
        # normal_bytes of every entry, plus large_bytes of the entries in _loaded.
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
        self,
        path: Path,
        model: "KilnBaseModel",
        identity: FileIdentity,
        detached: "DetachedValues | None" = None,
    ) -> None:
        """Cache a readonly record parsed from `path`.

        `identity` must describe the exact bytes the record was parsed from, so take
        it from the open file descriptor (`os.fstat`), not from a later stat.
        `detached` holds the large values `detach_large_values` took out of `model`;
        the cache keeps them apart and evicts them first.
        """
        if not self._enabled:
            return

        if not model._readonly:
            raise RuntimeError(
                "Mutable models are not allowed to be cached. Model should be readonly."
            )
        estimated_bytes = int(identity.size * MEMORY_FACTOR)
        if detached is not None and detached.values:
            entry = _Entry(
                model=model,
                identity=identity,
                normal_bytes=max(estimated_bytes - detached.size, MIN_RECORD_BYTES),
                large_bytes=detached.size,
                large_owner=detached.owner,
            )
        else:
            entry = _Entry(model=model, identity=identity, normal_bytes=estimated_bytes)
        with self._lock:
            self._remove(path)
            if entry.normal_bytes > self._budget_bytes:
                return
            self._records[path] = entry
            self._total_bytes += entry.normal_bytes
            if (
                detached is not None
                and entry.large_owner is not None
                and entry.large_bytes <= self._budget_bytes
            ):
                self._load_large_values(path, entry, detached.values)
            if self._total_bytes <= self._budget_bytes:
                return
            eviction = self._evict()
        eviction.log()

    def _load_large_values(
        self, path: Path, entry: _Entry, values: "Mapping[FieldPath, Any]"
    ) -> None:
        """Call with the lock held, for an entry in `_records` without loaded values."""
        entry.large_values = values
        self._loaded[path] = None
        self._total_bytes += entry.large_bytes

    def _drop_large_values(self, path: Path) -> None:
        """Call with the lock held, for a path in `_loaded`."""
        del self._loaded[path]
        entry = self._records[path]
        entry.large_values = None
        self._total_bytes -= entry.large_bytes

    def _evict(self) -> _Eviction:
        """Drop large values, then whole records, least recently used first, down to the
        eviction target. Returns what was dropped.

        Call with the lock held, and log the result after releasing it. Code already
        holding an evicted record or value keeps it: only the cache's reference goes.
        """
        target = int(self._budget_bytes * EVICTION_TARGET_FRACTION)
        evicted_large_values = 0
        while self._total_bytes > target and self._loaded:
            self._drop_large_values(next(iter(self._loaded)))
            evicted_large_values += 1
        evicted_records = 0
        while self._total_bytes > target and self._records:
            _, entry = self._records.popitem(last=False)
            self._total_bytes -= entry.normal_bytes
            evicted_records += 1
        return _Eviction(evicted_large_values, evicted_records, self.stats())

    def _remove(self, path: Path) -> None:
        """Call with the lock held."""
        entry = self._records.pop(path, None)
        if entry is None:
            return
        self._total_bytes -= entry.normal_bytes
        if path in self._loaded:
            del self._loaded[path]
            self._total_bytes -= entry.large_bytes

    def invalidate(self, path: Path) -> None:
        with self._lock:
            self._remove(path)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._loaded.clear()
            self._total_bytes = 0

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                records=len(self._records),
                records_with_large_values=len(self._loaded),
                total_bytes=self._total_bytes,
                budget_bytes=self._budget_bytes,
            )

    def large_values_for(
        self, path: Path, owner: object
    ) -> "Mapping[FieldPath, Any] | None":
        """The detached record's large values, if they're in memory.

        Marks the record and its values recently used. Code that gets the values keeps
        a valid mapping even if they're evicted afterwards.
        """
        with self._lock:
            entry = self._records.get(path)
            if (
                entry is None
                or entry.large_owner is not owner
                or entry.large_values is None
            ):
                return None
            self._records.move_to_end(path)
            self._loaded.move_to_end(path)
            return entry.large_values

    def store_restored_values(
        self,
        path: Path,
        owner: object,
        identity: FileIdentity,
        values: "Mapping[FieldPath, Any]",
        size: int,
    ) -> bool:
        """Keep large values re-read from the record's file, counted against the budget.

        Returns False, keeping nothing, when this cache no longer holds the record for
        `path`, when `identity` isn't the one the record was cached with, or when `size`
        is over the whole budget. When the values are already in memory (another thread
        restored them first), keeps those and returns True.
        """
        with self._lock:
            entry = self._records.get(path)
            if (
                entry is None
                or entry.large_owner is not owner
                or identity != entry.identity
                or size > self._budget_bytes
            ):
                return False
            self._records.move_to_end(path)
            if entry.large_values is not None:
                self._loaded.move_to_end(path)
                return True
            entry.large_bytes = size
            self._load_large_values(path, entry, values)
            if self._total_bytes <= self._budget_bytes:
                return True
            eviction = self._evict()
        eviction.log()
        return True

    def is_current_entry(self, path: Path, owner: object) -> bool:
        """Whether this cache still holds the detached record `owner` stands for."""
        with self._lock:
            entry = self._records.get(path)
            return entry is not None and entry.large_owner is owner

    def drop_entry(self, path: Path, owner: object) -> None:
        """Remove the entry for `path` if it holds the detached record `owner` stands for."""
        with self._lock:
            if self.is_current_entry(path, owner):
                self._remove(path)


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
