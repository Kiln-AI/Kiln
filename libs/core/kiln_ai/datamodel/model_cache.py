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

MEMORY_FACTOR = 1.3
"""Estimated in-memory bytes per file byte of a parsed record.

Task runs of 10 to 100 turns measure about 1.15 to 1.4.
"""

MIN_RECORD_BYTES = 8 * 1024
"""The least a record with large values counts for its other fields, whatever its file
size says.

Measured without their large values, a cached task run takes about 9 KiB, an eval run
about 6 KiB and a chunk embeddings record about 3 KiB, almost all of it fixed overhead.

Records without large values count `MEMORY_FACTOR` times their file size, with no floor.
"""

MAX_BUDGET_BYTES = 2 * 1024**3
"""The largest memory budget, however much RAM the machine has."""

RAM_FRACTION = 0.2
"""The share of physical RAM the budget takes, up to `MAX_BUDGET_BYTES`."""

FALLBACK_BUDGET_BYTES = 1 * 1024**3
"""The budget when the platform doesn't report its physical RAM."""

EVICTION_TARGET_FRACTION = 0.9
"""An add that takes the total over budget evicts down to this share of the budget, so
the adds after it don't each evict again."""


@dataclass(frozen=True, slots=True)
class FileIdentity:
    """The facts about a file that tell the cache whether a cached record is stale."""

    mtime_ns: int
    size: int
    inode: int

    @classmethod
    def from_stat(cls, st: os.stat_result) -> "FileIdentity":
        """The identity a stat result describes."""
        return cls(mtime_ns=st.st_mtime_ns, size=st.st_size, inode=st.st_ino)

    @classmethod
    def from_path(cls, path: Path) -> "FileIdentity | None":
        """The file's current identity, or None if it can't be stat'ed."""
        st = _stat(path)
        return None if st is None else cls.from_stat(st)

    def matches(self, st: os.stat_result) -> bool:
        """Whether `st` describes the file this identity was taken from, unchanged.

        Equal to `FileIdentity.from_stat(st) == self`, without building an identity on
        every cache hit.
        """
        return (
            st.st_mtime_ns == self.mtime_ns
            and st.st_size == self.size
            and st.st_ino == self.inode
        )


def _stat(path: Path) -> os.stat_result | None:
    try:
        return os.stat(path)
    except (OSError, ValueError):
        return None


def _cache_key(path: Path) -> str:
    """The key for `path` in the cache's dicts: `os.path.normcase(path)`, which folds
    case on Windows the way `Path` equality does."""
    # str, not Path: a warm list load does several lookups per record, and str keys
    # hash and compare in C where Path keys do both in Python.
    return os.path.normcase(path)


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
    """Parsed readonly records, keyed by file path, within a memory budget.

    The process shares one instance, `ModelCache.shared()`, which starts off;
    `set_model_cache_enabled` turns it on. `KilnBaseModel` fills and reads it: readonly
    loads add records, saves and deletes invalidate them, and a hit is served only while
    its file is unchanged. Constructing a `ModelCache` gives a separate cache, for
    example one with a small budget.

    Safe to use from several threads. The lock that guards the bookkeeping is never held
    during file I/O or while copying a record.
    """

    _shared_instance: "ModelCache | None" = None

    def __init__(
        self, *, enabled: bool = False, budget_bytes: int | None = None
    ) -> None:
        """`budget_bytes` defaults to `default_cache_budget_bytes()`."""
        self._enabled = enabled
        self._budget_bytes = (
            default_cache_budget_bytes() if budget_bytes is None else budget_bytes
        )
        # Keyed by _cache_key, least recently used first. Guarded by _lock.
        self._records: OrderedDict[str, _Entry] = OrderedDict()
        # The keys of the entries whose large values are in memory, least recently used
        # first.
        self._loaded: OrderedDict[str, None] = OrderedDict()
        # normal_bytes of every entry, plus large_bytes of the entries in _loaded.
        self._total_bytes = 0
        self._lock = threading.RLock()

    @classmethod
    def shared(cls) -> "ModelCache":
        """The process-wide cache that datamodel loads use. Off until
        `set_model_cache_enabled(True)`."""
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    @property
    def enabled(self) -> bool:
        """Whether this cache stores and serves records."""
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        """Turn caching on or off. Turning it off also drops every cached record."""
        self._enabled = value
        if not value:
            self.clear()

    def _get_model(self, path: Path, model_type: Type[T]) -> Optional[T]:
        if not self._enabled:
            return None
        key = _cache_key(path)
        with self._lock:
            entry = self._records.get(key)
        if entry is None:
            return None
        st = _stat(path)

        with self._lock:
            # Another thread removed or replaced the entry during the stat. A
            # replacement is a newer load, so leave it for the next read to check.
            if self._records.get(key) is not entry:
                return None
            if st is None or not entry.identity.matches(st):
                self._remove(key)
                return None
            if not isinstance(entry.model, model_type):
                self._remove(key)
                raise ValueError(
                    f"Model at {path} is not of type {model_type.__name__}"
                )
            self._records.move_to_end(key)
            return entry.model

    def get_model(
        self, path: Path, model_type: Type[T], readonly: bool = False
    ) -> Optional[T]:
        """The cached record for `path`, or None if there is none or its file changed.

        `readonly=True` returns the shared cached instance; otherwise an editable copy.
        Raises ValueError if the cached record isn't a `model_type`.
        """
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
        """The `id` of the cached record for `path`, or None if there is none or its
        file changed."""
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
        key = _cache_key(path)
        with self._lock:
            self._remove(key)
            if entry.normal_bytes > self._budget_bytes:
                return
            self._records[key] = entry
            self._total_bytes += entry.normal_bytes
            if (
                detached is not None
                and entry.large_owner is not None
                and entry.large_bytes <= self._budget_bytes
            ):
                self._load_large_values(key, entry, detached.values)
            if self._total_bytes <= self._budget_bytes:
                return
            eviction = self._evict()
        eviction.log()

    def _load_large_values(
        self, key: str, entry: _Entry, values: "Mapping[FieldPath, Any]"
    ) -> None:
        """Call with the lock held, for an entry in `_records` without loaded values."""
        entry.large_values = values
        self._loaded[key] = None
        self._total_bytes += entry.large_bytes

    def _drop_large_values(self, key: str) -> None:
        """Call with the lock held, for a key in `_loaded`."""
        del self._loaded[key]
        entry = self._records[key]
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

    def _remove(self, key: str) -> None:
        """Call with the lock held."""
        entry = self._records.pop(key, None)
        if entry is None:
            return
        self._total_bytes -= entry.normal_bytes
        if key in self._loaded:
            del self._loaded[key]
            self._total_bytes -= entry.large_bytes

    def invalidate(self, path: Path) -> None:
        """Drop the cached record for `path`, if there is one."""
        with self._lock:
            self._remove(_cache_key(path))

    def clear(self) -> None:
        """Drop every cached record."""
        with self._lock:
            self._records.clear()
            self._loaded.clear()
            self._total_bytes = 0

    def stats(self) -> CacheStats:
        """The cache's record counts, accounted bytes and budget, read together."""
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
        key = _cache_key(path)
        with self._lock:
            entry = self._records.get(key)
            if (
                entry is None
                or entry.large_owner is not owner
                or entry.large_values is None
            ):
                return None
            self._records.move_to_end(key)
            self._loaded.move_to_end(key)
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
        key = _cache_key(path)
        with self._lock:
            entry = self._records.get(key)
            if (
                entry is None
                or entry.large_owner is not owner
                or identity != entry.identity
                or size > self._budget_bytes
            ):
                return False
            self._records.move_to_end(key)
            if entry.large_values is not None:
                self._loaded.move_to_end(key)
                return True
            entry.large_bytes = size
            self._load_large_values(key, entry, values)
            if self._total_bytes <= self._budget_bytes:
                return True
            eviction = self._evict()
        eviction.log()
        return True

    def is_current_entry(self, path: Path, owner: object) -> bool:
        """Whether this cache still holds the detached record `owner` stands for."""
        with self._lock:
            entry = self._records.get(_cache_key(path))
            return entry is not None and entry.large_owner is owner

    def drop_entry(self, path: Path, owner: object) -> None:
        """Remove the entry for `path` if it holds the detached record `owner` stands for."""
        with self._lock:
            if self.is_current_entry(path, owner):
                self._remove(_cache_key(path))


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
