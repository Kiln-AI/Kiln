import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from kiln_ai.datamodel.chunk import ChunkerConfig

logger = logging.getLogger(__name__)


class TextChunk(BaseModel):
    text: str = Field(description="The text of the chunk.")


class ChunkingResult(BaseModel):
    chunks: list[TextChunk] = Field(description="The chunks of the text.")


class BaseChunker(ABC):
    """
    Base class for all chunkers.

    Should be subclassed by each chunker.
    """

    def __init__(self, chunker_config: ChunkerConfig):
        self.chunker_config = chunker_config

    async def chunk(self, text: str) -> ChunkingResult:
        if not text:
            return ChunkingResult(chunks=[])

        return await self._chunk(text)

    @abstractmethod
    async def _chunk(self, text: str) -> ChunkingResult:
        pass
