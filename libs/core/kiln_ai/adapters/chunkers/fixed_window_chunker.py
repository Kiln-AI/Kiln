"""
Fixed window chunker for splitting text into chunks.

This module requires the 'rag' optional dependencies:
    pip install kiln-ai[rag]
"""

from typing import List

from kiln_ai.adapters.chunkers.base_chunker import (
    BaseChunker,
    ChunkingResult,
    TextChunk,
)
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType
from kiln_ai.utils.optional_deps import lazy_import


class FixedWindowChunker(BaseChunker):
    def __init__(self, chunker_config: ChunkerConfig):
        if chunker_config.chunker_type != ChunkerType.FIXED_WINDOW:
            raise ValueError("Chunker type must be FIXED_WINDOW")

        super().__init__(chunker_config)

        text_splitter = lazy_import("llama_index.core.text_splitter", "rag")
        self.splitter = text_splitter.SentenceSplitter(
            chunk_size=chunker_config.fixed_window_properties["chunk_size"],
            chunk_overlap=chunker_config.fixed_window_properties["chunk_overlap"],
        )

    async def _chunk(self, text: str) -> ChunkingResult:
        sentences = self.splitter.split_text(text)

        chunks: List[TextChunk] = []
        for sentence in sentences:
            chunks.append(TextChunk(text=sentence))

        return ChunkingResult(chunks=chunks)
