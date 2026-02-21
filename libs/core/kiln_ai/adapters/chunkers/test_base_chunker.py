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


async def test_base_chunker_checks_clean_up_text_for_empty(chunker: WhitespaceChunker):
    """Test that clean_up_text is still called to check if text becomes empty."""
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
    chunks = await chunker.chunk("\n\n   ")
    assert chunks == ChunkingResult(chunks=[])


async def test_base_chunker_page_number_without_offsets(chunker: WhitespaceChunker):
    """Test that page_number is None when page_offsets are not provided."""
    output = await chunker.chunk("Hello world test")
    assert len(output.chunks) == 3
    for chunk in output.chunks:
        assert chunk.page_number is None


async def test_base_chunker_page_number_with_offsets(chunker: WhitespaceChunker):
    """Test that page_number is correctly assigned when page_offsets are provided."""
    text = "Page0 content here Page1 content here Page2 content here"
    page_offsets = [0, 20, 40]

    output = await chunker.chunk(text, page_offsets=page_offsets)

    assert len(output.chunks) == 9
    assert output.chunks[0].text == "Page0"
    assert output.chunks[0].page_number == 0

    assert output.chunks[1].text == "content"
    assert output.chunks[1].page_number == 0

    assert output.chunks[2].text == "here"
    assert output.chunks[2].page_number == 0


async def test_base_chunker_page_number_multiple_pages(chunker: WhitespaceChunker):
    """Test page number assignment across multiple pages."""
    text = (
        "Start of page 0. " * 10 + "Start of page 1. " * 10 + "Start of page 2. " * 10
    )
    page_offsets = [0, 160, 320]

    output = await chunker.chunk(text, page_offsets=page_offsets)

    assert len(output.chunks) > 0

    search_start = 0
    for chunk in output.chunks:
        chunk_offset = text.find(chunk.text, search_start)
        if chunk_offset == -1:
            # Chunk text not found, skip validation
            continue
        search_start = chunk_offset + 1

        if chunk_offset < 160:
            assert chunk.page_number == 0, (
                f"Chunk '{chunk.text}' at offset {chunk_offset} should be page 0"
            )
        elif chunk_offset < 320:
            assert chunk.page_number == 1, (
                f"Chunk '{chunk.text}' at offset {chunk_offset} should be page 1"
            )
        else:
            assert chunk.page_number == 2, (
                f"Chunk '{chunk.text}' at offset {chunk_offset} should be page 2"
            )


async def test_base_chunker_page_number_edge_cases(chunker: WhitespaceChunker):
    """Test edge cases for page number calculation."""
    text = "Test content"

    # Empty page_offsets
    output = await chunker.chunk(text, page_offsets=[])
    for chunk in output.chunks:
        assert chunk.page_number is None

    # Single page
    output = await chunker.chunk(text, page_offsets=[0])
    for chunk in output.chunks:
        assert chunk.page_number == 0

    # Chunk at exact page boundary
    text = "Page0" + " " * 15 + "Page1"
    page_offsets = [0, 20]
    output = await chunker.chunk(text, page_offsets=page_offsets)
    for chunk in output.chunks:
        chunk_offset = text.find(chunk.text)
        if chunk_offset < 20:
            assert chunk.page_number == 0
        else:
            assert chunk.page_number == 1


async def test_find_page_number_method(chunker: WhitespaceChunker):
    """Test the _find_page_number helper method directly."""
    page_offsets = [0, 100, 200]

    # Test various offsets
    assert chunker._find_page_number(0, page_offsets) == 0
    assert chunker._find_page_number(50, page_offsets) == 0
    assert chunker._find_page_number(99, page_offsets) == 0
    assert chunker._find_page_number(100, page_offsets) == 1
    assert chunker._find_page_number(150, page_offsets) == 1
    assert chunker._find_page_number(199, page_offsets) == 1
    assert chunker._find_page_number(200, page_offsets) == 2
    assert chunker._find_page_number(250, page_offsets) == 2

    # Test edge cases
    assert chunker._find_page_number(-10, page_offsets) == 0
    assert chunker._find_page_number(1000, page_offsets) == 2

    # Test empty offsets
    assert chunker._find_page_number(50, []) is None

    # Test single page
    assert chunker._find_page_number(0, [0]) == 0
    assert chunker._find_page_number(100, [0]) == 0
