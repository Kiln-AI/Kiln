from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, List, Union

import yaml
from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.utils.validation import SkillNameString

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


SKILL_MD_FILENAME = "SKILL.md"

RESOURCE_DIR_NAMES = ("references", "assets")


class ResourceTooLargeError(ValueError):
    """A resource file exceeds the caller's size limit."""


class Skill(KilnParentedModel):
    """A Skill represents reusable agent instructions following the agentskills.io specification.

    Skills are project-level resources that can be attached to run configs.
    The agent discovers available skills via the skill tool description, then
    loads a skill's body on demand by calling skill(name="skill_name").

    The skill's body (markdown instructions) is stored in a SKILL.md sidecar file
    rather than in skill.kiln, following the agentskills.io spec.
    """

    name: SkillNameString = Field(
        description="Skill name. Kebab-case: lowercase alphanumeric with hyphens.",
    )
    description: str = Field(
        description="Description of what the skill does and when to use it.",
        min_length=1,
        max_length=1024,
    )
    is_archived: bool = Field(
        default=False,
        description="Whether the skill is archived. Archived skills are hidden from the UI and not available for use.",
    )

    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore

    def skill_md_path(self) -> Path:
        """Path to the SKILL.md sidecar file (sibling of skill.kiln)."""
        if self.path is None:
            raise ValueError("Skill must be saved before accessing SKILL.md path")
        return self.path.parent / SKILL_MD_FILENAME

    def skill_md_raw(self) -> str:
        """Read the full SKILL.md file content (frontmatter + body)."""
        md_path = self.skill_md_path()
        if not md_path.exists():
            raise FileNotFoundError(f"SKILL.md not found at {md_path}")
        if md_path.is_dir():
            raise FileNotFoundError(f"SKILL.md path is a folder, not a file: {md_path}")
        return md_path.read_text(encoding="utf-8")

    def body(self) -> str:
        """Read the markdown body from SKILL.md (content after YAML frontmatter)."""
        return _parse_skill_md_body(self.skill_md_raw())

    # -- Resources (references & assets) --

    def references_dir(self) -> Path:
        if self.path is None:
            raise ValueError(
                "Skill must be saved before accessing references directory"
            )
        return self.path.parent / "references"

    def assets_dir(self) -> Path:
        if self.path is None:
            raise ValueError("Skill must be saved before accessing assets directory")
        return self.path.parent / "assets"

    def read_reference(self, relative_path: str) -> str:
        """Read a reference file. Raises ValueError for path traversal, non-text, or if the path is a folder, FileNotFoundError if missing."""
        return self._read_resource(self.references_dir(), relative_path)

    def read_asset(self, relative_path: str) -> str:
        """Read an asset file. Raises ValueError for path traversal, non-text, or if the path is a folder, FileNotFoundError if missing."""
        return self._read_resource(self.assets_dir(), relative_path)

    def _resolve_resource(self, base_dir: Path, relative_path: str) -> Path:
        """Resolve a resource path, validating it stays within base_dir and is not a folder."""
        if not relative_path or not relative_path.strip():
            raise ValueError("Path cannot be empty")

        target = base_dir / relative_path
        try:
            resolved = target.resolve()
            resolved.relative_to(base_dir.resolve())
        except ValueError:
            raise ValueError("Path traversal is not allowed") from None

        if resolved.is_dir():
            raise ValueError(f"Path is a folder, not a file: {relative_path}")

        return resolved

    def _read_resource(self, base_dir: Path, relative_path: str) -> str:
        """Read a resource file, validating it resolves within base_dir and is readable text."""
        resolved = self._resolve_resource(base_dir, relative_path)
        try:
            return resolved.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Resource file not found: {relative_path}"
            ) from None
        except UnicodeDecodeError:
            raise ValueError(
                f"File is not a readable text file: {relative_path}"
            ) from None

    def _resource_base_dir(self, prefixed_path: str) -> tuple[Path, str]:
        """Split a 'references/…' or 'assets/…' path into (base_dir, relative_path)."""
        prefix, sep, relative_path = prefixed_path.partition("/")
        if prefix not in RESOURCE_DIR_NAMES or not sep or not relative_path:
            raise ValueError(
                f"Resource path must start with 'references/' or 'assets/' followed by a filename: {prefixed_path!r}"
            )
        base_dir = (
            self.references_dir() if prefix == "references" else self.assets_dir()
        )
        return base_dir, relative_path

    def read_resource_bytes(
        self, prefixed_path: str, max_bytes: int | None = None
    ) -> bytes:
        """Read any resource file as bytes (binary-safe).

        prefixed_path must start with 'references/' or 'assets/'. Raises ValueError
        for invalid paths or path traversal, FileNotFoundError if missing, and
        ResourceTooLargeError if max_bytes is set and the file exceeds it (checked
        while reading, so a file growing mid-read cannot slip past the cap).
        """
        base_dir, relative_path = self._resource_base_dir(prefixed_path)
        resolved = self._resolve_resource(base_dir, relative_path)
        try:
            if max_bytes is None:
                return resolved.read_bytes()
            with open(resolved, "rb") as file:
                data = file.read(max_bytes + 1)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Resource file not found: {prefixed_path}"
            ) from None
        if len(data) > max_bytes:
            raise ResourceTooLargeError(
                f"Resource is over the {max_bytes} byte limit: {prefixed_path}"
            )
        return data

    def list_resources_with_sizes(self) -> List[tuple[str, int]]:
        """List every regular file under references/ and assets/ with its size
        in bytes, as sorted ('references/…' / 'assets/…', size) pairs.
        Symlinks are skipped."""
        resources: List[tuple[str, int]] = []
        for base_dir in (self.references_dir(), self.assets_dir()):
            if not base_dir.is_dir():
                continue
            for root, _dirs, files in os.walk(base_dir, followlinks=False):
                root_path = Path(root)
                for filename in files:
                    file_path = root_path / filename
                    try:
                        if file_path.is_symlink() or not file_path.is_file():
                            continue
                        size = file_path.stat().st_size
                    except OSError:
                        # File vanished mid-walk (e.g. the user is editing the
                        # folder directly) — skip it.
                        continue
                    relative = file_path.relative_to(base_dir).as_posix()
                    resources.append((f"{base_dir.name}/{relative}", size))
        return sorted(resources)

    def list_resource_files(self) -> List[str]:
        """List every regular file under references/ and assets/, as sorted
        'references/…' / 'assets/…' relative paths. Symlinks are skipped."""
        return [path for path, _size in self.list_resources_with_sizes()]

    def save_skill_md(self, body: str) -> None:
        """Write SKILL.md with YAML frontmatter (name, description) + markdown body.

        Reads name and description from self to keep SKILL.md in sync with skill.kiln.
        """
        if not body or not body.strip():
            raise ValueError("body must be non-empty")
        frontmatter = yaml.dump(
            {"name": self.name, "description": self.description},
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        ).rstrip("\n")
        content = f"---\n{frontmatter}\n---\n\n{body}"
        self.skill_md_path().write_text(content, encoding="utf-8")
        self.references_dir().mkdir(exist_ok=True)
        self.assets_dir().mkdir(exist_ok=True)


def _parse_skill_md_body(raw: str) -> str:
    """Parse a SKILL.md file and return the body content after frontmatter."""
    if not raw.startswith("---\n"):
        return raw
    end_idx = raw.index("\n---\n", 3)
    body = raw[end_idx + 5 :]
    return body.lstrip("\n")
