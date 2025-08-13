import logging
from typing import List, Sequence, Tuple

from weaviate import WeaviateAsyncClient
from weaviate.collections import CollectionAsync
from weaviate.collections.classes.data import DataObject
from weaviate.collections.classes.grpc import MetadataQuery
from weaviate.collections.classes.internal import ReferenceInputs
from weaviate.collections.classes.types import WeaviateProperties
from weaviate.util import generate_uuid5

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


class WeaviateAdapter(BaseVectorStoreAdapter):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
        client: WeaviateAsyncClient,
    ):
        super().__init__(vector_store_config)
        self.client = client
        self.config_properties = self.vector_store_config.weaviate_typed_properties()

    async def create_collection(self, rag_config: RagConfig, vector_dimensions: int):
        weaviate_collection = await self.client.collections.create(
            name=self.table_name_for_rag_config(rag_config),
        )
        return WeaviateCollection(
            vector_store_config=self.vector_store_config,
            weaviate_collection=weaviate_collection,
        )

    async def collection(
        self,
        rag_config: RagConfig,
    ) -> "WeaviateCollection":
        weaviate_collection = self.client.collections.get(
            name=self.table_name_for_rag_config(rag_config)
        )
        return WeaviateCollection(
            vector_store_config=self.vector_store_config,
            weaviate_collection=weaviate_collection,
        )

    async def destroy_collection(self, rag_config: RagConfig):
        await self.client.collections.delete(
            name=self.table_name_for_rag_config(rag_config)
        )

    def table_name_for_rag_config(self, rag_config: RagConfig) -> str:
        return f"rag_config_{rag_config.id}"


class WeaviateCollection(BaseVectorStoreCollection):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
        weaviate_collection: CollectionAsync,
    ):
        super().__init__(vector_store_config)
        self.weaviate_collection = weaviate_collection

    def id_for_chunk(self, document_id: str, chunk_idx: int) -> str:
        return f"{document_id}::{chunk_idx}"

    async def upsert_chunks(
        self,
        chunks: List[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ):
        # weaviate has a batching API, but it is not available in the async client, only synchronous one
        batch_size = 100
        for document_id, chunked_document, chunk_embeddings in chunks:
            chunk_texts = await chunked_document.load_chunks_text()

            batch: Sequence[
                WeaviateProperties
                | DataObject[WeaviateProperties, ReferenceInputs | None]
            ] = []
            for chunk_idx, (chunk_text, embedding) in enumerate(
                zip(chunk_texts, chunk_embeddings.embeddings)
            ):
                batch.append(
                    DataObject(
                        properties={
                            "document_id": document_id,
                            "chunk_idx": chunk_idx,
                            "chunk_text": chunk_text,
                        },
                        vector=embedding.vector,
                        # TODO: check that mapping from string to uuid does not risk collisions
                        uuid=generate_uuid5(self.id_for_chunk(document_id, chunk_idx)),
                    )
                )

                if len(batch) >= batch_size:
                    await self.weaviate_collection.data.insert_many(batch)
                    batch = []

        if len(batch) > 0:
            await self.weaviate_collection.data.insert_many(batch)

    async def search_fts(self, query: str, k: int) -> List[SearchResult]:
        weaviate_results = await self.weaviate_collection.query.bm25(
            query=query,
            limit=k,
            return_metadata=MetadataQuery(score=True),
        )

        results: List[SearchResult] = []
        for result in weaviate_results.objects:
            properties = result.properties
            document_id = properties.get("document_id")
            if not isinstance(document_id, str):
                raise ValueError(f"document_id is not a string: {document_id}")
            chunk_idx = properties.get("chunk_idx")
            if not isinstance(chunk_idx, int):
                raise ValueError(f"chunk_idx is not an int: {chunk_idx}")
            chunk_text = properties.get("chunk_text")
            if not isinstance(chunk_text, str):
                raise ValueError(f"chunk_text is not a string: {chunk_text}")
            score = result.metadata.score
            if not isinstance(score, float):
                raise ValueError(f"score is not a float: {score}")
            results.append(
                SearchResult(
                    document_id=document_id,
                    chunk_idx=chunk_idx,
                    chunk_text=chunk_text,
                    score=score,
                )
            )

        return results

    async def search_vector(
        self,
        vector: list[float | int],
        k: int,
        distance_type: SimilarityMetric,
    ):
        weaviate_results = await self.weaviate_collection.query.near_vector(
            target_vector=["query_vector"],
            near_vector={
                "query_vector": vector,
            },
            limit=k,
            return_metadata=MetadataQuery(distance=True),
        )

        results: List[SearchResult] = []
        for result in weaviate_results.objects:
            properties = result.properties
            document_id = properties.get("document_id")
            if not isinstance(document_id, str):
                raise ValueError(f"document_id is not a string: {document_id}")
            chunk_idx = properties.get("chunk_idx")
            if not isinstance(chunk_idx, int):
                raise ValueError(f"chunk_idx is not an int: {chunk_idx}")
            chunk_text = properties.get("chunk_text")
            if not isinstance(chunk_text, str):
                raise ValueError(f"chunk_text is not a string: {chunk_text}")
            results.append(
                SearchResult(
                    document_id=document_id,
                    chunk_idx=chunk_idx,
                    chunk_text=chunk_text,
                    score=result.metadata.score,
                )
            )
        return results

    async def count_records(self) -> int:
        aggregate_result = await self.weaviate_collection.aggregate.over_all(
            total_count=True
        )
        return aggregate_result.total_count or 0

    async def optimize(self):
        # no such operation needed for weaviate
        pass

    async def close(self):
        # TODO: resource is managed by the client, we need to close the client
        pass
