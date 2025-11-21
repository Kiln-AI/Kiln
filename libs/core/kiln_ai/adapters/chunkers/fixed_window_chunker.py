from typing import TYPE_CHECKING, List

from kiln_ai.adapters.chunkers.base_chunker import (
    BaseChunker,
    ChunkingResult,
    TextChunk,
)
from kiln_ai.core.dependencies import optional_import
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType

if TYPE_CHECKING:
    from llama_index.core.text_splitter import SentenceSplitter
else:
    llama_index = optional_import("llama_index.core", "rag")
    SentenceSplitter = llama_index.text_splitter.SentenceSplitter


class FixedWindowChunker(BaseChunker):
    def __init__(self, chunker_config: ChunkerConfig):
        if chunker_config.chunker_type != ChunkerType.FIXED_WINDOW:
            raise ValueError("Chunker type must be FIXED_WINDOW")

        super().__init__(chunker_config)
        self.splitter = SentenceSplitter(
            chunk_size=chunker_config.fixed_window_properties["chunk_size"],
            chunk_overlap=chunker_config.fixed_window_properties["chunk_overlap"],
        )

    async def _chunk(self, text: str) -> ChunkingResult:
        sentences = self.splitter.split_text(text)

        chunks: List[TextChunk] = []
        for sentence in sentences:
            chunks.append(TextChunk(text=sentence))

        return ChunkingResult(chunks=chunks)
