from typing import List

from llama_index.core.text_splitter import SentenceSplitter

from kiln_ai.adapters.chunkers.base_chunker import (
    BaseChunker,
    ChunkingResult,
    TextChunk,
)
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType


class FixedWindowChunker(BaseChunker):
    def __init__(self, chunker_config: ChunkerConfig):
        if chunker_config.chunker_type != ChunkerType.FIXED_WINDOW:
            raise ValueError("Chunker type must be FIXED_WINDOW")

        chunk_size = chunker_config.chunk_size()
        if chunk_size is None:
            raise ValueError("Chunk size must be set")

        chunk_overlap = chunker_config.chunk_overlap()
        if chunk_overlap is None:
            raise ValueError("Chunk overlap must be set")

        super().__init__(chunker_config)
        self.splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    async def _chunk(self, text: str) -> ChunkingResult:
        sentences = self.splitter.split_text(text)

        chunks: List[TextChunk] = []
        for sentence in sentences:
            chunks.append(TextChunk(text=sentence))

        return ChunkingResult(chunks=chunks)
