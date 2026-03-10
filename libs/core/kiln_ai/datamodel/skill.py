from __future__ import annotations

from typing import TYPE_CHECKING, Union

from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.utils.validation import ToolNameString

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class Skill(KilnParentedModel):
    """A Skill represents reusable agent instructions following the agentskills.io specification.

    Skills are project-level resources that can be attached to run configs.
    The agent discovers available skills via the skill tool description, then
    loads a skill's body on demand by calling skill(name="skill_name").
    """

    name: ToolNameString = Field(
        description="Skill name. Snake_case: lowercase alphanumeric with underscores, 1-64 chars.",
    )
    description: str = Field(
        description="Description of what the skill does and when to use it. 1-1024 chars.",
        min_length=1,
        max_length=1024,
    )
    body: str = Field(
        description="The markdown body content (instructions) of the skill.",
        min_length=1,
    )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore
