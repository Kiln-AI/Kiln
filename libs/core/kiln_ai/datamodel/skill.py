from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Union

import yaml
from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.utils.validation import ToolNameString

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

    name: ToolNameString = Field(
        description="Skill name. Snake_case: lowercase alphanumeric with underscores, 1-64 chars.",
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


def _parse_skill_md_body(raw: str) -> str:
    """Parse a SKILL.md file and return the body content after frontmatter."""
    if not raw.startswith("---\n"):
        return raw
    end_idx = raw.index("\n---\n", 3)
    body = raw[end_idx + 5 :]
    return body.lstrip("\n")
