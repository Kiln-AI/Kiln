"""Tests for embedding wrapper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kiln_ai.adapters.chunkers.embedding_wrapper import (
    KilnEmbeddingWrapper,
    create_embedding_wrapper,
)
from kiln_ai.adapters.embedding.base_embedding_adapter import Embedding, EmbeddingResult
from kiln_ai.datamodel.embedding import EmbeddingConfig


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
    async def test_aget_query_embedding(
        self, embedding_wrapper, mock_embedding_adapter
    ):
        """Test async query embedding."""
        # Setup mock
        mock_embedding_adapter.generate_embeddings.return_value = EmbeddingResult(
            embeddings=[Embedding(vector=[0.1, 0.2, 0.3])]
        )

        result = await embedding_wrapper._aget_query_embedding("test query")

        assert result == [0.1, 0.2, 0.3]
        mock_embedding_adapter.generate_embeddings.assert_called_once_with(
            ["test query"]
        )

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

    @pytest.mark.asyncio
    async def test_aget_query_embedding_no_embeddings(
        self, embedding_wrapper, mock_embedding_adapter
    ):
        """Test async query embedding with no embeddings returned."""
        # Setup mock to return empty embeddings
        mock_embedding_adapter.generate_embeddings.return_value = EmbeddingResult(
            embeddings=[]
        )

        with pytest.raises(ValueError, match="No embeddings returned from adapter"):
            await embedding_wrapper._aget_query_embedding("test query")

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


class TestCreateEmbeddingWrapper:
    """Test the create_embedding_wrapper function."""

    @patch("kiln_ai.adapters.embedding.embedding_registry.embedding_adapter_from_type")
    def test_create_embedding_wrapper(self, mock_adapter_from_type):
        """Test creating embedding wrapper."""
        # Setup mock
        mock_adapter = MagicMock()
        mock_adapter_from_type.return_value = mock_adapter

        wrapper = create_embedding_wrapper("text-embedding-3-small", "openai")

        # Verify the adapter was created with correct config
        mock_adapter_from_type.assert_called_once()
        call_args = mock_adapter_from_type.call_args[0][0]
        assert isinstance(call_args, EmbeddingConfig)
        assert call_args.model_name == "text-embedding-3-small"
        assert call_args.model_provider_name == "openai"

        # Verify wrapper was created
        assert isinstance(wrapper, KilnEmbeddingWrapper)
        assert wrapper._embedding_adapter == mock_adapter
