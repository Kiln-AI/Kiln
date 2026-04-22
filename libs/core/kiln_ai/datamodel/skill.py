from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Union

import yaml
from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.utils.validation import SkillNameString

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


SKILL_MD_FILENAME = "SKILL.md"


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

    def _read_resource(self, base_dir: Path, relative_path: str) -> str:
        """Read a resource file, validating it resolves within base_dir and is readable text."""
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
