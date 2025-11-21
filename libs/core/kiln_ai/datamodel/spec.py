from enum import Enum
from typing import List

from pydantic import Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import ID_TYPE, FilenameString, KilnParentedModel
from kiln_ai.datamodel.datamodel_enums import Priority


class SpecType(str, Enum):
    """Defines the type of spec."""

    # Functionality
    desired_behaviour = "desired_behaviour"
    undesired_behaviour = "undesired_behaviour"

    # Reasoning & Execution
    appropriate_tool_use = "appropriate_tool_use"
    intermediate_reasoning = "intermediate_reasoning"

    # Correctness
    reference_answer_accuracy = "reference_answer_accuracy"
    factual_correctness = "factual_correctness"
    hallucinations = "hallucinations"
    completeness = "completeness"
    consistency = "consistency"

    # Style
    tone = "tone"
    formatting = "formatting"
    localization = "localization"

    # Safety
    toxicity = "toxicity"
    bias = "bias"
    maliciousness = "maliciousness"
    nsfw = "nsfw"
    taboo = "taboo"

    # System Constraints
    jailbreak = "jailbreak"
    prompt_leakage = "prompt_leakage"


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
    type: SpecType = Field(
        description="The type of spec.",
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
    eval_id: ID_TYPE | None = Field(
        default=None,
        description="The id of the eval to use for this spec. If None, the spec is not associated with an eval.",
    )

    @model_validator(mode="after")
    def validate_tags(self) -> Self:
        for tag in self.tags:
            if not tag:
                raise ValueError("tags cannot be empty strings")
            if " " in tag:
                raise ValueError("tags cannot contain spaces. Try underscores.")

        return self
