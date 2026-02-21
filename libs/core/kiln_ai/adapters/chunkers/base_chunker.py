import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from kiln_ai.adapters.chunkers.helpers import clean_up_text
from kiln_ai.datamodel.chunk import ChunkerConfig

logger = logging.getLogger(__name__)


class TextChunk(BaseModel):
    text: str = Field(description="The text of the chunk.")
    page_number: int | None = Field(
        default=None,
        description="The page number (0-indexed) this chunk belongs to. Only set when page_offsets are provided.",
    )


class ChunkingResult(BaseModel):
    chunks: list[TextChunk] = Field(description="The chunks of the text.")


class BaseChunker(ABC):
    """
    Base class for all chunkers.

    Should be subclassed by each chunker.
    """

    def __init__(self, chunker_config: ChunkerConfig):
        self.chunker_config = chunker_config

    async def chunk(
        self, text: str, page_offsets: list[int] | None = None
    ) -> ChunkingResult:
        if not text or not clean_up_text(text):
            return ChunkingResult(chunks=[])

        chunking_result = await self._chunk(text)

        if page_offsets is not None and len(page_offsets) > 0:
            search_start = 0
            for chunk in chunking_result.chunks:
                chunk_start_offset = text.find(chunk.text, search_start)
                if chunk_start_offset == -1:
                    logger.warning(
                        f"Chunk text not found in sanitized text starting from offset {search_start}. "
                        "This may indicate an issue with the chunker implementation."
                    )
                    chunk.page_number = None
                else:
                    page_number = self._find_page_number(
                        chunk_start_offset, page_offsets
                    )
                    chunk.page_number = page_number
                    search_start = chunk_start_offset + 1

        return chunking_result

    def _find_page_number(
        self, chunk_offset: int, page_offsets: list[int]
    ) -> int | None:
        """
        Find the page number for a chunk at the given offset.

        Returns the page number (0-indexed) that the chunk belongs to,
        or None if the offset is before the first page.
        """
        if not page_offsets:
            return None

        if chunk_offset < page_offsets[0]:
            return 0

        for i in range(len(page_offsets) - 1, -1, -1):
            if chunk_offset >= page_offsets[i]:
                return i

        return None

    @abstractmethod
    async def _chunk(self, text: str) -> ChunkingResult:
        pass
