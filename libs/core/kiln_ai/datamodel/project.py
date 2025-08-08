from pydantic import Field

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentModel
from kiln_ai.datamodel.external_tool import ExternalTool
from kiln_ai.datamodel.task import Task


class Project(
    KilnParentModel, parent_of={"tasks": Task, "external_tools": ExternalTool}
):
    """
    A collection of related tasks.

    Projects organize tasks into logical groups and provide high-level descriptions
    of the overall goals.
    """

    name: FilenameString = Field(description="The name of the project.")
    description: str | None = Field(
        default=None,
        description="A description of the project for you and your team. Will not be used in prompts/training/validation.",
    )

    # Needed for typechecking. We should fix this in KilnParentModel
    def tasks(self) -> list[Task]:
        return super().tasks()  # type: ignore

    def external_tools(self, readonly: bool = False) -> list[ExternalTool]:
        return super().external_tools(readonly=readonly)  # type: ignore
