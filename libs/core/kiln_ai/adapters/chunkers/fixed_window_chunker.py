from typing import List

from llama_index.core.text_splitter import SentenceSplitter

from kiln_ai.adapters.chunkers.base_chunker import BaseChunker, Chunk, ChunkOutput
from kiln_ai.datamodel.chunk import ChunkerConfig


class FixedWindowChunker(BaseChunker):
    def __init__(self, chunker_config: ChunkerConfig):
        super().__init__(chunker_config)
        self.splitter = SentenceSplitter(
            chunk_size=self.chunker_config.properties.chunk_size,
            chunk_overlap=self.chunker_config.properties.chunk_overlap,
        )

    async def _chunk(self, text: str) -> ChunkOutput:
        sentences = self.splitter.split_text(text)

        chunks: List[Chunk] = []
        for sentence in sentences:
            chunks.append(Chunk(text=sentence))

        return ChunkOutput(chunks=chunks)
