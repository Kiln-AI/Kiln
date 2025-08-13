import logging
from typing import List, Tuple

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    BaseVectorStoreCollection,
    SearchResult,
    SimilarityMetric,
    VectorStoreConfig,
)
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.rag import RagConfig

logger = logging.getLogger(__name__)


class FakerAdapter(BaseVectorStoreAdapter):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
    ):
        super().__init__(vector_store_config)
        self.config_properties = self.vector_store_config.weaviate_typed_properties()

    async def create_collection(self, rag_config: RagConfig, vector_dimensions: int):
        raise NotImplementedError("Not implemented")

    async def collection(
        self,
        rag_config: RagConfig,
    ) -> "FakeCollection":
        raise NotImplementedError("Not implemented")

    async def destroy_collection(self, rag_config: RagConfig):
        raise NotImplementedError("Not implemented")

    def table_name_for_rag_config(self, rag_config: RagConfig) -> str:
        raise NotImplementedError("Not implemented")


class FakeCollection(BaseVectorStoreCollection):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
    ):
        super().__init__(vector_store_config)

    def id_for_chunk(self, document_id: str, chunk_idx: int) -> str:
        raise NotImplementedError("Not implemented")

    async def upsert_chunks(
        self,
        chunks: List[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ):
        raise NotImplementedError("Not implemented")

    async def search_fts(self, query: str, k: int) -> List[SearchResult]:
        raise NotImplementedError("Not implemented")

    async def search_vector(
        self,
        vector: list[float | int],
        k: int,
        distance_type: SimilarityMetric,
    ):
        raise NotImplementedError("Not implemented")

    async def count_records(self) -> int:
        raise NotImplementedError("Not implemented")

    async def optimize(self):
        raise NotImplementedError("Not implemented")

    async def close(self):
        raise NotImplementedError("Not implemented")
