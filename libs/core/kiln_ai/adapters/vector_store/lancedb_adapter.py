import json
import logging
from typing import List, Tuple

import lancedb
from lancedb import AsyncConnection, AsyncTable
from lancedb.index import FTS, HnswSq
from lancedb.pydantic import LanceModel, Vector

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
from kiln_ai.datamodel.vector_store import LanceDBVectorIndexType

logger = logging.getLogger(__name__)


class LanceDBAdapter(BaseVectorStoreAdapter):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
        connection: AsyncConnection,
    ):
        super().__init__(vector_store_config)
        self.connection = connection
        self.config_properties = self.vector_store_config.lancedb_typed_properties()

    def schema(self, vector_dimensions: int) -> type[LanceModel]:
        """
        LanceDB has different ways of defining the schema for a table. If using Pydantic / LanceModel,
        make sure to mark the fields as lancedb.Optional[type] otherwise upsert throws an error.
        See: https://discord.com/channels/1030247538198061086/1197630499926057021/1404511576060592210
        """

        class ChunkLanceDBSchema(LanceModel):
            id: lancedb.Optional[str]
            vector: lancedb.Optional[Vector(dim=vector_dimensions, nullable=False)]  # type: ignore
            text: lancedb.Optional[str]

        return ChunkLanceDBSchema

    async def create_hnsw_index(self, table: AsyncTable):
        count = await table.count_rows()
        if count == 0:
            logger.warning(f"Table {table.name} is empty, skipping HNSW index creation")
            return

        # many more options: https://lancedb.github.io/lancedb/js/interfaces/HnswSqOptions/
        kwargs = {}
        if self.config_properties.hnsw_distance_type:
            kwargs["distance_type"] = self.config_properties.hnsw_distance_type
        if self.config_properties.hnsw_m:
            kwargs["m"] = self.config_properties.hnsw_m
        if self.config_properties.hnsw_ef_construction:
            kwargs["ef_construction"] = self.config_properties.hnsw_ef_construction

        await table.create_index(
            "vector",
            # another option is to use HnswPQ - Scalar Quantization (SQ) is the simpler one
            # https://lancedb.github.io/lancedb/js/interfaces/HnswSqOptions/
            # https://lancedb.github.io/lancedb/js/interfaces/HnswPqOptions/
            config=HnswSq(**kwargs),
            replace=True,
        )

    async def create_collection(self, rag_config: RagConfig, vector_dimensions: int):
        """
        Create a table for the given RagConfig and return a collection adapter.
        Replaces the table if it already exists.
        """
        table_name = self.table_name_for_rag_config(rag_config=rag_config)

        table = await self.connection.create_table(
            name=table_name,
            exist_ok=True,
            schema=self.schema(vector_dimensions),
            # we overwrite the table if it already exists
            mode="overwrite",
        )

        # many options for preprocessing the text (stemming, tokenization, etc.):
        # https://lancedb.github.io/lancedb/fts/#tokenization
        await table.create_index("text", config=FTS())

        if self.config_properties.vector_index_type == LanceDBVectorIndexType.HNSW:
            await self.create_hnsw_index(table)
        else:
            # by default, when we don't create a specific index, LanceDB uses bruteforce KNN search
            pass

        # create_table also opens the table so we don't need to do it separately
        return LanceDBCollection(self.vector_store_config, table)

    async def collection(
        self,
        rag_config: RagConfig,
    ) -> "LanceDBCollection":
        """
        Open the table for the given RagConfig and return a collection adapter.
        Raises an error if the table does not exist.
        """
        table = await self.connection.open_table(
            self.table_name_for_rag_config(rag_config=rag_config)
        )

        return LanceDBCollection(self.vector_store_config, table)

    async def destroy_collection(self, rag_config: RagConfig):
        table_name = self.table_name_for_rag_config(rag_config=rag_config)
        await self.connection.drop_table(table_name)

    def table_name_for_rag_config(self, rag_config: RagConfig) -> str:
        return f"rag_config_{rag_config.id}"


class LanceDBCollection(BaseVectorStoreCollection):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
        table: AsyncTable,
    ):
        super().__init__(vector_store_config)
        self.table = table

    async def chunks_to_records(
        self,
        chunks: List[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ) -> List[dict]:
        records = []
        for document_id, chunked_document, chunk_embeddings in chunks:
            chunk_texts = await chunked_document.load_chunks_text()
            for chunk_id, (chunk_text, embedding) in enumerate(
                zip(chunk_texts, chunk_embeddings.embeddings)
            ):
                records.append(
                    {
                        "id": f"{document_id}_{chunk_id}",
                        "vector": embedding.vector,
                        "text": chunk_text,
                    }
                )

        return records

    async def upsert_chunks(
        self,
        chunks: List[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ):
        records = await self.chunks_to_records(chunks)
        await (
            self.table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(records)
        )

        # this should not be needed, unclear if bug or feature, but if we don't
        # do this here, FTS search after an upsert raises an error
        await self.table.create_index("text", config=FTS(), replace=False)

    def map_to_search_results(self, results: List[dict]) -> List[SearchResult]:
        search_results: List[SearchResult] = []
        for result in results:
            document_id = result["id"].split("_")[0]
            chunk_idx = int(result["id"].split("_")[1])
            chunk_text = result["text"]
            # LanceDB returns _distance for vector search and _score for FTS search
            score = result.get("_distance", None) or result.get("_score", -1)
            search_results.append(
                SearchResult(
                    document_id=document_id,
                    chunk_idx=chunk_idx,
                    chunk_text=chunk_text,
                    score=score,
                )
            )
        return search_results

    async def search_fts(self, query: str, k: int):
        results = (
            await (
                await self.table.search(query, query_type="fts", fts_columns=["text"])
            )
            .limit(k)
            .to_list()
        )

        return self.map_to_search_results(results)

    async def search_vector(
        self,
        vector: List[float],
        k: int,
        distance_type: SimilarityMetric,
    ) -> List[SearchResult]:
        results = (
            await (await self.table.search(vector))
            .distance_type(distance_type)
            .limit(k)
            .to_list()
        )

        return self.map_to_search_results(results)

    async def count_records(self) -> int:
        return await self.table.count_rows()

    async def optimize(self):
        await self.table.optimize()

    async def close(self):
        if self.table.is_open():
            try:
                self.table.close()
            except Exception as e:
                logger.error(
                    f"Error closing table {self.table.name}: {e}", exc_info=True
                )
