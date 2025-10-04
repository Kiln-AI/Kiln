from abc import ABC, abstractmethod
from typing import AsyncGenerator, Generator

from llama_index.core.schema import TextNode

from kiln_ai.adapters.rag.deduplication import (
    deduplicate_chunk_embeddings,
    deduplicate_chunked_documents,
    deduplicate_extractions,
)
from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    DocumentWithChunksAndEmbeddings,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig


class BaseVectorStoreLoader(ABC):
    """
    Base class for loading data into a vector store. Higher-level than the
    BaseVectorStoreAdapter.
    """

    @abstractmethod
    async def iter_llama_index_nodes(self) -> AsyncGenerator[TextNode, None]:
        """Returns a generator of LlamaIndex TextNodes."""
        pass

    @abstractmethod
    async def insert_nodes(
        self,
        nodes: list[TextNode],
        flush_batch_size: int = 100,
    ) -> None:
        """Inserts nodes into the vector store."""
        pass

    def iter_docs_with_chunks(
        self, project: Project, rag_config: RagConfig
    ) -> Generator[DocumentWithChunksAndEmbeddings, None, None]:
        """Returns a generator of documents with their corresponding chunks and embeddings."""
        for document in project.documents():
            for extraction in deduplicate_extractions(document.extractions()):
                if extraction.extractor_config_id != rag_config.extractor_config_id:
                    continue
                for chunk in deduplicate_chunked_documents(
                    extraction.chunked_documents()
                ):
                    if chunk.chunker_config_id != rag_config.chunker_config_id:
                        continue
                    for embedding in deduplicate_chunk_embeddings(
                        chunk.chunk_embeddings()
                    ):
                        if (
                            embedding.embedding_config_id
                            != rag_config.embedding_config_id
                        ):
                            continue

                        yield DocumentWithChunksAndEmbeddings(
                            document_id=str(document.id),
                            chunked_document=chunk,
                            chunk_embeddings=embedding,
                        )
