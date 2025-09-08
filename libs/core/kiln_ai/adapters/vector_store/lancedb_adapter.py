import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Literal, Tuple

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import (
    BaseNode,
    NodeRelationship,
    RelatedNodeInfo,
    TextNode,
)
from llama_index.core.vector_stores.types import (
    VectorStoreQuery,
    VectorStoreQueryResult,
)
from llama_index.vector_stores.lancedb import LanceDBVectorStore
from llama_index.vector_stores.lancedb.base import TableNotFoundError

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
from kiln_ai.utils.uuid import string_to_uuid

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
            mode="create",
            uri=LanceDBAdapter.lancedb_path_for_config(rag_config),
            query_type=self.query_type,
            overfetch_factor=vector_store_config.lancedb_properties.overfetch_factor,
            vector_column_name=vector_store_config.lancedb_properties.vector_column_name,
            text_key=vector_store_config.lancedb_properties.text_key,
            doc_id_key=vector_store_config.lancedb_properties.doc_id_key,
            **kwargs,
        )

        self._index = None

    @property
    def index(self) -> VectorStoreIndex:
        if self._index is not None:
            return self._index

        storage_context = StorageContext.from_defaults(
            vector_store=self.lancedb_vector_store
        )

        # FIXME:
        # embed_model=None should be valid and result in llama_index initializing it
        # to a mock (like it does elsewhere) but there is a fallback in the
        # VectorStoreIndex constructor that overrides None with "default"
        # and tries to load OpenAI and throws if the OPENAI_API_KEY is not set
        # maybe should open an issue on their repo
        if "OPENAI_API_KEY" not in os.environ:
            os.environ["OPENAI_API_KEY"] = "dummy"

        # - VectorStoreIndex is a wrapper around a vector store
        # it exposes higher level operations (that rely on internal
        # fields like ref_doc_id); make sure implementation mirrors
        # the upstream llama_index logic that we do not use
        # - Make sure you do not initialize the VectorStoreIndex before
        # having data in the underlying vector store, otherwise downstream
        # operations will fail due to schema mismatch
        self._index = VectorStoreIndex(
            [],
            storage_context=storage_context,
            embed_model=None,
        )

        return self._index

    async def delete_nodes_by_document_id(self, document_id: str) -> None:
        # higher level operation that requires ref_doc_id to be set on the nodes
        # which is set through the source node relationship
        try:
            self.index.delete_ref_doc(document_id)
        except TableNotFoundError:
            # Table doesn't exist yet, so there's nothing to delete
            logger.debug(
                f"Table not found while deleting nodes for document {document_id}, which is expected if the table does not exist yet"
            )

    async def get_nodes_by_ids(self, node_ids: List[str]) -> List[BaseNode]:
        try:
            chunk_ids_in_database = await self.lancedb_vector_store.aget_nodes(
                node_ids=node_ids
            )
            return chunk_ids_in_database
        except TableNotFoundError:
            logger.warning(
                "Table not found while getting nodes by ids, which may be expected if the table does not exist yet",
            )
            return []

    async def add_chunks_with_embeddings(
        self,
        records: list[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
        nodes_batch_size: int = 100,
    ) -> None:
        if len(records) == 0:
            return

        node_batch: List[TextNode] = []
        for document_id, chunked_document, chunk_embeddings in records:
            if len(chunk_embeddings.embeddings) != len(chunked_document.chunks):
                raise RuntimeError(
                    f"Number of embeddings ({len(chunk_embeddings.embeddings)}) does not match number of chunks ({len(chunked_document.chunks)}) for document {document_id}"
                )

            chunk_count_for_document = len(chunked_document.chunks)
            deterministic_chunk_ids = [
                self.compute_deterministic_chunk_id(document_id, chunk_idx)
                for chunk_idx in range(chunk_count_for_document)
            ]

            # check if the chunk ids are already in the database
            chunk_ids_in_database = await self.get_nodes_by_ids(deterministic_chunk_ids)

            # we already have all the chunks for this document in the database
            if len(chunk_ids_in_database) == chunk_count_for_document:
                # free up event loop to avoid risk of looping for a long time
                # without any real async ops releasing the event loop at all
                # (get_nodes_by_ids implementation in llama_index is actually sync
                # and it is slow)
                await asyncio.sleep(0)
                continue
            else:
                # the chunks are different, which is because either:
                # - an upstream sync conflict caused multiple chunked documents to be created and the incoming one
                # is different; we need to delete all the chunks for this document otherwise there can be lingering stale chunks
                # that are not in the incoming batch if current is longer than incoming
                # - an incomplete indexing of this same chunked doc, upserting is enough to overwrite the current chunked doc fully
                await self.delete_nodes_by_document_id(document_id)

            chunks_text = await chunked_document.load_chunks_text()
            for chunk_idx, (chunk_text, embedding) in enumerate(
                zip(chunks_text, chunk_embeddings.embeddings)
            ):
                node_batch.append(
                    TextNode(
                        id_=deterministic_chunk_ids[chunk_idx],
                        text=chunk_text,
                        embedding=embedding.vector,
                        metadata={
                            # metadata is populated by some internal llama_index logic
                            # that uses for example the source_node relationship
                            "kiln_doc_id": document_id,
                            "kiln_chunk_idx": chunk_idx,
                            #
                            # llama_index lancedb vector store automatically sets these metadata:
                            # "doc_id": "UUID node_id of the Source Node relationship",
                            # "document_id": "UUID node_id of the Source Node relationship",
                            # "ref_doc_id": "UUID node_id of the Source Node relationship"
                            #
                            # llama_index file loaders set these metadata, which would be useful to also support:
                            # "creation_date": "2025-09-03",
                            # "file_name": "file.pdf",
                            # "file_path": "/absolute/path/to/the/file.pdf",
                            # "file_size": 395154,
                            # "file_type": "application\/pdf",
                            # "last_modified_date": "2025-09-03",
                            # "page_label": "1",
                        },
                        relationships={
                            # when using the llama_index loaders, llama_index groups Nodes under Documents
                            # and relationships point to the Document (which is also a Node), which confusingly
                            # enough does not map to an actual file (for a PDF, a Document is a page of the PDF)
                            # the Document structure is not something that is persisted, so it is fine here
                            # if we have a relationship to a node_id that does not exist in the db
                            NodeRelationship.SOURCE: RelatedNodeInfo(
                                node_id=document_id,
                                node_type="1",
                                metadata={},
                            ),
                        },
                    )
                )

                if len(node_batch) >= nodes_batch_size:
                    # async_add is currently not async, LanceDB has an async API but
                    # llama_index does not use it, so it is synchronous and blocking
                    # avoid calling with too many nodes at once
                    await self.lancedb_vector_store.async_add(node_batch)
                    node_batch.clear()

            await asyncio.sleep(0)

        if node_batch:
            await self.lancedb_vector_store.async_add(node_batch)
            node_batch.clear()

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
        for _, node, similarity in zip(
            query_result.ids or [],
            query_result.nodes or [],
            query_result.similarities or [],
        ):
            if node.metadata is None:
                raise ValueError("node.metadata must not be None")
            document_id = node.metadata.get("kiln_doc_id")
            if document_id is None:
                raise ValueError("node.metadata.kiln_doc_id must not be None")
            chunk_idx = node.metadata.get("kiln_chunk_idx")
            if chunk_idx is None:
                raise ValueError("node.metadata.kiln_chunk_idx must not be None")
            results.append(
                SearchResult(
                    document_id=document_id,
                    chunk_idx=chunk_idx,
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

    def compute_deterministic_chunk_id(self, document_id: str, chunk_idx: int) -> str:
        # the id_ of the Node must be a UUID string, otherwise llama_index / LanceDB fails downstream
        return str(string_to_uuid(f"{document_id}::{chunk_idx}"))

    async def count_records(self) -> int:
        try:
            table = self.lancedb_vector_store.table
            if table is None:
                raise ValueError("Table is not initialized")
            count = table.count_rows()
            return count
        except TableNotFoundError:
            return 0

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
