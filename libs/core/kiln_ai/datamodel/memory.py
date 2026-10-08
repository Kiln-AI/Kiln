import contextlib
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.datamodel.model_cache import ModelCache
from kiln_ai.utils.validation import validate_tags

# These caps are enforced at write time AND re-applied by pydantic when loading
# stored rows, so any row exceeding them (e.g. from an out-of-band writer) fails
# to load: the memory store skips it with a warning, in listings and fetches by id.
# Raising them is safe; never lower them.
MAX_OVERVIEW_LENGTH = 280
MAX_CONTENT_LENGTH = 4000
MAX_SCOPE_LENGTH = 255

# Flags for the temp file of an atomic write. O_EXCL makes the create fail if the
# name exists, so two writers never share a temp file. O_NOFOLLOW and O_BINARY
# match what tempfile.mkstemp uses, where the platform has them.
_TEMP_OPEN_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_BINARY", 0)
)
_TEMP_CREATE_ATTEMPTS = 100


def _create_temp_file(directory: Path) -> tuple[int, str]:
    """Create a new temp file in directory with the mode of a normal file write.

    tempfile.mkstemp creates its file with mode 0o600, so a file moved into place
    with os.replace would be private while every other .kiln file is not. This
    creates the file with mode 0o666, and the kernel applies the process umask,
    exactly as it does for open(path, "w"). There is no need to read the umask:
    os.umask can only be read by setting it, which is a race with other threads.
    """
    for _ in range(_TEMP_CREATE_ATTEMPTS):
        name = str(directory / f".tmp-{uuid.uuid4().hex}.kiln")
        try:
            return os.open(name, _TEMP_OPEN_FLAGS, 0o666), name
        except FileExistsError:
            continue
    raise FileExistsError(f"No free temp file name in {directory}")


# On Windows, os.replace fails with PermissionError while another handle has the
# target open, because Python's open() does not share delete access. Readers hold
# a memory file only for the time of one read, so a short retry gets through.
_RETRY_REPLACE = sys.platform == "win32"
_REPLACE_ATTEMPTS = 20
_REPLACE_RETRY_DELAY_SECONDS = 0.01


def _replace(src: str, dst: Path) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not _RETRY_REPLACE or attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS)


class Memory(KilnParentedModel):
    """One memory record of the assistant working on this project.

    Stored at assistant_memory/{id}/memory.kiln. Concurrent-append safe
    (file per memory); updates are last-writer-wins.
    """

    overview: str = Field(
        max_length=MAX_OVERVIEW_LENGTH,
        description="One-line summary written so a future reader can decide "
        "whether to fetch the full content. For very short memories this IS "
        "the whole memory (leave content null). No newlines.",
    )
    content: str | None = Field(
        default=None,
        max_length=MAX_CONTENT_LENGTH,
        description="The memory body: the finding/fact/decision with its "
        "conditions and evidence level, citing related Kiln records as prose "
        "IDs (e.g. 'run_config 184623901234', 'eval 5678'). Null when the "
        "overview says everything. Record observations with conditions "
        "('batch API 429'd at 50rps on 07-04'), never universal rules.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Snake_case tags for filtering (existing Kiln tag rules). "
        "Free-form; skills define the working vocabulary (e.g. experiment, "
        "dead_end, constraint, api_quirk, session_state; faceted tags like "
        "lever_prompt, verdict_accept, evidence_weak).",
    )
    scope: str = Field(
        max_length=MAX_SCOPE_LENGTH,
        description="Opaque scope string, exact-match filterable. Conventions: "
        "'project' for project-wide knowledge (constraints, environment "
        "facts); 'task::<task_id>' for task-scoped work. Not validated "
        "against existing records — a convention, not a reference.",
    )

    # Write-time-only, load-safe validators. All rules are monotonic (a record
    # that once saved keeps satisfying them), so nothing here fails on load.

    @field_validator("overview", mode="before")
    @classmethod
    def _normalize_overview(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        v = v.strip()
        if not v:
            raise ValueError("overview cannot be empty")
        if "\n" in v or "\r" in v:
            raise ValueError("overview cannot contain newlines")
        return v

    @field_validator("content", mode="before")
    @classmethod
    def _normalize_content(cls, v: Any) -> Any:
        if v is None or not isinstance(v, str):
            return v
        v = v.strip()
        if v == "":
            return None
        return v

    @field_validator("scope", mode="before")
    @classmethod
    def _normalize_scope(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        v = v.strip()
        if not v:
            raise ValueError("scope cannot be empty")
        if "\n" in v or "\r" in v:
            raise ValueError("scope cannot contain newlines")
        if len(v) > MAX_SCOPE_LENGTH:
            raise ValueError(
                f"scope cannot be longer than {MAX_SCOPE_LENGTH} characters"
            )
        return v

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str]) -> list[str]:
        return validate_tags(v)

    def save_to_file(self, create_dirs: bool = True) -> None:
        """Atomically write the record (temp file + os.replace).

        The memory store is lock-free and multi-process by design (many sessions
        append concurrently with no locking). Core save_to_file writes in place
        (truncate + write), so a reader in another process can observe a
        half-written file. Writing to a temp file in the same directory and then
        os.replace()-ing it into place means every concurrent reader sees either
        the previous complete file or the new complete file — never a torn one.
        Memory has no attachments, so the plain JSON dump is sufficient. The temp
        file gets the same mode as a normal write (see _create_temp_file).

        `create_dirs=False` writes only into a folder that still exists: an update
        racing a delete in another process then fails with FileNotFoundError
        instead of re-creating the folder and bringing the memory back.
        """
        path = self.build_path()
        if path is None:
            raise ValueError(
                "Cannot save to file because 'path' is not set. "
                f"Class: {self.__class__.__name__}, id: {getattr(self, 'id', None)}"
            )
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)

        json_data = self.model_dump_json(indent=2, exclude={"path"})

        fd, tmp_name = _create_temp_file(path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(json_data)
            _replace(tmp_name, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

        # Save the resolved path so later field changes don't move the file.
        self.path = path
        ModelCache.shared().invalidate(path)
