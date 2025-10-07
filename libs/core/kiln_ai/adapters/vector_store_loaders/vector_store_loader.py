import asyncio
from typing import AsyncGenerator, List

from llama_index.core.schema import TextNode

from kiln_ai.adapters.rag.deduplication import (
    deduplicate_chunk_embeddings,
    deduplicate_chunked_documents,
    deduplicate_extractions,
)
from kiln_ai.adapters.vector_store.lancedb_helpers import (
    convert_to_llama_index_node,
    deterministic_chunk_id,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig


class VectorStoreLoader:
    """
    Class for loading data as LlamaIndex Nodes.
    """

    def __init__(
        self,
        project: Project,
        rag_config: RagConfig,
    ):
        self.project = project
        self.rag_config = rag_config

    async def iter_llama_index_nodes(
        self, batch_size: int = 100
    ) -> AsyncGenerator[List[TextNode], None]:
        """Returns a generator of documents with their corresponding chunks and embeddings."""
        batch: List[TextNode] = []
        for document in self.project.documents():
            await asyncio.sleep(0)
            for extraction in deduplicate_extractions(document.extractions()):
                if (
                    extraction.extractor_config_id
                    != self.rag_config.extractor_config_id
                ):
                    continue
                for chunked_document in deduplicate_chunked_documents(
                    extraction.chunked_documents()
                ):
                    if (
                        chunked_document.chunker_config_id
                        != self.rag_config.chunker_config_id
                    ):
                        continue
                    for chunk_embeddings in deduplicate_chunk_embeddings(
                        chunked_document.chunk_embeddings()
                    ):
                        if (
                            chunk_embeddings.embedding_config_id
                            != self.rag_config.embedding_config_id
                        ):
                            continue

                        document_id = str(document.id)
                        chunks_text = await chunked_document.load_chunks_text()
                        embeddings = chunk_embeddings.embeddings
                        if len(chunks_text) != len(embeddings):
                            raise ValueError(
                                f"Chunk text/embedding count mismatch for document {document_id}: "
                                f"{len(chunks_text)} texts vs {len(embeddings)} embeddings"
                            )

                        for chunk_idx, (chunk_text, chunk_embeddings) in enumerate(
                            zip(chunks_text, embeddings)
                        ):
                            batch.append(
                                convert_to_llama_index_node(
                                    document_id=document_id,
                                    chunk_idx=chunk_idx,
                                    node_id=deterministic_chunk_id(
                                        document_id, chunk_idx
                                    ),
                                    text=chunk_text,
                                    vector=chunk_embeddings.vector,
                                )
                            )

                            if len(batch) >= batch_size:
                                yield batch
                                batch = []

        if batch:
            yield batch
