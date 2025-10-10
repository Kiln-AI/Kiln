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

    def _build_embedding_model(self, chunker_config: ChunkerConfig) -> BaseEmbedding:
        embedding_config_id = chunker_config.embedding_config_id()
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

    def __init__(self, chunker_config: ChunkerConfig):
        if chunker_config.chunker_type != ChunkerType.SEMANTIC:
            raise ValueError("Chunker type must be SEMANTIC")

        super().__init__(chunker_config)

        self.embed_model = self._build_embedding_model(chunker_config)

        buffer_size = chunker_config.buffer_size()
        if buffer_size is None:
            raise ValueError("buffer_size must be set for semantic chunker")

        breakpoint_percentile_threshold = (
            chunker_config.breakpoint_percentile_threshold()
        )
        if breakpoint_percentile_threshold is None:
            raise ValueError(
                "breakpoint_percentile_threshold must be set for semantic chunker"
            )

        include_metadata = chunker_config.include_metadata()
        if include_metadata is None:
            raise ValueError("include_metadata must be set for semantic chunker")

        include_prev_next_rel = chunker_config.include_prev_next_rel()
        if include_prev_next_rel is None:
            raise ValueError("include_prev_next_rel must be set for semantic chunker")

        self.semantic_splitter = SemanticSplitterNodeParser(
            embed_model=self.embed_model,
            buffer_size=buffer_size,
            breakpoint_percentile_threshold=breakpoint_percentile_threshold,
            include_metadata=include_metadata,
            include_prev_next_rel=include_prev_next_rel,
        )

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
