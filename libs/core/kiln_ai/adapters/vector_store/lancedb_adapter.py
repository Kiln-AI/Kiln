import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Literal, Tuple

from llama_index.core.schema import TextNode
from llama_index.core.vector_stores.types import (
    VectorStoreQuery,
    VectorStoreQueryResult,
)
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    KilnVectorStoreQuery,
    SearchResult,
)
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import (
    VectorStoreConfig,
    VectorStoreType,
    raise_exhaustive_enum_error,
)
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)


class LanceDBAdapter(BaseVectorStoreAdapter):
    def __init__(
        self,
        rag_config: RagConfig,
        vector_store_config: VectorStoreConfig,
    ):
        super().__init__(rag_config, vector_store_config)
        self.config_properties = self.vector_store_config.lancedb_properties

        kwargs: Dict[str, Any] = {}
        if vector_store_config.lancedb_properties.nprobes is not None:
            kwargs["nprobes"] = vector_store_config.lancedb_properties.nprobes

        self.lancedb_vector_store = LanceDBVectorStore(
            uri=LanceDBAdapter.lancedb_path_for_config(rag_config),
            query_type=self.query_type,
            overfetch_factor=vector_store_config.lancedb_properties.overfetch_factor,
            vector_column_name=vector_store_config.lancedb_properties.vector_column_name,
            text_key=vector_store_config.lancedb_properties.text_key,
            doc_id_key=vector_store_config.lancedb_properties.doc_id_key,
            **kwargs,
        )

    def hash_node(
        self, text: str, embedding: list[float], document_id: str, chunk_idx: int
    ) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "text": text,
                    "embedding": embedding,
                    "kiln_doc_id": document_id,
                    "kiln_chunk_idx": chunk_idx,
                }
            ).encode()
        ).hexdigest()

    async def add_chunks_with_embeddings(
        self,
        records: list[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
    ) -> None:
        nodes: List[TextNode] = []
        for document_id, chunked_document, chunk_embeddings in records:
            # Get text content from each chunk in the document
            chunks_text = await chunked_document.load_chunks_text()

            for chunk_idx, (chunk_text, embedding) in enumerate(
                zip(chunks_text, chunk_embeddings.embeddings)
            ):
                node_hash = self.hash_node(
                    chunk_text, embedding.vector, document_id, chunk_idx
                )

                nodes.append(
                    TextNode(
                        text=chunk_text,
                        embedding=embedding.vector,
                        metadata={
                            "kiln_doc_id": document_id,
                            "kiln_chunk_idx": chunk_idx,
                            "kiln_node_hash": node_hash,
                        },
                    )
                )
        await self.lancedb_vector_store.async_add(nodes)

        table = self.lancedb_vector_store.table
        if table is None:
            raise ValueError("Table is not initialized")

        table.optimize()

    def format_query_result(
        self, query_result: VectorStoreQueryResult
    ) -> List[SearchResult]:
        if (
            query_result.ids is None
            or query_result.nodes is None
            or query_result.similarities is None
        ):
            raise ValueError("ids, nodes, and similarities must not be None")
        if not (
            len(query_result.ids)
            == len(query_result.nodes)
            == len(query_result.similarities)
        ):
            raise ValueError("ids, nodes, and similarities must have the same length")

        results = []
        for id, node, similarity in zip(
            query_result.ids or [],
            query_result.nodes or [],
            query_result.similarities or [],
        ):
            results.append(
                SearchResult(
                    document_id=id,
                    chunk_idx=node.metadata["kiln_chunk_idx"],
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
            case "fts":
                if query.query_string is None:
                    raise ValueError("query_string must be provided for fts search")
                kwargs["query_str"] = query.query_string
            case "hybrid":
                if query.query_embedding is None or query.query_string is None:
                    raise ValueError(
                        "query_string and query_embedding must be provided for hybrid search"
                    )
                kwargs["query_embedding"] = query.query_embedding
                kwargs["query_str"] = query.query_string
            case "vector":
                if not query.query_embedding:
                    raise ValueError(
                        "query_embedding must be provided for vector search"
                    )
                kwargs["query_embedding"] = query.query_embedding
            case _:
                raise_exhaustive_enum_error(self.query_type)
        return kwargs

    async def search(self, query: KilnVectorStoreQuery) -> List[SearchResult]:
        query_result = await self.lancedb_vector_store.aquery(
            VectorStoreQuery(
                **self.build_kwargs_for_query(query),
            ),
            query_type=self.query_type,
        )
        return self.format_query_result(query_result)

    async def count_records(self) -> int:
        # this throws a TableNotFoundError if the table doesn't exist
        table = self.lancedb_vector_store.table
        if table is None:
            raise ValueError("Table is not initialized")
        table.optimize()
        count = table.count_rows()
        return count

    @property
    def query_type(self) -> Literal["fts", "hybrid", "vector"]:
        match self.vector_store_config.store_type:
            case VectorStoreType.LANCE_DB_FTS:
                return "fts"
            case VectorStoreType.LANCE_DB_HYBRID:
                return "hybrid"
            case VectorStoreType.LANCE_DB_VECTOR:
                return "vector"
            case _:
                raise_exhaustive_enum_error(self.vector_store_config.store_type)

    @staticmethod
    def lancedb_path_for_config(rag_config: RagConfig) -> str:
        data_dir = Path(Config.settings_dir())
        if rag_config.id is None:
            raise ValueError("Vector store config ID is required")
        return str(data_dir / "rag_indexes" / "lancedb" / rag_config.id)

    async def destroy(self) -> None:
        lancedb_path = LanceDBAdapter.lancedb_path_for_config(self.rag_config)
        shutil.rmtree(lancedb_path)
