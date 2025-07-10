import logging
from abc import ABC, abstractmethod
from typing import List

from litellm import Usage
from pydantic import BaseModel, Field

from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.embedding import EmbeddingConfig

logger = logging.getLogger(__name__)


class GeneratedEmbedding(BaseModel):
    vector: list[float] = Field(description="The vector of the embedding.")


class EmbeddingResult(BaseModel):
    embeddings: list[GeneratedEmbedding] = Field(
        description="The embeddings of the text."
    )

    usage: Usage | None = Field(default=None, description="The usage of the embedding.")


class BaseEmbeddingAdapter(ABC):
    """
    Base class for all embedding adapters.

    Should be subclassed by each embedding adapter.
    """

    def __init__(self, embedding_config: EmbeddingConfig):
        self.embedding_config = embedding_config

    async def embed(self, text: List[str]) -> EmbeddingResult:
        if not text:
            return EmbeddingResult(
                embeddings=[],
                usage=None,
            )

        return await self._embed(text)

    @abstractmethod
    async def _embed(self, text: List[str]) -> EmbeddingResult:
        pass

    def embedding_config_id(self) -> ID_TYPE:
        return self.embedding_config.id
