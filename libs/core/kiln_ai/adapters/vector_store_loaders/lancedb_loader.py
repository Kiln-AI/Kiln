from typing import AsyncGenerator

from llama_index.core.schema import TextNode
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from kiln_ai.adapters.vector_store.lancedb_helpers import (
    convert_to_llama_index_node,
    deterministic_chunk_id,
)
from kiln_ai.adapters.vector_store_loaders.base_vector_store_loader import (
    BaseVectorStoreLoader,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig


class LanceDBLoader(BaseVectorStoreLoader):
    def __init__(
        self,
        project: Project,
        rag_config: RagConfig,
        vector_store_config: VectorStoreConfig,
        lancedb_vector_store: LanceDBVectorStore,
    ):
        self.project = project
        self.rag_config = rag_config
        self.lancedb_vector_store = lancedb_vector_store
        self.vector_store_config = vector_store_config

    async def iter_llama_index_nodes(self) -> AsyncGenerator[TextNode, None]:
        for doc in self.iter_docs_with_chunks(self.project, self.rag_config):
            chunks_text = await doc.chunked_document.load_chunks_text()
            embeddings = doc.chunk_embeddings.embeddings
            if len(chunks_text) != len(embeddings):
                raise ValueError(
                    f"Chunk text/embedding count mismatch for document {doc.document_id}: "
                    f"{len(chunks_text)} texts vs {len(embeddings)} embeddings"
                )
            for chunk_idx, (chunk_text, embedding) in enumerate(
                zip(chunks_text, embeddings)
            ):
                yield convert_to_llama_index_node(
                    document_id=doc.document_id,
                    chunk_idx=chunk_idx,
                    node_id=deterministic_chunk_id(doc.document_id, chunk_idx),
                    text=chunk_text,
                    vector=embedding.vector,
                )

    async def insert_nodes(
        self,
        nodes: list[TextNode],
        flush_batch_size: int = 100,
    ) -> None:
        for i in range(0, len(nodes), flush_batch_size):
            batch = nodes[i : i + flush_batch_size]
            await self.lancedb_vector_store.async_add(batch)
