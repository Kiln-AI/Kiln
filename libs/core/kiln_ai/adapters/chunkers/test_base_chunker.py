from unittest.mock import patch

import pytest

from kiln_ai.adapters.chunkers.base_chunker import (
    BaseChunker,
    ChunkingResult,
    TextChunk,
)
from kiln_ai.adapters.chunkers.helpers import clean_up_text
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType


@pytest.fixture
def config() -> ChunkerConfig:
    return ChunkerConfig(
        name="test-chunker",
        chunker_type=ChunkerType.FIXED_WINDOW,
        properties={
            "chunker_type": ChunkerType.FIXED_WINDOW,
            "chunk_size": 100,
            "chunk_overlap": 10,
        },
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


async def test_base_chunker_calls_clean_up_text(chunker: WhitespaceChunker):
    with patch(
        "kiln_ai.adapters.chunkers.base_chunker.clean_up_text"
    ) as mock_clean_up_text:
        mock_clean_up_text.side_effect = clean_up_text
        await chunker.chunk("Hello, world!")
        mock_clean_up_text.assert_called_once_with("Hello, world!")


async def test_base_chunker_empty_text(chunker: WhitespaceChunker):
    chunks = await chunker.chunk("")
    assert chunks == ChunkingResult(chunks=[])


async def test_base_chunker_empty_text_after_clean_up(chunker: WhitespaceChunker):
    with patch(
        "kiln_ai.adapters.chunkers.base_chunker.clean_up_text"
    ) as mock_clean_up_text:
        mock_clean_up_text.side_effect = clean_up_text
        chunks = await chunker.chunk("\n\n   ")
        mock_clean_up_text.assert_called_once_with("\n\n   ")
        assert chunks == ChunkingResult(chunks=[])
