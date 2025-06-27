import pytest

from kiln_ai.adapters.chunkers.base_chunker import (
    BaseChunker,
    ChunkingResult,
    TextChunk,
)
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType


@pytest.fixture
def config() -> ChunkerConfig:
    return ChunkerConfig(
        name="test-chunker",
        chunker_type=ChunkerType.FIXED_WINDOW,
        properties={"chunk_size": 100, "chunk_overlap": 10},
    )


class WhitespaceChunker(BaseChunker):
    async def _chunk(self, text: str) -> ChunkingResult:
        return ChunkingResult(chunks=[TextChunk(text=chunk) for chunk in text.split()])


@pytest.fixture
def chunker(config: ChunkerConfig) -> WhitespaceChunker:
    return WhitespaceChunker(config)


async def test_base_chunker_chunk_empty_text(chunker: WhitespaceChunker):
    assert await chunker.chunk("") == ChunkingResult(chunks=[])


async def test_base_chunker_concrete_chunker(chunker: WhitespaceChunker):
    output = await chunker.chunk("Hello, world!")
    assert len(output.chunks) == 2
