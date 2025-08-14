import logging
import uuid
from typing import List, Tuple

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    CollectionInfo,
    Distance,
    Document,
    HnswConfigDiff,
    Modifier,
    PointStruct,
    SparseVectorParams,
    VectorParams,
)

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
from kiln_ai.datamodel.vector_store import QdrantVectorIndexMetric

logger = logging.getLogger(__name__)


class QdrantAdapter(BaseVectorStoreAdapter):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
        client: AsyncQdrantClient,
    ):
        super().__init__(vector_store_config)
        self.client = client
        self.config_properties = self.vector_store_config.qdrant_typed_properties()

    async def create_collection(self, rag_config: RagConfig, vector_dimensions: int):
        # TODO: check that it throws an error if the collection already exists
        operation_result = await self.client.create_collection(
            self.table_name_for_rag_config(rag_config),
            vectors_config={
                "chunk_embeddings": VectorParams(
                    size=vector_dimensions,
                    distance=Distance(self.config_properties.distance),
                    hnsw_config=HnswConfigDiff(
                        m=self.config_properties.hnsw_m,
                        ef_construct=self.config_properties.hnsw_ef_construction,
                        payload_m=self.config_properties.hnsw_payload_m,
                    ),
                )
            },
            sparse_vectors_config={"bm25": SparseVectorParams(modifier=Modifier.IDF)},
        )

        if not operation_result:
            raise RuntimeError(
                f"Failed to create collection {self.table_name_for_rag_config(rag_config)}"
            )

        qdrant_collection = await self.client.get_collection(
            self.table_name_for_rag_config(rag_config)
        )

        return QdrantCollection(
            vector_store_config=self.vector_store_config,
            qdrant_collection=qdrant_collection,
            collection_name=self.table_name_for_rag_config(rag_config),
            client=self.client,
            distance_type=self.config_properties.distance,
        )

    async def collection(
        self,
        rag_config: RagConfig,
    ) -> "QdrantCollection":
        qdrant_collection = await self.client.get_collection(
            self.table_name_for_rag_config(rag_config)
        )
        return QdrantCollection(
            vector_store_config=self.vector_store_config,
            qdrant_collection=qdrant_collection,
            collection_name=self.table_name_for_rag_config(rag_config),
            client=self.client,
            distance_type=self.config_properties.distance,
        )

    async def destroy_collection(self, rag_config: RagConfig):
        await self.client.delete_collection(self.table_name_for_rag_config(rag_config))

    def table_name_for_rag_config(self, rag_config: RagConfig) -> str:
        return f"rag_config_{rag_config.id}"


class QdrantCollection(BaseVectorStoreCollection):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
        qdrant_collection: CollectionInfo,
        collection_name: str,
        client: AsyncQdrantClient,
        distance_type: QdrantVectorIndexMetric,
    ):
        super().__init__(vector_store_config)
        self.qdrant_collection = qdrant_collection
        self.collection_name = collection_name
        self.client = client
        # distance type is set in the config of the collection itself, so we cannot query
        # using a different distance type after the collection is created
        self.distance_type = distance_type

    def id_for_chunk(self, document_id: str, chunk_idx: int) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}::{chunk_idx}"))

    async def execute_upserts(self, batch: List[PointStruct]):
        await self.client.upsert(
            collection_name=self.collection_name,
            points=batch,
        )

    async def upsert_chunks(
        self,
        chunks: List[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ):
        # bm25_embedding_model = SparseTextEmbedding("Qdrant/bm25")
        batch_size = 100
        batch: List[PointStruct] = []
        for document_id, chunked_document, chunk_embeddings in chunks:
            chunk_texts = await chunked_document.load_chunks_text()

            for chunk_idx, (chunk_text, embedding) in enumerate(
                zip(chunk_texts, chunk_embeddings.embeddings)
            ):
                batch.append(
                    PointStruct(
                        id=self.id_for_chunk(document_id, chunk_idx),
                        vector={
                            "chunk_embeddings": embedding.vector,
                            # what this does under the hood is compute the sparse vector for BM25
                            # which can also be done more explicitly as shown here:
                            # https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search/#embeddings
                            "bm25": Document(text=chunk_text, model="Qdrant/bm25"),
                        },
                        payload={
                            "document_id": document_id,
                            "chunk_idx": chunk_idx,
                            "chunk_text": chunk_text,
                        },
                    )
                )

                if len(batch) >= batch_size:
                    await self.client.upsert(
                        collection_name=self.collection_name,
                        points=batch,
                    )
                    batch.clear()

        if batch:
            await self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
            )

    async def search_fts(self, query: str, k: int):
        hits = await self.client.query_points(
            collection_name=self.collection_name,
            query=Document(text=query, model="Qdrant/bm25"),
            using="bm25",
            limit=k,
        )

        results: List[SearchResult] = []
        for hit in hits.points:
            if not hit.payload:
                raise RuntimeError("Payload is empty")

            document_id = hit.payload.get("document_id")
            if not document_id or not isinstance(document_id, str):
                raise RuntimeError("Document ID is empty")

            chunk_idx = hit.payload.get("chunk_idx")
            if not isinstance(chunk_idx, int):
                raise RuntimeError("Chunk index is empty")

            chunk_text = hit.payload.get("chunk_text")
            if not chunk_text or not isinstance(chunk_text, str):
                raise RuntimeError("Chunk text is empty")

            results.append(
                SearchResult(
                    score=hit.score,
                    document_id=document_id,
                    chunk_idx=chunk_idx,
                    chunk_text=chunk_text,
                )
            )

        return results

    async def search_vector(
        self,
        vector: List[float],
        k: int,
        distance_type: SimilarityMetric,
    ) -> List[SearchResult]:
        qdrant_distance_mapping = {
            "cosine": "Cosine",
            "l2": "Euclid",
            "dot_product": "Dot",
        }
        expected_qdrant_distance = qdrant_distance_mapping.get(distance_type.value)
        if expected_qdrant_distance != self.distance_type.value:
            raise ValueError(
                f"Distance type {distance_type} does not match the distance type of the collection {self.distance_type}"
            )

        hits = await self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=k,
            using="chunk_embeddings",
        )

        results: List[SearchResult] = []
        for scored_point in hits.points:
            score = scored_point.score
            payload = scored_point.payload
            if not payload:
                raise RuntimeError("Payload is empty")

            document_id = payload.get("document_id")
            if not document_id or not isinstance(document_id, str):
                raise RuntimeError("Document ID is empty")

            chunk_idx = payload.get("chunk_idx")
            if not isinstance(chunk_idx, int):
                raise RuntimeError("Chunk index is empty")

            chunk_text = payload.get("chunk_text")
            if not chunk_text or not isinstance(chunk_text, str):
                raise RuntimeError("Chunk text is empty")

            results.append(
                SearchResult(
                    score=score,
                    document_id=document_id,
                    chunk_idx=chunk_idx,
                    chunk_text=chunk_text,
                )
            )

        return results

    async def count_records(self) -> int:
        result = await self.client.count(self.collection_name, exact=True)
        return result.count

    async def optimize(self):
        pass

    async def close(self):
        pass
