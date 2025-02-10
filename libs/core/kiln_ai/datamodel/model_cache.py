"""
A simple cache for our datamodel.

Works at the file level, caching the pydantic model based on the file path.

Keeping this really simple. Our goal is to really be "disk-backed" data model, so using disk primitives.

 - Use disk mtime to determine if the cached model is stale.
 - Still using glob for iterating over projects, just caching at the file level
 - Use path as the cache key
 - Cache always populated from a disk read, so we know it refects what's on disk. Even if we had a memory-constructed version, we don't cache that.
 - Cache the parsed model, not the raw file contents. Parsing and validating is what's expensive. >99% speedup when measured.
"""

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ModelCache:
    _shared_instance = None

    def __init__(self):
        # Store both the model and the modified time of the cached file contents
        self.model_cache: Dict[Path, Tuple[BaseModel, int]] = {}
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
        if path not in self.model_cache:
            return None
        model, cached_mtime_ns = self.model_cache[path]
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
                return model.model_copy(deep=True)
        return None

    def get_model_id(self, path: Path, model_type: Type[T]) -> Optional[str]:
        model = self._get_model(path, model_type)
        if model and hasattr(model, "id"):
            id = model.id  # type: ignore
            if isinstance(id, str):
                return id
        return None

    def set_model(self, path: Path, model: BaseModel, mtime_ns: int):
        # disable caching if the filesystem doesn't support fine-grained timestamps
        if not self._enabled:
            return
        self.model_cache[path] = (model, mtime_ns)

    def invalidate(self, path: Path):
        if path in self.model_cache:
            del self.model_cache[path]

    def clear(self):
        self.model_cache.clear()

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
