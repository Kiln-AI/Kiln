from pydantic import Field

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnParentModel
from kiln_ai.datamodel.chunk import ChunkerConfig
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.datamodel.extraction import Document, ExtractorConfig
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.vector_store import VectorStoreConfig


class Project(
    KilnParentModel,
    parent_of={
        "tasks": Task,
        "documents": Document,
        "extractor_configs": ExtractorConfig,
        "chunker_configs": ChunkerConfig,
        "embedding_configs": EmbeddingConfig,
        "rag_configs": RagConfig,
        "vector_store_configs": VectorStoreConfig,
    },
):
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

    def documents(self, readonly: bool = False) -> list[Document]:
        return super().documents(readonly=readonly)  # type: ignore

    def extractor_configs(self, readonly: bool = False) -> list[ExtractorConfig]:
        return super().extractor_configs(readonly=readonly)  # type: ignore

    def chunker_configs(self, readonly: bool = False) -> list[ChunkerConfig]:
        return super().chunker_configs(readonly=readonly)  # type: ignore

    def embedding_configs(self, readonly: bool = False) -> list[EmbeddingConfig]:
        return super().embedding_configs(readonly=readonly)  # type: ignore

    def vector_store_configs(self, readonly: bool = False) -> list[VectorStoreConfig]:
        return super().vector_store_configs(readonly=readonly)  # type: ignore

    def rag_configs(self, readonly: bool = False) -> list[RagConfig]:
        return super().rag_configs(readonly=readonly)  # type: ignore
