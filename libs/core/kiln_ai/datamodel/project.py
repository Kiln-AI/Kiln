from pydantic import Field

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnParentModel
from kiln_ai.datamodel.task import Task


class Project(KilnParentModel, parent_of={"tasks": Task}):
    """
    A collection of related tasks.

    Projects organize tasks into logical groups and provide high-level descriptions
    of the overall goals.
    """

    name: str = NAME_FIELD
    description: str | None = Field(
        default=None,
        description="A description of the project for you and your team. Will not be used in prompts/training/validation.",
    )

    # Needed for typechecking. TODO P2: fix this in KilnParentModel
    def tasks(self) -> list[Task]:
        return super().tasks()  # type: ignore
