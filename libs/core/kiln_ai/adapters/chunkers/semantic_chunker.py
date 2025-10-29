from typing import List

from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.core.schema import Document

from kiln_ai.adapters.chunkers.base_chunker import (
    BaseChunker,
    ChunkingResult,
    TextChunk,
)
from kiln_ai.adapters.chunkers.embedding_wrapper import KilnEmbeddingWrapper
from kiln_ai.adapters.embedding.embedding_registry import embedding_adapter_from_type
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType
from kiln_ai.datamodel.embedding import EmbeddingConfig


class SemanticChunker(BaseChunker):
    """Semantic chunker that groups semantically related sentences together."""

    def __init__(self, chunker_config: ChunkerConfig):
        if chunker_config.chunker_type != ChunkerType.SEMANTIC:
            raise ValueError("Chunker type must be SEMANTIC")

        super().__init__(chunker_config)

        self.embed_model = self._build_embedding_model(chunker_config)
        self.properties = chunker_config.semantic_properties

        self.semantic_splitter = SemanticSplitterNodeParser(
            embed_model=self.embed_model,
            buffer_size=self.properties["buffer_size"],
            breakpoint_percentile_threshold=self.properties[
                "breakpoint_percentile_threshold"
            ],
            include_metadata=self.properties["include_metadata"],
            include_prev_next_rel=self.properties["include_prev_next_rel"],
        )

    def _build_embedding_model(self, chunker_config: ChunkerConfig) -> BaseEmbedding:
        properties = chunker_config.semantic_properties
        embedding_config_id = properties["embedding_config_id"]
        if embedding_config_id is None:
            raise ValueError("embedding_config_id must be set for semantic chunker")

        parent_project = chunker_config.parent_project()
        if parent_project is None or parent_project.path is None:
            raise ValueError("SemanticChunker requires parent project")

        embedding_config = EmbeddingConfig.from_id_and_parent_path(
            embedding_config_id, parent_project.path
        )
        if embedding_config is None:
            raise ValueError(f"Embedding config not found for id {embedding_config_id}")

        embedding_adapter = embedding_adapter_from_type(embedding_config)
        return KilnEmbeddingWrapper(embedding_adapter)

    async def _chunk(self, text: str) -> ChunkingResult:
        document = Document(text=text)

        nodes = await self.semantic_splitter.abuild_semantic_nodes_from_documents(
            [document],
        )

        chunks: List[TextChunk] = []
        for node in nodes:
            text_content = node.get_content()
            chunks.append(TextChunk(text=text_content))

        return ChunkingResult(chunks=chunks)
