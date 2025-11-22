from enum import Enum
from typing import List

from pydantic import Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import ID_TYPE, FilenameString, KilnParentedModel
from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.spec_properties import SpecProperties, SpecType


class SpecStatus(str, Enum):
    """Defines the status of a spec."""

    active = "active"
    future = "future"
    deprecated = "deprecated"
    archived = "archived"


class Spec(KilnParentedModel):
    """A spec for a task."""

    name: FilenameString = Field(description="The name of the spec.", min_length=1)
    description: str = Field(description="A description of the spec.", min_length=1)
    type: SpecType = Field(
        description="The type of spec.",
    )
    properties: SpecProperties | None = Field(
        default=None,
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

    @model_validator(mode="after")
    def validate_type_matches_properties(self) -> Self:
        if self.properties is not None:
            properties_type = self.properties.get("spec_type")
            if properties_type != self.type:
                raise ValueError(
                    f"Spec type mismatch: spec.type is '{self.type}' but properties.spec_type is '{properties_type}'"
                )
        return self
