import asyncio
import logging
import shutil
from pathlib import Path
from typing import List, Literal, Optional, Set, TypedDict

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import BaseNode, TextNode
from llama_index.core.vector_stores.types import (
    VectorStoreQuery as LlamaIndexVectorStoreQuery,
)
from llama_index.core.vector_stores.types import VectorStoreQueryResult
from llama_index.vector_stores.lancedb import LanceDBVectorStore
from llama_index.vector_stores.lancedb.base import TableNotFoundError

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    DocumentWithChunksAndEmbeddings,
    SearchResult,
    VectorStoreQuery,
)
from kiln_ai.adapters.vector_store.lancedb_helpers import (
    convert_to_llama_index_node,
    deterministic_chunk_id,
    lancedb_construct_from_config,
    store_type_to_lancedb_query_type,
)
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig
from kiln_ai.utils.config import Config
from kiln_ai.utils.env import temporary_env
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_ai.utils.lock import AsyncLockManager

table_lock_manager = AsyncLockManager()

logger = logging.getLogger(__name__)


class LanceDBAdapterQueryKwargs(TypedDict):
    similarity_top_k: int
    query_str: Optional[str]
    query_embedding: Optional[List[float]]


class LanceDBAdapter(BaseVectorStoreAdapter):
    def __init__(
        self,
        rag_config: RagConfig,
        vector_store_config: VectorStoreConfig,
        lancedb_vector_store: LanceDBVectorStore | None = None,
    ):
        super().__init__(rag_config, vector_store_config)

        # allow overriding the vector store with a custom one, useful for user loading into an arbitrary
        # deployment
        self.lancedb_vector_store = (
            lancedb_vector_store
            or lancedb_construct_from_config(
                vector_store_config,
                uri=LanceDBAdapter.lancedb_path_for_config(rag_config),
            )
        )
        self._index = None

    @property
    def index(self) -> VectorStoreIndex:
        """
        - VectorStoreIndex is a wrapper around the underlying LanceDBVectorStore.
        It exposes higher level operations, and you need to make sure our
        implementation mirrors the upstream llama_index logic that it expects to have available (e.g. ref_doc_id)
        - VectorStoreIndex throws on initialization if the underlying vector store is empty due to schema mismatch;
        make sure there is data in the underlying vector store before calling this
        """
        if self._index is not None:
            return self._index

        storage_context = StorageContext.from_defaults(
            vector_store=self.lancedb_vector_store
        )

        # embed_model=None in the constructor should initialize the embed model to a mock
        # like it does elsewhere in llama_index. However, that is not happening for VectorStoreIndex
        # because the constructor overrides None with "default" and tries to load OpenAI and
        # expects OPENAI_API_KEY to be set
        #
        # Since our own implementation does not actually use OpenAI, we set a fake API key just to
        # avoid the error
        with temporary_env("OPENAI_API_KEY", "fake-api-key"):
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
        doc_batch: list[DocumentWithChunksAndEmbeddings],
        nodes_batch_size: int = 100,
    ) -> None:
        if len(doc_batch) == 0:
            return

        node_batch: List[TextNode] = []
        for doc in doc_batch:
            document_id = doc.document_id
            chunks = doc.chunks
            embeddings = doc.embeddings

            # the lancedb vector store implementation is sync (even though it has an async API)
            # so we sleep to avoid blocking the event loop - that allows other async ops to run
            await asyncio.sleep(0)

            if len(embeddings) != len(chunks):
                raise RuntimeError(
                    f"Number of embeddings ({len(embeddings)}) does not match number of chunks ({len(chunks)}) for document {document_id}"
                )

            chunk_count_for_document = len(chunks)
            deterministic_chunk_ids = [
                deterministic_chunk_id(document_id, chunk_idx)
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
                continue
            else:
                # the chunks are different, which is because either:
                # - an upstream sync conflict caused multiple chunked documents to be created and the incoming one
                # is different; we need to delete all the chunks for this document otherwise there can be lingering stale chunks
                # that are not in the incoming batch if current is longer than incoming
                # - an incomplete indexing of this same chunked doc, upserting is enough to overwrite the current chunked doc fully
                await self.delete_nodes_by_document_id(document_id)

            chunks_text = await doc.chunked_document.load_chunks_text()
            for chunk_idx, (chunk_text, embedding) in enumerate(
                zip(chunks_text, embeddings)
            ):
                node_batch.append(
                    convert_to_llama_index_node(
                        document_id=document_id,
                        chunk_idx=chunk_idx,
                        node_id=deterministic_chunk_id(document_id, chunk_idx),
                        text=chunk_text,
                        vector=embedding.vector,
                    )
                )

                if len(node_batch) >= nodes_batch_size:
                    # async_add is currently not async, LanceDB has an async API but
                    # llama_index does not use it, so it is synchronous and blocking
                    # avoid calling with too many nodes at once
                    await self.lancedb_vector_store.async_add(node_batch)
                    node_batch.clear()

        if node_batch:
            await self.lancedb_vector_store.async_add(node_batch)
            node_batch.clear()

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
            and len(query_result.nodes) == 0
            and len(query_result.similarities) == 0
        ):
            return []

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

    def build_kwargs_for_query(
        self, query: VectorStoreQuery
    ) -> LanceDBAdapterQueryKwargs:
        similarity_top_k = self.vector_store_config.properties.get("similarity_top_k")
        kwargs: LanceDBAdapterQueryKwargs = {
            "similarity_top_k": similarity_top_k,
            "query_str": None,
            "query_embedding": None,
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

    async def search(self, query: VectorStoreQuery) -> List[SearchResult]:
        try:
            if self.lancedb_vector_store.table is None:
                raise ValueError("Table is not initialized")

            # llama_index implementation create the FTS index on query if it does not exist
            async with table_lock_manager.acquire(self.lancedb_vector_store.table.name):
                query_result = await self.lancedb_vector_store.aquery(
                    LlamaIndexVectorStoreQuery(
                        **self.build_kwargs_for_query(query),
                    ),
                    query_type=self.query_type,
                )
                return self.format_query_result(query_result)
        except TableNotFoundError as e:
            logger.info("Vector store search returned no results: %s", e)
            return []
        except Warning as e:
            msg = str(e).lower()
            if ("query results are empty" in msg) or (
                "empty" in msg and "result" in msg
            ):
                logger.warning("Vector store search returned no results: %s", e)
                return []
            raise

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
        return store_type_to_lancedb_query_type(self.vector_store_config.store_type)

    @staticmethod
    def lancedb_path_for_config(rag_config: RagConfig) -> str:
        data_dir = Path(Config.settings_dir())
        if rag_config.id is None:
            raise ValueError("Vector store config ID is required")
        return str(data_dir / "rag_indexes" / "lancedb" / rag_config.id)

    async def destroy(self) -> None:
        lancedb_path = LanceDBAdapter.lancedb_path_for_config(self.rag_config)
        shutil.rmtree(lancedb_path)

    async def delete_nodes_not_in_set(self, document_ids: Set[str]) -> None:
        tbl = self.lancedb_vector_store.table
        if tbl is None:
            raise ValueError("Table is not initialized")

        for batch in tbl.search().to_batches(100):
            batch = batch.to_pandas()

            rows_to_delete = []
            for _, row in batch.iterrows():
                kiln_doc_id = row["metadata"]["kiln_doc_id"]
                if kiln_doc_id not in document_ids:
                    kiln_chunk_idx = row["metadata"]["kiln_chunk_idx"]
                    record_id = deterministic_chunk_id(kiln_doc_id, kiln_chunk_idx)
                    rows_to_delete.append(record_id)

            if rows_to_delete:
                self.lancedb_vector_store.delete_nodes(rows_to_delete)
