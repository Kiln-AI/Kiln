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
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Type, TypeVar

if TYPE_CHECKING:
    from kiln_ai.datamodel.basemodel import KilnBaseModel

    T = TypeVar("T", bound="KilnBaseModel")
else:
    T = TypeVar("T")


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
class _Entry:
    model: "KilnBaseModel"
    identity: FileIdentity


class ModelCache:
    _shared_instance: "ModelCache | None" = None

    def __init__(self, *, enabled: bool = False) -> None:
        self._entries: dict[Path, _Entry] = {}
        self._enabled = enabled

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
        # One dict call, not a membership test and then an index: another thread
        # can remove the entry between the two, and the index raises KeyError.
        entry = self._entries.get(path)
        if entry is None:
            return None
        if FileIdentity.from_path(path) != entry.identity:
            self.invalidate(path)
            return None

        model = entry.model
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
        self._entries[path] = _Entry(model=model, identity=identity)

    def invalidate(self, path: Path) -> None:
        # pop() with a default is one dict call, so two threads that invalidate the
        # same path at once cannot both pass a membership test and then both delete.
        self._entries.pop(path, None)

    def clear(self) -> None:
        self._entries.clear()


def set_model_cache_enabled(value: bool) -> None:
    """Turn the process-wide datamodel cache on or off.

    Off by default in the library. With it on, readonly loads
    (`load_from_file(..., readonly=True)`, `task.runs(readonly=True)`, ...) keep each
    parsed record in memory and serve it again until its file changes. Turning it off
    drops every cached record.
    """
    ModelCache.shared().set_enabled(value)


def model_cache_enabled() -> bool:
    """Whether the process-wide datamodel cache is on."""
    return ModelCache.shared().enabled
