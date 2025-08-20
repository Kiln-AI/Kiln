from pydantic import Field

from kiln_ai.datamodel.basemodel import ID_TYPE, FilenameString, KilnParentedModel


class RagConfig(KilnParentedModel):
    name: FilenameString = Field(
        description="A name to identify this RAG configuration for your own reference.",
    )

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
