"""Semantic chunker implementation using llama_index SemanticSplitterNodeParser."""

from typing import List

from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.core.schema import Document

from kiln_ai.adapters.chunkers.base_chunker import (
    BaseChunker,
    ChunkingResult,
    TextChunk,
)
from kiln_ai.adapters.chunkers.embedding_wrapper import create_embedding_wrapper
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType


class SemanticChunker(BaseChunker):
    """Semantic chunker that groups semantically related sentences together."""

    def __init__(self, chunker_config: ChunkerConfig):
        if chunker_config.chunker_type != ChunkerType.SEMANTIC:
            raise ValueError("Chunker type must be SEMANTIC")

        model_provider = chunker_config.model_provider()
        if model_provider is None:
            raise ValueError("Model provider must be set")

        model_provider_name = chunker_config.model_provider_name()
        if model_provider_name is None:
            raise ValueError("Model provider name must be set")

        super().__init__(chunker_config)

        # Create the embedding wrapper
        self.embed_model = create_embedding_wrapper(model_provider, model_provider_name)

        # Create the semantic splitter with defaults for optional properties
        self.semantic_splitter = SemanticSplitterNodeParser(
            embed_model=self.embed_model,
            buffer_size=chunker_config.buffer_size() or 1,
            breakpoint_percentile_threshold=int(
                chunker_config.breakpoint_percentile_threshold() or 95
            ),
            include_metadata=chunker_config.include_metadata() or True,
            include_prev_next_rel=chunker_config.include_prev_next_rel() or True,
        )

    async def _chunk(self, text: str) -> ChunkingResult:
        """Chunk text using semantic splitting."""
        # Create a document from the text
        document = Document(text=text)

        # Use the semantic splitter to create nodes
        nodes = self.semantic_splitter.build_semantic_nodes_from_documents([document])

        # Convert nodes to TextChunk objects
        chunks: List[TextChunk] = []
        for node in nodes:
            # Get text content from the node
            text_content = node.get_content()
            chunks.append(TextChunk(text=text_content))

        return ChunkingResult(chunks=chunks)
