from enum import Enum
from typing import List

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import ID_TYPE, FilenameString, KilnParentedModel
from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.spec_properties import SpecProperties


class TaskSample(BaseModel):
    """An example task input/output pair used to demonstrate expected behavior."""

    input: str = Field(description="The example input for the task.")
    output: str = Field(description="The expected output for the task.")


class PromptGenerationInfo(BaseModel):
    """Information about a prompt generation step during copilot spec creation."""

    model_name: str = Field(description="The model used for generation.")
    provider_name: str = Field(
        description="The provider of the model used for generation."
    )
    prompt: str = Field(description="The prompt used for generation.")


class SpecStatus(str, Enum):
    """Defines the status of a spec."""

    active = "active"
    future = "future"
    deprecated = "deprecated"
    archived = "archived"


class Spec(KilnParentedModel):
    """A spec for a task."""

    name: FilenameString = Field(description="The name of the spec.", min_length=1)
    definition: str = Field(
        description="A detailed definition of the spec.", min_length=1
    )
    properties: SpecProperties = Field(
        description="The properties of the spec.",
        discriminator="spec_type",
    )
    priority: Priority = Field(
        default=Priority.p1,
        description="The priority of the spec.",
    )
    status: SpecStatus = Field(
        default=SpecStatus.active,
        description="The status of the spec.",
    )
    tags: List[str] = Field(
        default=[],
        description="The tags of the spec.",
    )
    eval_id: ID_TYPE = Field(
        description="The id of the eval to use for this spec.",
    )
    task_sample: TaskSample | None = Field(
        default=None,
        description="An example task input/output pair used to demonstrate expected behavior for this spec.",
    )
    topic_generation_info: PromptGenerationInfo | None = Field(
        default=None,
        description="Information about topic generation during copilot spec creation.",
    )
    input_generation_info: PromptGenerationInfo | None = Field(
        default=None,
        description="Information about input generation during copilot spec creation.",
    )

    @model_validator(mode="after")
    def validate_tags(self) -> Self:
        for tag in self.tags:
            if not tag:
                raise ValueError("tags cannot be empty strings")
            if " " in tag:
                raise ValueError("tags cannot contain spaces. Try underscores.")

        return self
