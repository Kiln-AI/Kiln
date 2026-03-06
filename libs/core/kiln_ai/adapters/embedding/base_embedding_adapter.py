import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import List

from litellm import Usage
from pydantic import BaseModel, Field

from kiln_ai.datamodel.embedding import EmbeddingConfig

logger = logging.getLogger(__name__)


class EmbeddingContext(str, Enum):
    """
    Context for embedding generation.

    Determines whether instructions should be applied to the input texts.
    Instructions are only applied for query search, not for document indexing
    or semantic chunking.
    """

    DOCUMENT_INDEXING = "document_indexing"
    QUERY_SEARCH = "query_search"
    SEMANTIC_CHUNKING = "semantic_chunking"


class Embedding(BaseModel):
    vector: list[float] = Field(description="The vector of the embedding.")


class EmbeddingResult(BaseModel):
    embeddings: list[Embedding] = Field(description="The embeddings of the text.")

    usage: Usage | None = Field(default=None, description="The usage of the embedding.")


class BaseEmbeddingAdapter(ABC):
    """
    Base class for all embedding adapters.

    Should be subclassed by each embedding adapter.
    """

    def __init__(self, embedding_config: EmbeddingConfig):
        self.embedding_config = embedding_config

    async def generate_embeddings(
        self,
        input_texts: List[str],
        context: EmbeddingContext = EmbeddingContext.DOCUMENT_INDEXING,
    ) -> EmbeddingResult:
        if not input_texts:
            return EmbeddingResult(
                embeddings=[],
                usage=None,
            )

        apply_instructions = self._should_apply_instructions(context)
        return await self._generate_embeddings(input_texts, apply_instructions)

    def _should_apply_instructions(self, context: EmbeddingContext) -> bool:
        """
        Determine whether instructions should be applied based on context.

        By default, instructions are only applied for QUERY_SEARCH context.
        Subclasses can override this to add model-specific checks (e.g., supports_instructions).
        """
        return context == EmbeddingContext.QUERY_SEARCH

    @abstractmethod
    async def _generate_embeddings(
        self, input_texts: List[str], apply_embedding_instructions: bool
    ) -> EmbeddingResult:
        pass
