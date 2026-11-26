"""Temporary files for `save_to_tmpfile`: API response bodies written to a
private folder on the machine that runs Kiln."""

import logging
import os
import secrets
import stat
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_SECONDS = 24 * 3600


def default_tmp_root() -> Path:
    return Path(tempfile.gettempdir()) / "kiln_mcp"


@dataclass(frozen=True)
class SavedFile:
    path: Path
    size_bytes: int


class TmpFileError(Exception):
    pass


class TmpFileStore:
    """Writes response bodies to files in `root`, readable by the current user
    only, and removes them again. `root` is created on first save."""

    def __init__(
        self, root: Path, max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS
    ) -> None:
        self._root = root
        self._max_age_seconds = max_age_seconds

    def save(self, text: str, is_json: bool) -> SavedFile:
        """Write `text` as UTF-8 to a new file. Raises TmpFileError when the
        folder is not a private folder of this user, OSError when the write
        fails."""
        self._ensure_root()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        suffix = ".json" if is_json else ".txt"
        path = self._root / f"kiln_api_{stamp}_{secrets.token_hex(4)}{suffix}"
        data = text.encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        return SavedFile(path=path, size_bytes=len(data))

    def purge_all(self) -> None:
        self._purge(older_than=None)

    def purge_expired(self) -> None:
        self._purge(older_than=time.time() - self._max_age_seconds)

    def _ensure_root(self) -> None:
        try:
            os.mkdir(self._root, 0o700)
        except FileExistsError:
            self._check_root()
        os.chmod(self._root, 0o700)

    def _check_root(self) -> None:
        """Raises FileNotFoundError when the folder is missing, TmpFileError
        when it is a symlink, not a folder, or owned by another user."""
        info = os.lstat(self._root)
        owned = not hasattr(os, "getuid") or info.st_uid == os.getuid()
        if not stat.S_ISDIR(info.st_mode) or not owned:
            raise TmpFileError(
                f"{self._root} exists but is not a folder owned by the current user"
            )

    def _purge(self, older_than: float | None) -> None:
        """Remove the regular files directly in the folder, all of them or
        those last modified before `older_than`. Never raises."""
        try:
            self._check_root()
            entries = list(os.scandir(self._root))
        except FileNotFoundError:
            return
        except (TmpFileError, OSError) as e:
            logger.warning("Not purging MCP temp files: %s", e)
            return
        for entry in entries:
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                if (
                    older_than is not None
                    and entry.stat(follow_symlinks=False).st_mtime >= older_than
                ):
                    continue
                os.unlink(entry.path)
            except OSError:
                logger.debug("Could not remove MCP temp file %s", entry.path)
