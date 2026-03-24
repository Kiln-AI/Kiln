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
        description="Skill name. Kebab-case: lowercase alphanumeric with hyphens, 1-64 chars.",
    )
    description: str = Field(
        description="Description of what the skill does and when to use it. 1-1024 chars.",
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
        return md_path.read_text(encoding="utf-8")

    def body(self) -> str:
        """Read the markdown body from SKILL.md (content after YAML frontmatter)."""
        return _parse_skill_md_body(self.skill_md_raw())

    # -- References --

    def references_dir(self) -> Path:
        if self.path is None:
            raise ValueError(
                "Skill must be saved before accessing references directory"
            )
        return self.path.parent / "references"

    def read_reference(self, relative_path: str) -> str:
        """Read a reference file's content. Raises ValueError if path traversal, FileNotFoundError if missing."""
        path = self._validated_reference_path(relative_path)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Reference file not found: {relative_path}"
            ) from None

    def _validated_reference_path(self, relative_path: str) -> Path:
        _validate_reference_path(relative_path)
        if not relative_path.endswith(".md"):
            raise ValueError("Reference files must have a .md extension")
        return self.references_dir() / relative_path

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


def _validate_reference_path(relative_path: str) -> None:
    """Reject paths that are empty, use backslashes, or contain traversal components."""
    if not relative_path or not relative_path.strip():
        raise ValueError("Path cannot be empty")
    if "\\" in relative_path:
        raise ValueError("Path must not contain backslash separators")
    for segment in relative_path.split("/"):
        if not segment or not segment.strip():
            raise ValueError("Path must not contain empty segments")
        if segment == "." or segment == "..":
            raise ValueError("Path must not contain traversal components")


def _parse_skill_md_body(raw: str) -> str:
    """Parse a SKILL.md file and return the body content after frontmatter."""
    if not raw.startswith("---\n"):
        return raw
    end_idx = raw.index("\n---\n", 3)
    body = raw[end_idx + 5 :]
    return body.lstrip("\n")
