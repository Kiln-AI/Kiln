"""Custom embedding model wrapper for semantic chunker."""

from typing import List

from llama_index.core.embeddings import BaseEmbedding

from kiln_ai.adapters.embedding.base_embedding_adapter import BaseEmbeddingAdapter
from kiln_ai.datamodel.embedding import EmbeddingConfig


class KilnEmbeddingWrapper(BaseEmbedding):
    """Wrapper around BaseEmbeddingAdapter to make it compatible with llama_index BaseEmbedding."""

    def __init__(self, embedding_adapter: BaseEmbeddingAdapter):
        super().__init__()
        # Store the adapter as a private attribute to avoid Pydantic validation issues
        self._embedding_adapter = embedding_adapter

    def _get_query_embedding(self, query: str) -> List[float]:
        """Get query embedding synchronously."""
        raise NotImplementedError("Use async methods instead")

    def _get_text_embedding(self, text: str) -> List[float]:
        """Get text embedding synchronously."""
        raise NotImplementedError("Use async methods instead")

    def _get_text_embedding_batch(self, texts: List[str]) -> List[List[float]]:
        """Get text embeddings batch synchronously."""
        raise NotImplementedError("Use async methods instead")

    async def _aget_query_embedding(self, query: str) -> List[float]:
        """Get query embedding asynchronously."""
        result = await self._embedding_adapter.generate_embeddings([query])
        if not result.embeddings:
            raise ValueError("No embeddings returned from adapter")
        return result.embeddings[0].vector

    async def _aget_text_embedding(self, text: str) -> List[float]:
        """Get text embedding asynchronously."""
        result = await self._embedding_adapter.generate_embeddings([text])
        if not result.embeddings:
            raise ValueError("No embeddings returned from adapter")
        return result.embeddings[0].vector

    async def _aget_text_embedding_batch(self, texts: List[str]) -> List[List[float]]:
        """Get text embeddings batch asynchronously."""
        result = await self._embedding_adapter.generate_embeddings(texts)
        return [embedding.vector for embedding in result.embeddings]


def create_embedding_wrapper(
    model_provider: str, model_provider_name: str
) -> KilnEmbeddingWrapper:
    """Create an embedding wrapper from model provider information."""
    from kiln_ai.adapters.embedding.embedding_registry import (
        embedding_adapter_from_type,
    )
    from kiln_ai.datamodel.datamodel_enums import ModelProviderName

    # Create a minimal embedding config for the adapter
    embedding_config = EmbeddingConfig(
        name="semantic_chunker_embedding",
        model_name=model_provider,
        model_provider_name=ModelProviderName(model_provider_name),
        properties={},
    )

    # Get the embedding adapter
    embedding_adapter = embedding_adapter_from_type(embedding_config)

    return KilnEmbeddingWrapper(embedding_adapter)
