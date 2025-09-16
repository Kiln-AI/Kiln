import os
from unittest.mock import AsyncMock, patch

import pytest
from litellm import Usage
from litellm.types.utils import EmbeddingResponse

from kiln_ai.adapters.embedding.base_embedding_adapter import Embedding
from kiln_ai.adapters.embedding.litellm_embedding_adapter import (
    MAX_BATCH_SIZE,
    EmbeddingOptions,
    LitellmEmbeddingAdapter,
    validate_map_to_embeddings,
)
from kiln_ai.adapters.ml_embedding_model_list import KilnEmbeddingModelProvider
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.utils.config import Config


@pytest.fixture
def mock_embedding_config():
    return EmbeddingConfig(
        name="test-embedding",
        model_provider_name=ModelProviderName.openai,
        model_name="openai_text_embedding_3_small",
        properties={},
    )


@pytest.fixture
def mock_litellm_core_config():
    return LiteLlmCoreConfig()


@pytest.fixture
def mock_litellm_adapter(mock_embedding_config, mock_litellm_core_config):
    return LitellmEmbeddingAdapter(
        mock_embedding_config, litellm_core_config=mock_litellm_core_config
    )


class TestEmbeddingOptions:
    """Test the EmbeddingOptions class."""

    def test_default_values(self):
        """Test that EmbeddingOptions has correct default values."""
        options = EmbeddingOptions()
        assert options.dimensions is None

    def test_with_dimensions(self):
        """Test EmbeddingOptions with dimensions set."""
        options = EmbeddingOptions(dimensions=1536)
        assert options.dimensions == 1536

    def test_model_dump_excludes_none(self):
        """Test that model_dump excludes None values."""
        options = EmbeddingOptions()
        dumped = options.model_dump(exclude_none=True)
        assert "dimensions" not in dumped

        options_with_dim = EmbeddingOptions(dimensions=1536)
        dumped_with_dim = options_with_dim.model_dump(exclude_none=True)
        assert "dimensions" in dumped_with_dim
        assert dumped_with_dim["dimensions"] == 1536


class TestLitellmEmbeddingAdapter:
    """Test the LitellmEmbeddingAdapter class."""

    def test_init_success(self, mock_embedding_config, mock_litellm_core_config):
        """Test successful initialization of the adapter."""
        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, mock_litellm_core_config
        )
        assert adapter.embedding_config == mock_embedding_config

    def test_build_options_no_dimensions(self, mock_litellm_adapter):
        """Test build_options when no dimensions are specified."""
        options = mock_litellm_adapter.build_options()
        assert options.dimensions is None

    def test_build_options_with_dimensions(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test build_options when dimensions are specified."""
        mock_embedding_config.properties = {"dimensions": 1536}
        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )
        options = adapter.build_options()
        assert options.dimensions == 1536

    async def test_generate_embeddings_with_completion_kwargs(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test that completion_kwargs are properly passed to litellm.aembedding."""
        # Set up litellm_core_config with additional options
        mock_litellm_core_config.additional_body_options = {"custom_param": "value"}
        mock_litellm_core_config.base_url = "https://custom-api.example.com"
        mock_litellm_core_config.default_headers = {
            "Authorization": "Bearer custom-token"
        }

        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )

        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ) as mock_aembedding:
            await adapter._generate_embeddings(["test text"])

        # Verify litellm.aembedding was called with completion_kwargs
        call_args = mock_aembedding.call_args
        assert call_args[1]["custom_param"] == "value"
        assert call_args[1]["api_base"] == "https://custom-api.example.com"
        assert call_args[1]["default_headers"] == {
            "Authorization": "Bearer custom-token"
        }

    async def test_generate_embeddings_with_partial_completion_kwargs(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test that completion_kwargs work when only some options are set."""
        # Set only additional_body_options
        mock_litellm_core_config.additional_body_options = {"timeout": 30}
        mock_litellm_core_config.base_url = None
        mock_litellm_core_config.default_headers = None

        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )

        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ) as mock_aembedding:
            await adapter._generate_embeddings(["test text"])

        # Verify only the set options are passed
        call_args = mock_aembedding.call_args
        assert call_args[1]["timeout"] == 30
        assert "api_base" not in call_args[1]
        assert "default_headers" not in call_args[1]

    async def test_generate_embeddings_with_empty_completion_kwargs(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test that completion_kwargs work when all options are None/empty."""
        # Ensure all options are None/empty
        mock_litellm_core_config.additional_body_options = None
        mock_litellm_core_config.base_url = None
        mock_litellm_core_config.default_headers = None

        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )

        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ) as mock_aembedding:
            await adapter._generate_embeddings(["test text"])

        # Verify no completion_kwargs are passed
        call_args = mock_aembedding.call_args
        assert "api_base" not in call_args[1]
        assert "default_headers" not in call_args[1]
        # Should only have the basic parameters
        assert "model" in call_args[1]
        assert "input" in call_args[1]

    async def test_generate_embeddings_empty_list(self, mock_litellm_adapter):
        """Test embed method with empty text list."""
        result = await mock_litellm_adapter.generate_embeddings([])
        assert result.embeddings == []
        assert result.usage is None

    async def test_generate_embeddings_success(self, mock_litellm_adapter):
        """Test successful embedding generation."""
        # mock the response type
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
            {"object": "embedding", "index": 1, "embedding": [0.4, 0.5, 0.6]},
        ]
        mock_response.usage = Usage(prompt_tokens=10, total_tokens=10)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await mock_litellm_adapter._generate_embeddings(["text1", "text2"])

        assert len(result.embeddings) == 2
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.embeddings[1].vector == [0.4, 0.5, 0.6]
        assert result.usage == mock_response.usage

    async def test_generate_embeddings_for_batch_success(self, mock_litellm_adapter):
        """Test successful embedding generation for a single batch."""
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
            {"object": "embedding", "index": 1, "embedding": [0.4, 0.5, 0.6]},
        ]
        mock_response.usage = Usage(prompt_tokens=10, total_tokens=10)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await mock_litellm_adapter._generate_embeddings_for_batch(
                ["text1", "text2"]
            )

        assert len(result.embeddings) == 2
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.embeddings[1].vector == [0.4, 0.5, 0.6]
        assert result.usage == mock_response.usage

    async def test_generate_embeddings_for_batch_with_completion_kwargs(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test that completion_kwargs are properly passed to litellm.aembedding in batch method."""
        # Set up litellm_core_config with additional options
        mock_litellm_core_config.additional_body_options = {"custom_param": "value"}
        mock_litellm_core_config.base_url = "https://custom-api.example.com"
        mock_litellm_core_config.default_headers = {
            "Authorization": "Bearer custom-token"
        }

        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )

        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ) as mock_aembedding:
            await adapter._generate_embeddings_for_batch(["test text"])

        # Verify litellm.aembedding was called with completion_kwargs
        call_args = mock_aembedding.call_args
        assert call_args[1]["custom_param"] == "value"
        assert call_args[1]["api_base"] == "https://custom-api.example.com"
        assert call_args[1]["default_headers"] == {
            "Authorization": "Bearer custom-token"
        }

    async def test_generate_embeddings_with_dimensions(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test embedding with dimensions specified."""
        mock_embedding_config.properties = {"dimensions": 1536}
        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )

        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1] * 1536}
        ]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ) as mock_aembedding:
            result = await adapter._generate_embeddings(["test text"])

        # Verify litellm.aembedding was called with correct parameters
        mock_aembedding.assert_called_once_with(
            model="openai/text-embedding-3-small",
            input=["test text"],
            dimensions=1536,
        )

        assert len(result.embeddings) == 1
        assert len(result.embeddings[0].vector) == 1536
        assert result.usage == mock_response.usage

    async def test_generate_embeddings_batch_size_exceeded(self, mock_litellm_adapter):
        """Test that embedding fails when batch size is exceeded in individual batch."""
        # This test now tests the _generate_embeddings_for_batch method directly
        # since the main _generate_embeddings method now handles batching automatically
        large_text_list = ["text"] * (MAX_BATCH_SIZE + 1)

        with pytest.raises(
            ValueError,
            match=f"Too many input texts, max batch size is {MAX_BATCH_SIZE}, got {MAX_BATCH_SIZE + 1}",
        ):
            await mock_litellm_adapter._generate_embeddings_for_batch(large_text_list)

    async def test_generate_embeddings_response_length_mismatch(
        self, mock_litellm_adapter
    ):
        """Test that embedding fails when response data length doesn't match input."""
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]  # Only one embedding

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ):
            with pytest.raises(
                RuntimeError,
                match=r"Expected the number of embeddings in the response to be 2, got 1.",
            ):
                await mock_litellm_adapter._generate_embeddings(["text1", "text2"])

    async def test_generate_embeddings_litellm_exception(self, mock_litellm_adapter):
        """Test that litellm exceptions are properly raised."""
        with patch(
            "litellm.aembedding",
            new_callable=AsyncMock,
            side_effect=Exception("litellm error"),
        ):
            with pytest.raises(Exception, match="litellm error"):
                await mock_litellm_adapter._generate_embeddings(["test text"])

    async def test_generate_embeddings_sorts_by_index(self, mock_litellm_adapter):
        """Test that embeddings are sorted by index."""
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 2, "embedding": [0.3, 0.4, 0.5]},
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
            {"object": "embedding", "index": 1, "embedding": [0.2, 0.3, 0.4]},
        ]
        mock_response.usage = Usage(prompt_tokens=15, total_tokens=15)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await mock_litellm_adapter._generate_embeddings(
                ["text1", "text2", "text3"]
            )

        # Verify embeddings are sorted by index
        assert len(result.embeddings) == 3
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]  # index 0
        assert result.embeddings[1].vector == [0.2, 0.3, 0.4]  # index 1
        assert result.embeddings[2].vector == [0.3, 0.4, 0.5]  # index 2

    async def test_generate_embeddings_single_text(self, mock_litellm_adapter):
        """Test embedding a single text."""
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ) as mock_aembedding:
            result = await mock_litellm_adapter._generate_embeddings(["single text"])

        # The call should not include dimensions since the fixture has empty properties
        mock_aembedding.assert_called_once_with(
            model="openai/text-embedding-3-small",
            input=["single text"],
        )

        assert len(result.embeddings) == 1
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.usage == mock_response.usage

    async def test_generate_embeddings_max_batch_size(self, mock_litellm_adapter):
        """Test embedding with exactly the maximum batch size."""
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": i, "embedding": [0.1, 0.2, 0.3]}
            for i in range(MAX_BATCH_SIZE)
        ]
        mock_response.usage = Usage(
            prompt_tokens=MAX_BATCH_SIZE * 5, total_tokens=MAX_BATCH_SIZE * 5
        )

        large_text_list = ["text"] * MAX_BATCH_SIZE

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await mock_litellm_adapter._generate_embeddings(large_text_list)

        assert len(result.embeddings) == MAX_BATCH_SIZE
        assert result.usage == mock_response.usage

    async def test_generate_embeddings_multiple_batches(self, mock_litellm_adapter):
        """Test that embedding properly handles multiple batches."""
        # Create a list that will require multiple batches
        total_texts = MAX_BATCH_SIZE * 2 + 50  # 2 full batches + 50 more
        text_list = [f"text_{i}" for i in range(total_texts)]

        # Mock responses for each batch
        batch1_response = AsyncMock(spec=EmbeddingResponse)
        batch1_response.data = [
            {"object": "embedding", "index": i, "embedding": [0.1, 0.2, 0.3]}
            for i in range(MAX_BATCH_SIZE)
        ]
        batch1_response.usage = Usage(prompt_tokens=100, total_tokens=100)

        batch2_response = AsyncMock(spec=EmbeddingResponse)
        batch2_response.data = [
            {"object": "embedding", "index": i, "embedding": [0.4, 0.5, 0.6]}
            for i in range(MAX_BATCH_SIZE)
        ]
        batch2_response.usage = Usage(prompt_tokens=100, total_tokens=100)

        batch3_response = AsyncMock(spec=EmbeddingResponse)
        batch3_response.data = [
            {"object": "embedding", "index": i, "embedding": [0.7, 0.8, 0.9]}
            for i in range(50)
        ]
        batch3_response.usage = Usage(prompt_tokens=50, total_tokens=50)

        # Mock litellm.aembedding to return different responses based on input size
        async def mock_aembedding(*args, **kwargs):
            input_size = len(kwargs.get("input", []))
            if input_size == MAX_BATCH_SIZE:
                if len(mock_aembedding.call_count) == 0:
                    mock_aembedding.call_count.append(1)
                    return batch1_response
                else:
                    mock_aembedding.call_count.append(1)
                    return batch2_response
            else:
                return batch3_response

        mock_aembedding.call_count = []

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, side_effect=mock_aembedding
        ):
            result = await mock_litellm_adapter._generate_embeddings(text_list)

        # Should have all embeddings combined
        assert len(result.embeddings) == total_texts

        # Should have combined usage from all batches
        assert result.usage is not None
        assert result.usage.prompt_tokens == 250  # 100 + 100 + 50
        assert result.usage.total_tokens == 250  # 100 + 100 + 50

        # Verify embeddings are in the right order
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]  # First batch
        assert result.embeddings[MAX_BATCH_SIZE].vector == [
            0.4,
            0.5,
            0.6,
        ]  # Second batch
        assert result.embeddings[MAX_BATCH_SIZE * 2].vector == [
            0.7,
            0.8,
            0.9,
        ]  # Third batch

    async def test_generate_embeddings_batching_edge_cases(self, mock_litellm_adapter):
        """Test batching edge cases like empty lists and single items."""
        # Test empty list
        result = await mock_litellm_adapter._generate_embeddings([])
        assert result.embeddings == []
        assert result.usage is not None
        assert result.usage.prompt_tokens == 0
        assert result.usage.total_tokens == 0

        # Test single item (should still go through batching logic)
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch("litellm.aembedding", return_value=mock_response):
            result = await mock_litellm_adapter._generate_embeddings(["single text"])

        assert len(result.embeddings) == 1
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.usage == mock_response.usage

    async def test_generate_embeddings_batching_with_mixed_usage(
        self, mock_litellm_adapter
    ):
        """Test batching when some responses have usage and others don't."""
        # Create a list that will require multiple batches
        text_list = ["text"] * (MAX_BATCH_SIZE + 10)

        # First batch with usage
        batch1_response = AsyncMock(spec=EmbeddingResponse)
        batch1_response.data = [
            {"object": "embedding", "index": i, "embedding": [0.1, 0.2, 0.3]}
            for i in range(MAX_BATCH_SIZE)
        ]
        batch1_response.usage = Usage(prompt_tokens=100, total_tokens=100)

        # Second batch without usage
        batch2_response = AsyncMock(spec=EmbeddingResponse)
        batch2_response.data = [
            {"object": "embedding", "index": i, "embedding": [0.4, 0.5, 0.6]}
            for i in range(10)
        ]
        batch2_response.usage = None

        # Mock litellm.aembedding to return different responses based on input size
        async def mock_aembedding(*args, **kwargs):
            input_size = len(kwargs.get("input", []))
            if input_size == MAX_BATCH_SIZE:
                return batch1_response
            else:
                return batch2_response

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, side_effect=mock_aembedding
        ):
            result = await mock_litellm_adapter._generate_embeddings(text_list)

        # Should have all embeddings combined
        assert len(result.embeddings) == MAX_BATCH_SIZE + 10

        # Should have None usage since one batch has None usage
        assert result.usage is None

    async def test_generate_embeddings_batching_with_all_usage(
        self, mock_litellm_adapter
    ):
        """Test batching when all responses have usage information."""
        # Create a list that will require multiple batches
        text_list = ["text"] * (MAX_BATCH_SIZE + 10)

        # First batch with usage
        batch1_response = AsyncMock(spec=EmbeddingResponse)
        batch1_response.data = [
            {"object": "embedding", "index": i, "embedding": [0.1, 0.2, 0.3]}
            for i in range(MAX_BATCH_SIZE)
        ]
        batch1_response.usage = Usage(prompt_tokens=100, total_tokens=100)

        # Second batch with usage
        batch2_response = AsyncMock(spec=EmbeddingResponse)
        batch2_response.data = [
            {"object": "embedding", "index": i, "embedding": [0.4, 0.5, 0.6]}
            for i in range(10)
        ]
        batch2_response.usage = Usage(prompt_tokens=50, total_tokens=50)

        # Mock litellm.aembedding to return different responses based on input size
        async def mock_aembedding(*args, **kwargs):
            input_size = len(kwargs.get("input", []))
            if input_size == MAX_BATCH_SIZE:
                return batch1_response
            else:
                return batch2_response

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, side_effect=mock_aembedding
        ):
            result = await mock_litellm_adapter._generate_embeddings(text_list)

        # Should have all embeddings combined
        assert len(result.embeddings) == MAX_BATCH_SIZE + 10

        # Should have combined usage since all batches have usage
        assert result.usage is not None
        assert result.usage.prompt_tokens == 150  # 100 + 50
        assert result.usage.total_tokens == 150  # 100 + 50

    def test_embedding_config_inheritance(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test that the adapter properly inherits from BaseEmbeddingAdapter."""
        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )
        assert adapter.embedding_config == mock_embedding_config

    async def test_generate_embeddings_method_integration(self, mock_litellm_adapter):
        """Test the public embed method integration."""
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await mock_litellm_adapter.generate_embeddings(["test text"])

        assert len(result.embeddings) == 1
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.usage == mock_response.usage


class TestLitellmEmbeddingAdapterEdgeCases:
    """Test edge cases and error conditions."""

    async def test_generate_embeddings_with_none_usage(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test embedding when litellm returns None usage."""
        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]
        mock_response.usage = None

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await adapter._generate_embeddings(["test text"])

        assert len(result.embeddings) == 1
        # With the new logic, if any response has None usage, the result has None usage
        assert result.usage is None

    async def test_generate_embeddings_with_empty_embedding_vector(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test embedding with empty vector."""
        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [{"object": "embedding", "index": 0, "embedding": []}]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await adapter._generate_embeddings(["test text"])

        assert len(result.embeddings) == 1
        assert result.embeddings[0].vector == []

    async def test_generate_embeddings_with_duplicate_indices(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test embedding with duplicate indices (should still work due to sorting)."""
        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )
        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
            {
                "object": "embedding",
                "index": 0,
                "embedding": [0.4, 0.5, 0.6],
            },  # Duplicate index
        ]
        mock_response.usage = Usage(prompt_tokens=10, total_tokens=10)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await adapter._generate_embeddings(["text1", "text2"])

        # Both embeddings should be present and match the order in response.data
        assert len(result.embeddings) == 2
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.embeddings[1].vector == [0.4, 0.5, 0.6]

    async def test_generate_embeddings_with_complex_properties(
        self, mock_embedding_config, mock_litellm_core_config
    ):
        """Test embedding with complex properties (only dimensions should be used)."""
        mock_embedding_config.properties = {
            "dimensions": 1536,
            "custom_property": "value",
            "numeric_property": 42,
            "boolean_property": True,
        }
        adapter = LitellmEmbeddingAdapter(
            mock_embedding_config, litellm_core_config=mock_litellm_core_config
        )

        mock_response = AsyncMock(spec=EmbeddingResponse)
        mock_response.data = [
            {"object": "embedding", "index": 0, "embedding": [0.1] * 1536}
        ]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ) as mock_aembedding:
            await adapter._generate_embeddings(["test text"])

        # Only dimensions should be passed to litellm
        call_args = mock_aembedding.call_args
        assert call_args[1]["dimensions"] == 1536
        # Other properties should not be passed
        assert "custom_property" not in call_args[1]
        assert "numeric_property" not in call_args[1]
        assert "boolean_property" not in call_args[1]


@pytest.mark.paid
@pytest.mark.parametrize(
    "provider,model_name,expected_dim",
    [
        (ModelProviderName.openai, "openai_text_embedding_3_small", 1536),
        (ModelProviderName.openai, "openai_text_embedding_3_large", 3072),
        (ModelProviderName.gemini_api, "gemini_text_embedding_004", 768),
    ],
)
@pytest.mark.asyncio
async def test_paid_generate_embeddings_basic(
    provider, model_name, expected_dim, mock_litellm_core_config
):
    openai_key = Config.shared().open_ai_api_key
    if not openai_key:
        pytest.skip("OPENAI_API_KEY not set")
    # Set the API key for litellm
    os.environ["OPENAI_API_KEY"] = openai_key

    # gemini key
    gemini_key = Config.shared().gemini_api_key
    if not gemini_key:
        pytest.skip("GEMINI_API_KEY not set")
    os.environ["GEMINI_API_KEY"] = gemini_key

    config = EmbeddingConfig(
        name="paid-embedding",
        model_provider_name=provider,
        model_name=model_name,
        properties={},
    )
    adapter = LitellmEmbeddingAdapter(
        config, litellm_core_config=mock_litellm_core_config
    )
    text = ["Kiln is an open-source evaluation platform for LLMs."]
    result = await adapter.generate_embeddings(text)
    assert len(result.embeddings) == 1
    assert isinstance(result.embeddings[0].vector, list)
    assert len(result.embeddings[0].vector) == expected_dim
    assert all(isinstance(x, float) for x in result.embeddings[0].vector)


# test model_provider
def test_model_provider(mock_litellm_core_config):
    mock_embedding_config = EmbeddingConfig(
        name="test",
        model_provider_name=ModelProviderName.openai,
        model_name="openai_text_embedding_3_small",
        properties={},
    )
    adapter = LitellmEmbeddingAdapter(
        mock_embedding_config, litellm_core_config=mock_litellm_core_config
    )
    assert adapter.model_provider.name == ModelProviderName.openai
    assert adapter.model_provider.model_id == "text-embedding-3-small"


def test_model_provider_gemini(mock_litellm_core_config):
    config = EmbeddingConfig(
        name="test",
        model_provider_name=ModelProviderName.gemini_api,
        model_name="gemini_text_embedding_004",
        properties={},
    )
    adapter = LitellmEmbeddingAdapter(
        config, litellm_core_config=mock_litellm_core_config
    )
    assert adapter.model_provider.name == ModelProviderName.gemini_api
    assert adapter.model_provider.model_id == "text-embedding-004"


@pytest.mark.parametrize(
    "provider,model_name,expected_model_id",
    [
        (
            ModelProviderName.gemini_api,
            "gemini_text_embedding_004",
            "gemini/text-embedding-004",
        ),
        (
            ModelProviderName.openai,
            "openai_text_embedding_3_small",
            "openai/text-embedding-3-small",
        ),
    ],
)
def test_litellm_model_id(
    provider, model_name, expected_model_id, mock_litellm_core_config
):
    config = EmbeddingConfig(
        name="test",
        model_provider_name=provider,
        model_name=model_name,
        properties={},
    )
    adapter = LitellmEmbeddingAdapter(
        config, litellm_core_config=mock_litellm_core_config
    )
    assert adapter.litellm_model_id == expected_model_id


def test_litellm_model_id_custom_provider_without_base_url(mock_litellm_core_config):
    """Test that custom providers without base_url raise an error."""
    config = EmbeddingConfig(
        name="test",
        model_provider_name=ModelProviderName.openai_compatible,
        model_name="some-model",
        properties={},
    )
    adapter = LitellmEmbeddingAdapter(
        config, litellm_core_config=mock_litellm_core_config
    )

    with pytest.raises(
        ValueError,
        match="Embedding model some-model not found in the list of built-in models",
    ):
        adapter.model_provider


def test_litellm_model_id_custom_provider_with_base_url(mock_litellm_core_config):
    """Test that custom providers with base_url work correctly."""
    # Set up a custom provider with base_url
    mock_litellm_core_config.base_url = "https://custom-api.example.com"

    config = EmbeddingConfig(
        name="test",
        model_provider_name=ModelProviderName.openai_compatible,
        model_name="some-model",
        properties={},
    )
    adapter = LitellmEmbeddingAdapter(
        config, litellm_core_config=mock_litellm_core_config
    )

    with pytest.raises(
        ValueError,
        match="Embedding model some-model not found in the list of built-in models",
    ):
        adapter.model_provider


def test_litellm_model_id_custom_provider_ollama_with_base_url():
    """Test that ollama provider with base_url works correctly."""

    # Create a mock provider that would be found in the built-in models
    # We need to mock the built_in_embedding_models_from_provider function
    with patch(
        "kiln_ai.adapters.embedding.litellm_embedding_adapter.built_in_embedding_models_from_provider"
    ) as mock_built_in:
        mock_built_in.return_value = KilnEmbeddingModelProvider(
            name=ModelProviderName.ollama,
            model_id="test-model",
            n_dimensions=768,
        )

        config = EmbeddingConfig(
            name="test",
            model_provider_name=ModelProviderName.ollama,
            model_name="test-model",
            properties={},
        )

        # With base_url - should work
        litellm_core_config_with_url = LiteLlmCoreConfig(
            base_url="http://localhost:11434"
        )
        adapter = LitellmEmbeddingAdapter(
            config, litellm_core_config=litellm_core_config_with_url
        )

        # Should not raise an error
        model_id = adapter.litellm_model_id
        assert model_id == "openai/test-model"


def test_litellm_model_id_custom_provider_ollama_without_base_url():
    """Test that ollama provider without base_url raises an error."""
    from kiln_ai.adapters.ml_embedding_model_list import KilnEmbeddingModelProvider

    # Create a mock provider that would be found in the built-in models
    with patch(
        "kiln_ai.adapters.embedding.litellm_embedding_adapter.built_in_embedding_models_from_provider"
    ) as mock_built_in:
        mock_built_in.return_value = KilnEmbeddingModelProvider(
            name=ModelProviderName.ollama,
            model_id="test-model",
            n_dimensions=768,
        )

        config = EmbeddingConfig(
            name="test",
            model_provider_name=ModelProviderName.ollama,
            model_name="test-model",
            properties={},
        )

        # Without base_url - should raise an error
        litellm_core_config_without_url = LiteLlmCoreConfig(base_url=None)
        adapter = LitellmEmbeddingAdapter(
            config, litellm_core_config=litellm_core_config_without_url
        )

        with pytest.raises(
            ValueError,
            match="Provider ollama must have an explicit base URL",
        ):
            adapter.litellm_model_id


def test_litellm_model_id_custom_provider_openai_compatible_with_base_url():
    """Test that openai_compatible provider with base_url works correctly."""
    from kiln_ai.adapters.ml_embedding_model_list import KilnEmbeddingModelProvider

    # Create a mock provider that would be found in the built-in models
    with patch(
        "kiln_ai.adapters.embedding.litellm_embedding_adapter.built_in_embedding_models_from_provider"
    ) as mock_built_in:
        mock_built_in.return_value = KilnEmbeddingModelProvider(
            name=ModelProviderName.openai_compatible,
            model_id="test-model",
            n_dimensions=768,
        )

        config = EmbeddingConfig(
            name="test",
            model_provider_name=ModelProviderName.openai_compatible,
            model_name="test-model",
            properties={},
        )

        # With base_url - should work
        litellm_core_config_with_url = LiteLlmCoreConfig(
            base_url="https://custom-api.example.com"
        )
        adapter = LitellmEmbeddingAdapter(
            config, litellm_core_config=litellm_core_config_with_url
        )

        # Should not raise an error
        model_id = adapter.litellm_model_id
        assert model_id == "openai/test-model"


def test_litellm_model_id_custom_provider_openai_compatible_without_base_url():
    """Test that openai_compatible provider without base_url raises an error."""

    # Create a mock provider that would be found in the built-in models
    with patch(
        "kiln_ai.adapters.embedding.litellm_embedding_adapter.built_in_embedding_models_from_provider"
    ) as mock_built_in:
        mock_built_in.return_value = KilnEmbeddingModelProvider(
            name=ModelProviderName.openai_compatible,
            model_id="test-model",
            n_dimensions=768,
        )

        config = EmbeddingConfig(
            name="test",
            model_provider_name=ModelProviderName.openai_compatible,
            model_name="test-model",
            properties={},
        )

        # Without base_url - should raise an error
        litellm_core_config_without_url = LiteLlmCoreConfig(base_url=None)
        adapter = LitellmEmbeddingAdapter(
            config, litellm_core_config=litellm_core_config_without_url
        )

        with pytest.raises(
            ValueError,
            match="Provider openai_compatible must have an explicit base URL",
        ):
            adapter.litellm_model_id


@pytest.mark.paid
@pytest.mark.parametrize(
    "provider,model_name,expected_dim",
    [
        (ModelProviderName.openai, "openai_text_embedding_3_small", 256),
        (ModelProviderName.openai, "openai_text_embedding_3_small", 512),
        (ModelProviderName.openai, "openai_text_embedding_3_large", 256),
        (ModelProviderName.openai, "openai_text_embedding_3_large", 512),
        (ModelProviderName.openai, "openai_text_embedding_3_large", 1024),
        (ModelProviderName.openai, "openai_text_embedding_3_large", 2048),
    ],
)
@pytest.mark.asyncio
async def test_paid_generate_embeddings_with_custom_dimensions_supported(
    provider, model_name, expected_dim, mock_litellm_core_config
):
    """
    Some models support custom dimensions - where the provider shortens the dimensions to match
    the desired custom number of dimensions. Ref: https://openai.com/index/new-embedding-models-and-api-updates/
    """
    api_key = Config.shared().open_ai_api_key or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    config = EmbeddingConfig(
        name="paid-embedding",
        model_provider_name=provider,
        model_name=model_name,
        properties={"dimensions": expected_dim},
    )
    adapter = LitellmEmbeddingAdapter(
        config, litellm_core_config=mock_litellm_core_config
    )
    text = ["Kiln is an open-source evaluation platform for LLMs."]
    result = await adapter.generate_embeddings(text)
    assert len(result.embeddings) == 1
    assert isinstance(result.embeddings[0].vector, list)
    assert len(result.embeddings[0].vector) == expected_dim
    assert all(isinstance(x, float) for x in result.embeddings[0].vector)


def test_validate_map_to_embeddings():
    mock_response = AsyncMock(spec=EmbeddingResponse)
    mock_response.data = [
        {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
        {"object": "embedding", "index": 1, "embedding": [0.4, 0.5, 0.6]},
    ]
    expected_embeddings = [
        Embedding(vector=[0.1, 0.2, 0.3]),
        Embedding(vector=[0.4, 0.5, 0.6]),
    ]
    result = validate_map_to_embeddings(mock_response, 2)
    assert result == expected_embeddings


def test_validate_map_to_embeddings_invalid_length():
    mock_response = AsyncMock(spec=EmbeddingResponse)
    mock_response.data = [
        {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
    ]
    with pytest.raises(
        RuntimeError,
        match=r"Expected the number of embeddings in the response to be 2, got 1.",
    ):
        validate_map_to_embeddings(mock_response, 2)


def test_validate_map_to_embeddings_invalid_object_type():
    mock_response = AsyncMock(spec=EmbeddingResponse)
    mock_response.data = [
        {"object": "not_embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
    ]
    with pytest.raises(
        RuntimeError,
        match=r"Embedding response data has an unexpected shape. Property 'object' is not 'embedding'. Got not_embedding.",
    ):
        validate_map_to_embeddings(mock_response, 1)


def test_validate_map_to_embeddings_invalid_embedding_type():
    mock_response = AsyncMock(spec=EmbeddingResponse)
    mock_response.data = [
        {"object": "embedding", "index": 0, "embedding": "not_a_list"},
    ]
    mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)
    with pytest.raises(
        RuntimeError,
        match=r"Embedding response data has an unexpected shape. Property 'embedding' is not a list. Got <class 'str'>.",
    ):
        validate_map_to_embeddings(mock_response, 1)

    # missing embedding
    mock_response = AsyncMock(spec=EmbeddingResponse)
    mock_response.data = [
        {"object": "embedding", "index": 0},
    ]
    with pytest.raises(
        RuntimeError,
        match=r"Embedding response data has an unexpected shape. Property 'embedding' is None in response data item.",
    ):
        validate_map_to_embeddings(mock_response, 1)


def test_validate_map_to_embeddings_invalid_index_type():
    mock_response = AsyncMock(spec=EmbeddingResponse)
    mock_response.data = [
        {"object": "embedding", "index": "not_an_int", "embedding": [0.1, 0.2, 0.3]},
    ]
    mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)
    with pytest.raises(
        RuntimeError,
        match=r"Embedding response data has an unexpected shape. Property 'index' is not an integer. Got <class 'str'>.",
    ):
        validate_map_to_embeddings(mock_response, 1)

    # missing index
    mock_response = AsyncMock(spec=EmbeddingResponse)
    mock_response.data = [
        {"object": "embedding", "embedding": [0.1, 0.2, 0.3]},
    ]
    with pytest.raises(
        RuntimeError,
        match=r"Embedding response data has an unexpected shape. Property 'index' is None in response data item.",
    ):
        validate_map_to_embeddings(mock_response, 1)


def test_validate_map_to_embeddings_sorting():
    mock_response = AsyncMock(spec=EmbeddingResponse)
    mock_response.data = [
        {"object": "embedding", "index": 2, "embedding": [0.3, 0.4, 0.5]},
        {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
        {"object": "embedding", "index": 1, "embedding": [0.2, 0.3, 0.4]},
    ]
    expected_embeddings = [
        Embedding(vector=[0.1, 0.2, 0.3]),
        Embedding(vector=[0.2, 0.3, 0.4]),
        Embedding(vector=[0.3, 0.4, 0.5]),
    ]
    result = validate_map_to_embeddings(mock_response, 3)
    assert result == expected_embeddings


def test_generate_embeddings_response_not_embedding_response():
    response = AsyncMock()
    response.data = [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}]
    response.usage = Usage(prompt_tokens=5, total_tokens=5)
    with pytest.raises(
        RuntimeError,
        match=r"Expected EmbeddingResponse, got <class 'unittest.mock.AsyncMock'>.",
    ):
        validate_map_to_embeddings(response, 1)
