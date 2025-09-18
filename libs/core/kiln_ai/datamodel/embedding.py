from typing import TYPE_CHECKING, List, Union

from pydantic import BaseModel, Field, model_validator

from kiln_ai.datamodel.basemodel import ID_TYPE, FilenameString, KilnParentedModel
from kiln_ai.datamodel.datamodel_enums import ModelProviderName

if TYPE_CHECKING:
    from kiln_ai.datamodel.chunk import ChunkedDocument
    from kiln_ai.datamodel.project import Project


class EmbeddingConfig(KilnParentedModel):
    name: FilenameString = Field(
        description="A name to identify the embedding config.",
    )
    description: str | None = Field(
        default=None,
        description="A description for your reference, not shared with embedding models.",
    )
    model_provider_name: ModelProviderName = Field(
        description="The provider to use to generate embeddings.",
    )
    model_name: str = Field(
        description="The model to use to generate embeddings.",
    )
    properties: dict[str, str | int | float | bool] = Field(
        description="Properties to be used to execute the embedding config.",
    )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore

    @model_validator(mode="after")
    def validate_properties(self):
        if "dimensions" in self.properties:
            if (
                not isinstance(self.properties["dimensions"], int)
                or self.properties["dimensions"] <= 0
            ):
                raise ValueError("Dimensions must be a positive integer")

        return self


class Embedding(BaseModel):
    vector: List[float] = Field(description="The vector of the embedding.")


class ChunkEmbeddings(KilnParentedModel):
    embedding_config_id: ID_TYPE = Field(
        description="The ID of the embedding config used to generate the embeddings.",
    )
    embeddings: List[Embedding] = Field(
        description="The embeddings of the chunks. The embedding at index i corresponds to the chunk at index i in the parent chunked document."
    )

    def parent_chunked_document(self) -> Union["ChunkedDocument", None]:
        if self.parent is None or self.parent.__class__.__name__ != "ChunkedDocument":
            return None
        return self.parent  # type: ignore
