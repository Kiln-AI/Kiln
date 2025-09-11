from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from pydantic import BaseModel, Field

from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig


@dataclass
class DocumentWithChunksAndEmbeddings:
    document_id: str
    chunked_document: ChunkedDocument
    chunk_embeddings: ChunkEmbeddings

    @property
    def chunks(self) -> list[Chunk]:
        return self.chunked_document.chunks

    @property
    def embeddings(self) -> list[Embedding]:
        return self.chunk_embeddings.embeddings


class SearchResult(BaseModel):
    document_id: str = Field(description="The id of the Kiln document.")
    chunk_idx: int = Field(description="The index of the chunk.")
    chunk_text: str = Field(description="The text of the chunk.")
    similarity: float | None = Field(
        description="The score of the chunk, which depends on the similarity metric used."
    )


class VectorStoreQuery(BaseModel):
    query_string: Optional[str] = Field(
        description="The query string to search for.",
        default=None,
    )
    query_embedding: Optional[List[float]] = Field(
        description="The embedding of the query.",
        default=None,
    )


class BaseVectorStoreAdapter(ABC):
    def __init__(self, rag_config: RagConfig, vector_store_config: VectorStoreConfig):
        self.vector_store_config = vector_store_config
        self.rag_config = rag_config

    @abstractmethod
    async def add_chunks_with_embeddings(
        self,
        doc_batch: list[DocumentWithChunksAndEmbeddings],
    ) -> None:
        pass

    @abstractmethod
    async def search(self, query: VectorStoreQuery) -> List[SearchResult]:
        pass

    @abstractmethod
    async def count_records(self) -> int:
        pass

    @abstractmethod
    async def destroy(self) -> None:
        pass
