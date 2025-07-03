from typing import TYPE_CHECKING, Any, List, Union

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from kiln_ai.datamodel.basemodel import ID_TYPE, NAME_FIELD, KilnParentedModel

if TYPE_CHECKING:
    from kiln_ai.datamodel.chunk import ChunkedDocument
    from kiln_ai.datamodel.project import Project


class EmbeddingConfig(KilnParentedModel):
    name: str = NAME_FIELD
    description: str | None = Field(
        default=None, description="The description of the embedding config"
    )
    model_provider: Any = Field(
        description="The provider to use to generate embeddings.",
    )
    model_name: Any = Field(
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

    @field_validator("properties")
    @classmethod
    def validate_properties(
        cls, properties: dict[str, str | int | float | bool], info: ValidationInfo
    ) -> dict[str, str | int | float | bool]:
        # TODO: no properties for now
        return properties


class Embedding(BaseModel):
    vector: List[float] = Field(description="The vector of the embedding.")


class ChunkEmbeddings(KilnParentedModel):
    embedding_config_id: ID_TYPE = Field(
        description="The ID of the embedding config that was used to generate the embeddings.",
    )
    embeddings: List[Embedding] = Field(
        description="The embeddings of the chunks. The embedding at index i corresponds to the chunk at index i in the parent chunked document."
    )

    def parent_chunked_document(self) -> Union["ChunkedDocument", None]:
        if self.parent is None or self.parent.__class__.__name__ != "ChunkedDocument":
            return None
        return self.parent  # type: ignore
