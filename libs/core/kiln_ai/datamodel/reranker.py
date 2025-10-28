from enum import Enum
from typing import TYPE_CHECKING, Literal, Union

from pydantic import Field, PositiveInt
from typing_extensions import TypedDict

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class RerankerType(str, Enum):
    COHERE_COMPATIBLE = "cohere_compatible"


class CohereCompatibleProperties(TypedDict, total=True):
    type: Literal[RerankerType.COHERE_COMPATIBLE]


class RerankerConfig(KilnParentedModel):
    name: FilenameString = Field(
        description="A name for your own reference to identify the reranker config.",
    )
    description: str | None = Field(
        description="A description for your own reference.",
        default=None,
    )
    top_n: PositiveInt = Field(
        description="The number of results to return from the reranker.",
    )
    model_provider_name: str = Field(
        description="The name of the model provider to use.",
    )
    model_name: str = Field(
        description="The name of the model to use.",
    )
    properties: CohereCompatibleProperties = Field(
        description="The properties of the reranker config, specific to the selected type.",
        discriminator="type",
    )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore
