import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    KilnVectorStoreQuery,
    SearchResult,
)
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.vector_store import (
    LanceDBQueryType,
    VectorStoreConfig,
    VectorStoreType,
    raise_exhaustive_enum_error,
)
from kiln_ai.utils.config import Config
from llama_index.core.schema import MetadataMode, TextNode
from llama_index.core.vector_stores.types import (
    VectorStoreQuery,
    VectorStoreQueryResult,
)
from llama_index.vector_stores.lancedb import LanceDBVectorStore
from llama_index.vector_stores.lancedb.base import TableNotFoundError

logger = logging.getLogger(__name__)


class LanceDBAdapter(BaseVectorStoreAdapter):
    def __init__(
        self,
        vector_store_config: VectorStoreConfig,
        lancedb_vector_store: LanceDBVectorStore,
    ):
        super().__init__(vector_store_config)
        self.lancedb_vector_store = lancedb_vector_store
        self.config_properties = self.vector_store_config.lancedb_properties

    async def add_chunks_with_embeddings(
        self,
        records: list[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ) -> None:
        nodes: List[TextNode] = []
        for document_id, chunked_document, chunk_embeddings in records:
            # Get text content from each chunk in the document
            chunks_text = await chunked_document.load_chunks_text()

            for chunk_text, embedding in zip(chunks_text, chunk_embeddings.embeddings):
                nodes.append(
                    TextNode(
                        text=chunk_text,
                        embedding=embedding.vector,
                        metadata={
                            "ref_doc_id": document_id,
                        },
                    )
                )
        await self.lancedb_vector_store.async_add(nodes)

    def format_query_result(
        self, query_result: VectorStoreQueryResult
    ) -> List[SearchResult]:
        # Handle case where no results are found - return empty list
        if (
            query_result.ids is None
            or query_result.nodes is None
            or query_result.similarities is None
        ):
            # If any of the fields are None (which shouldn't happen normally),
            # return empty results instead of raising an error
            return []

        # If all fields exist but are empty lists, that's a valid empty result
        if (
            len(query_result.ids) == 0
            or len(query_result.nodes) == 0
            or len(query_result.similarities) == 0
        ):
            return []

        if not (
            len(query_result.ids)
            == len(query_result.nodes)
            == len(query_result.similarities)
        ):
            raise ValueError("ids, nodes, and similarities must have the same length")

        results = []
        for id, node, similarity in zip(
            query_result.ids,
            query_result.nodes,
            query_result.similarities,
        ):
            results.append(
                SearchResult(
                    document_id=id,
                    chunk_text=node.get_content(),
                    similarity=similarity,
                )
            )
        return results

    def build_kwargs_for_query(self, query: KilnVectorStoreQuery) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "similarity_top_k": self.config_properties.similarity_top_k,
        }

        match self.query_type:
            case LanceDBQueryType.FTS:
                if query.query_string is None:
                    raise ValueError("query_string must be provided for fts search")
                kwargs["query_str"] = query.query_string
            case LanceDBQueryType.HYBRID:
                if query.query_embedding is None or query.query_string is None:
                    raise ValueError(
                        "query_string and query_embedding must be provided for hybrid search"
                    )
                kwargs["query_embedding"] = query.query_embedding
                kwargs["query_str"] = query.query_string
            case LanceDBQueryType.VECTOR:
                if not query.query_embedding:
                    raise ValueError(
                        "query_embedding must be provided for vector search"
                    )
                kwargs["query_embedding"] = query.query_embedding
            case _:
                raise_exhaustive_enum_error(self.query_type)
        return kwargs

    async def search(self, query: KilnVectorStoreQuery) -> List[SearchResult]:
        try:
            query_result = await self.lancedb_vector_store.aquery(
                VectorStoreQuery(
                    **self.build_kwargs_for_query(query),
                ),
                query_type=self.query_type,
            )
            return self.format_query_result(query_result)
        except (TableNotFoundError, Exception) as e:
            # Handle various error conditions that can occur with empty or non-existent tables
            error_msg = str(e).lower()
            if (
                isinstance(e, TableNotFoundError)
                or "query results are empty" in error_msg
                or "table is not initialized" in error_msg
                or "table does not exist" in error_msg
                or "no data" in error_msg
                or "empty" in error_msg
            ):
                # Return empty results instead of propagating the error
                logger.info(f"Vector store search returned no results: {e}")
                return []
            else:
                # Re-raise other errors
                raise

    async def get_all_chunks(self) -> List[SearchResult]:
        nodes = self.lancedb_vector_store.get_nodes()
        return [
            SearchResult(
                document_id=node.metadata["ref_doc_id"],
                chunk_text=node.get_content(MetadataMode.NONE),
                similarity=None,
            )
            for node in nodes
        ]

    async def count_records(self) -> int:
        # this throws a TableNotFoundError if the table doesn't exist
        table = self.lancedb_vector_store.table
        if table is None:
            raise ValueError("Table is not initialized")
        return table.count_rows()

    @property
    def query_type(self) -> LanceDBQueryType:
        return LanceDBAdapter.lancedb_query_type_for_config(self.vector_store_config)

    @staticmethod
    def lancedb_query_type_for_config(
        vector_store_config: VectorStoreConfig,
    ) -> LanceDBQueryType:
        match vector_store_config.store_type:
            case VectorStoreType.LANCE_DB_FTS:
                return LanceDBQueryType.FTS
            case VectorStoreType.LANCE_DB_HYBRID:
                return LanceDBQueryType.HYBRID
            case VectorStoreType.LANCE_DB_VECTOR:
                return LanceDBQueryType.VECTOR
            case _:
                raise_exhaustive_enum_error(vector_store_config.store_type)

    @staticmethod
    def lancedb_path_for_config(vector_store_config: VectorStoreConfig) -> str:
        data_dir = Config.shared().local_data_dir()
        if isinstance(data_dir, str):
            data_dir = Path(data_dir)
        if vector_store_config.id is None:
            raise ValueError("Vector store config ID is required")
        return str(data_dir / "lancedb" / vector_store_config.id)
        return str(data_dir / "lancedb" / vector_store_config.id)
        return str(data_dir / "lancedb" / vector_store_config.id)
