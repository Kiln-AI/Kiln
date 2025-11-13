"""Tests for embedding wrapper."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from kiln_ai.adapters.chunkers.embedding_wrapper import KilnEmbeddingWrapper
from kiln_ai.adapters.embedding.base_embedding_adapter import Embedding, EmbeddingResult


@pytest.fixture
def mock_embedding_adapter():
    """Create a mock embedding adapter."""
    adapter = MagicMock()
    adapter.generate_embeddings = AsyncMock()
    return adapter


@pytest.fixture
def embedding_wrapper(mock_embedding_adapter):
    """Create an embedding wrapper with mocked adapter."""
    return KilnEmbeddingWrapper(mock_embedding_adapter)


class TestKilnEmbeddingWrapper:
    """Test the KilnEmbeddingWrapper class."""

    def test_init(self, mock_embedding_adapter):
        """Test initialization."""
        wrapper = KilnEmbeddingWrapper(mock_embedding_adapter)
        assert wrapper._embedding_adapter == mock_embedding_adapter

    @pytest.mark.asyncio
    async def test_aget_text_embedding(self, embedding_wrapper, mock_embedding_adapter):
        """Test async text embedding."""
        # Setup mock
        mock_embedding_adapter.generate_embeddings.return_value = EmbeddingResult(
            embeddings=[Embedding(vector=[0.4, 0.5, 0.6])]
        )

        result = await embedding_wrapper._aget_text_embedding("test text")

        assert result == [0.4, 0.5, 0.6]
        mock_embedding_adapter.generate_embeddings.assert_called_once_with(
            ["test text"]
        )

    @pytest.mark.asyncio
    async def test_aget_text_embedding_batch(
        self, embedding_wrapper, mock_embedding_adapter
    ):
        """Test async text embedding batch."""
        # Setup mock
        mock_embedding_adapter.generate_embeddings.return_value = EmbeddingResult(
            embeddings=[
                Embedding(vector=[0.1, 0.2, 0.3]),
                Embedding(vector=[0.4, 0.5, 0.6]),
            ]
        )

        result = await embedding_wrapper._aget_text_embedding_batch(["text1", "text2"])

        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_embedding_adapter.generate_embeddings.assert_called_once_with(
            ["text1", "text2"]
        )

    def test_get_query_embedding_sync_not_implemented(self, embedding_wrapper):
        """Test synchronous query embedding raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Use async methods instead"):
            embedding_wrapper._get_query_embedding("test query")

    def test_get_text_embedding_sync_not_implemented(self, embedding_wrapper):
        """Test synchronous text embedding raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Use async methods instead"):
            embedding_wrapper._get_text_embedding("test text")

    def test_get_text_embedding_batch_sync_not_implemented(self, embedding_wrapper):
        """Test synchronous text embedding batch raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Use async methods instead"):
            embedding_wrapper._get_text_embedding_batch(["text1", "text2"])

    async def test_aget_query_embedding_not_implemented(self, embedding_wrapper):
        """Test async query embedding not implemented."""
        with pytest.raises(NotImplementedError, match="Not implemented"):
            await embedding_wrapper._aget_query_embedding("q")

    async def test_aget_text_embedding_no_embeddings(
        self, embedding_wrapper, mock_embedding_adapter
    ):
        """Test error when adapter returns no embeddings."""
        mock_embedding_adapter.generate_embeddings.return_value = EmbeddingResult(
            embeddings=[]
        )
        with pytest.raises(ValueError, match="No embeddings returned from adapter"):
            await embedding_wrapper._aget_text_embedding("text")


class TestCreateEmbeddingWrapperFromAdapter:
    """Test the create_embedding_wrapper_from_adapter function."""

    def test_create_embedding_wrapper_from_adapter(self):
        """Test creating embedding wrapper from an adapter."""
        mock_adapter = MagicMock()
        wrapper = KilnEmbeddingWrapper(mock_adapter)
        assert isinstance(wrapper, KilnEmbeddingWrapper)
        assert wrapper._embedding_adapter == mock_adapter
