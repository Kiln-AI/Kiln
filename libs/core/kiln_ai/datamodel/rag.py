from typing import TYPE_CHECKING, Union

from pydantic import Field

from kiln_ai.datamodel.basemodel import ID_TYPE, NAME_FIELD, KilnParentedModel

if TYPE_CHECKING:
    from kiln_ai.datamodel.project import Project


class RagConfig(KilnParentedModel):
    name: str = NAME_FIELD

    description: str | None = Field(
        default=None,
        description="A description of the RAG configuration for you and your team. Will not be used in prompts/training/validation.",
    )

    extractor_config_id: ID_TYPE = Field(
        description="The ID of the extractor config that was used to extract the documents.",
    )

    chunker_config_id: ID_TYPE = Field(
        description="The ID of the chunker config that was used to chunk the documents.",
    )

    embedding_config_id: ID_TYPE = Field(
        description="The ID of the embedding config that was used to embed the documents.",
    )

    vector_store_config_id: ID_TYPE = Field(
        description="The ID of the vector store config that was used to store the documents.",
    )

    # Workaround to return typed parent without importing Project
    def parent_project(self) -> Union["Project", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Project":
            return None
        return self.parent  # type: ignore
