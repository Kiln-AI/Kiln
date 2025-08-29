from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.vector_store import VectorStoreConfig


class SearchResult(BaseModel):
    document_id: str = Field(description="The id of the Kiln document.")
    chunk_text: str = Field(description="The text of the chunk.")
    similarity: float | None = Field(
        description="The score of the chunk, which depends on the similarity metric used."
    )


class KilnVectorStoreQuery(BaseModel):
    query_string: Optional[str] = Field(
        description="The query string to search for.",
        default=None,
    )
    query_embedding: Optional[List[float]] = Field(
        description="The embedding of the query.",
        default=None,
    )


class BaseVectorStoreAdapter(ABC):
    def __init__(self, vector_store_config: VectorStoreConfig):
        self.vector_store_config = vector_store_config

    @abstractmethod
    async def add_chunks_with_embeddings(
        self,
        records: list[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ) -> None:
        pass

    @abstractmethod
    async def delete_chunks_by_document_id(self, document_id: str) -> None:
        pass

    @abstractmethod
    async def search(self, query: KilnVectorStoreQuery) -> List[SearchResult]:
        pass

    @abstractmethod
    async def get_all_chunks(self) -> List[SearchResult]:
        pass

    @abstractmethod
    async def count_records(self) -> int:
        pass
