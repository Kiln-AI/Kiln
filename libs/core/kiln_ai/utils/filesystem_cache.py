import logging
import tempfile
from pathlib import Path

import anyio

from kiln_ai.datamodel.basemodel import name_validator

logger = logging.getLogger(__name__)


class FilesystemCache:
    def __init__(self, path: Path):
        self.cache_dir_path = path

    def validate_key(self, key: str) -> None:
        # throws if invalid
        name_validator(min_length=1, max_length=120)(key)

    def get_path(self, key: str) -> Path:
        self.validate_key(key)
        return self.cache_dir_path / key

    async def get(self, key: str) -> bytes | None:
        # check if the file exists - don't need to validate the key
        # worst case we just return None
        if not self.get_path(key).exists():
            return None

        # we don't want to raise because of internal cache corruption issues
        try:
            return await anyio.Path(self.get_path(key)).read_bytes()
        except Exception:
            logger.error(f"Error reading file {self.get_path(key)}", exc_info=True)
            return None

    async def set(self, key: str, value: bytes) -> Path:
        logger.debug(f"Caching {key} at {self.get_path(key)}")
        self.validate_key(key)
        path = self.get_path(key)
        await anyio.Path(path).write_bytes(value)
        return path

    async def delete_by_prefix(self, prefix: str) -> None:
        # we avoid globbing here to avoid any unexpected traversal/glob injection
        logger.debug(f"Deleting cache by prefix {prefix} in {self.cache_dir_path}")
        for path in self.cache_dir_path.iterdir():
            if path.is_file() and path.name.startswith(prefix):
                try:
                    await anyio.Path(path).unlink()
                except FileNotFoundError:
                    continue
                except Exception:
                    logger.error(f"Error deleting cache path {path}", exc_info=True)


class TemporaryFilesystemCache:
    _shared_instance = None

    def __init__(self):
        self._cache_temp_dir = tempfile.mkdtemp(prefix="kiln_cache_")
        self.filesystem_cache = FilesystemCache(path=Path(self._cache_temp_dir))

        logger.debug(
            f"Created temporary filesystem cache directory: {self._cache_temp_dir}"
        )

    @classmethod
    def shared(cls) -> FilesystemCache:
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance.filesystem_cache
