import logging
import tempfile
from pathlib import Path

from kiln_ai.datamodel.basemodel import name_validator

logger = logging.getLogger(__name__)


class FilesystemCache:
    def __init__(self, path: Path):
        # the key must be a valid filename
        validate_key = name_validator(min_length=1, max_length=120)
        self.validate_key = validate_key
        self.cache_dir_path = path

    def get_path(self, key: str) -> Path:
        self.validate_key(key)
        return self.cache_dir_path / key

    def get(self, key: str) -> bytes | None:
        # check if the file exists
        if not self.get_path(key).exists():
            return None

        # we don't want to raise because of internal cache corruption issues
        try:
            with open(self.get_path(key), "rb") as f:
                return f.read()
        except Exception:
            logger.error(f"Error reading file {self.get_path(key)}", exc_info=True)
            return None

    def set(self, key: str, value: bytes) -> Path:
        logger.debug(f"Caching {key} at {self.get_path(key)}")
        self.validate_key(key)
        path = self.get_path(key)
        path.write_bytes(value)
        return path


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
