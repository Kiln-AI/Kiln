import contextlib
import os
import tempfile
from typing import Any

from pydantic import Field, field_validator

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.datamodel.model_cache import ModelCache
from kiln_ai.utils.validation import validate_tags

MAX_OVERVIEW_LENGTH = 140
MAX_CONTENT_LENGTH = 2000
MAX_SCOPE_LENGTH = 255


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

    def save_to_file(self) -> None:
        """Atomically write the record (temp file + os.replace).

        The memory store is lock-free and multi-process by design (many sessions
        append concurrently with no locking). Core save_to_file writes in place
        (truncate + write), so a reader in another process can observe a
        half-written file. Writing to a temp file in the same directory and then
        os.replace()-ing it into place means every concurrent reader sees either
        the previous complete file or the new complete file — never a torn one.
        Memory has no attachments, so the plain JSON dump is sufficient.
        """
        path = self.build_path()
        if path is None:
            raise ValueError(
                "Cannot save to file because 'path' is not set. "
                f"Class: {self.__class__.__name__}, id: {getattr(self, 'id', None)}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)

        json_data = self.model_dump_json(indent=2, exclude={"path"})

        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".kiln")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(json_data)
            os.replace(tmp_name, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

        # Save the resolved path so later field changes don't move the file.
        self.path = path
        ModelCache.shared().invalidate(path)
