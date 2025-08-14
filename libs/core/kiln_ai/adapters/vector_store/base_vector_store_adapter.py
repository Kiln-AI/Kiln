from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Tuple

from pydantic import BaseModel, Field

from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig


class SimilarityMetric(str, Enum):
    L2 = "l2"
    COSINE = "cosine"
    DOT_PRODUCT = "dot_product"


class SearchResult(BaseModel):
    document_id: str = Field(description="The id of the Kiln document.")
    chunk_idx: int = Field(description="The index of the chunk in the Kiln document.")
    chunk_text: str = Field(description="The text of the chunk.")
    score: float | None = Field(
        description="The score of the chunk, which depends on the similarity metric used."
    )


class BaseVectorStoreAdapter(ABC):
    def __init__(self, vector_store_config: VectorStoreConfig):
        self.vector_store_config = vector_store_config

    @abstractmethod
    async def create_collection(
        self, rag_config: RagConfig, vector_dimensions: int
    ) -> "BaseVectorStoreCollection":
        """
        Creates a new collection for the given RagConfig.
        """
        pass

    @abstractmethod
    async def collection(self, rag_config: RagConfig) -> "BaseVectorStoreCollection":
        """
        Returns a collection for the given RagConfig or creates a new one if it doesn't already exist.

        A collection is a unified interface around an underlying concrete construct that depends on the vector store,
        for example in LanceDB, it is called a table.
        """
        pass

    @abstractmethod
    async def destroy_collection(self, rag_config: RagConfig):
        """
        Destroys the collection for the given RagConfig.
        """
        pass


class BaseVectorStoreCollection(ABC):
    def __init__(self, vector_store_config: VectorStoreConfig):
        self.vector_store_config = vector_store_config

    @abstractmethod
    async def upsert_chunks(
        self,
        chunks: List[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ) -> None:
        """
        Upsert documents into the index for the given RagConfig. The implementation
        must be idempotent.

        Args:
            chunks: tuple of (document_id, chunked_document, chunk_embeddings)
        """
        pass

    @abstractmethod
    async def search_fts(
        self,
        query: str,
        k: int,
    ) -> List[SearchResult]:
        """
        Searches the full text index for the given query.
        """
        pass

    @abstractmethod
    async def search_vector(
        self,
        vector: List[float],
        k: int,
        distance_type: SimilarityMetric,
    ) -> List[SearchResult]:
        """
        Searches using vector similarity.
        """
        pass

    @abstractmethod
    async def search_hybrid(
        self,
        query: str,
        vector: List[float],
        k: int,
        distance_type: SimilarityMetric,
    ) -> List[SearchResult]:
        """
        Searches using hybrid search.
        """
        pass

    @abstractmethod
    async def count_records(self) -> int:
        """
        Counts the number of records in the index.
        """
        pass

    @abstractmethod
    async def optimize(self) -> None:
        """
        Some stores may have a way to force process the index (e.g. compacting, merging, etc.)
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Closes the collection and releases any resources, if applicable.
        """
        pass
