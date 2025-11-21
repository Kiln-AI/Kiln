import asyncio
from typing import TYPE_CHECKING, List

from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.core.dependencies import optional_import

if TYPE_CHECKING:
    from llama_index.core.embeddings import BaseEmbedding
else:
    llama_index = optional_import("llama_index.core", "rag")
    BaseEmbedding = llama_index.embeddings.BaseEmbedding


class KilnEmbeddingWrapper(BaseEmbedding):
    """Wrapper around BaseEmbeddingAdapter to make it compatible with llama_index BaseEmbedding."""

    def __init__(self, embedding_adapter: BaseEmbeddingAdapter):
        super().__init__()
        self._semaphore = asyncio.Semaphore(10)
        self._embedding_adapter = embedding_adapter

    def _get_query_embedding(self, query: str) -> List[float]:
        raise NotImplementedError("Use async methods instead")

    def _get_text_embedding(self, text: str) -> List[float]:
        raise NotImplementedError("Use async methods instead")

    def _get_text_embedding_batch(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError("Use async methods instead")

    async def _aget_query_embedding(self, query: str) -> List[float]:
        # we do not need this for semantic chunking, which currently is the only use case for this wrapper
        raise NotImplementedError("Not implemented")

    async def _aget_text_embedding(self, text: str) -> List[float]:
        # llama_index only ever calls this one (not the batch one) during semantic chunking
        async with self._semaphore:
            result = await self._embedding_adapter.generate_embeddings([text])
            if not result.embeddings:
                raise ValueError("No embeddings returned from adapter")
            return result.embeddings[0].vector

    async def _aget_text_embedding_batch(self, texts: List[str]) -> List[List[float]]:
        async with self._semaphore:
            result = await self._embedding_adapter.generate_embeddings(texts)
            # this should not happen if the embedding adapter is properly implemented
            if len(result.embeddings) != len(texts):
                raise ValueError(
                    f"Expected {len(texts)} embeddings but got {len(result.embeddings)}"
                )
            return [embedding.vector for embedding in result.embeddings]
