import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import Usage

from kiln_ai.adapters.embedding.litellm_embedding_adapter import (
    MAX_BATCH_SIZE,
    EmbeddingOptions,
    LitellmEmbeddingAdapter,
)
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
def mock_litellm_adapter(mock_embedding_config):
    return LitellmEmbeddingAdapter(mock_embedding_config)


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

    def test_init_success(self, mock_embedding_config):
        """Test successful initialization of the adapter."""
        adapter = LitellmEmbeddingAdapter(mock_embedding_config)
        assert adapter.model_provider_name == ModelProviderName.openai
        assert adapter.model_name == "openai_text_embedding_3_small"
        assert adapter.properties == {}
        assert adapter.embedding_config == mock_embedding_config

    def test_init_missing_provider(self):
        """Test initialization fails when provider is None."""
        config = MagicMock()
        config.model_provider_name = None
        config.model_name = "openai_text_embedding_3_small"
        config.properties = {}
        with pytest.raises(ValueError, match="Provider must be set"):
            LitellmEmbeddingAdapter(config)

    def test_init_missing_model_name(self):
        """Test initialization fails when model_name is None."""
        config = MagicMock()
        config.model_provider_name = ModelProviderName.openai
        config.model_name = None
        config.properties = {}
        with pytest.raises(ValueError, match="Model name must be set"):
            LitellmEmbeddingAdapter(config)

    def test_build_options_no_dimensions(self, mock_litellm_adapter):
        """Test build_options when no dimensions are specified."""
        options = mock_litellm_adapter.build_options()
        assert options.dimensions is None

    def test_build_options_with_dimensions(self, mock_embedding_config):
        """Test build_options when dimensions are specified."""
        mock_embedding_config.properties = {"dimensions": 1536}
        adapter = LitellmEmbeddingAdapter(mock_embedding_config)
        options = adapter.build_options()
        assert options.dimensions == 1536

    async def test_embed_empty_list(self, mock_litellm_adapter):
        """Test embed method with empty text list."""
        result = await mock_litellm_adapter.embed([])
        assert result.embeddings == []
        assert result.usage is None

    async def test_embed_success(self, mock_litellm_adapter):
        """Test successful embedding generation."""
        mock_response = AsyncMock()
        mock_response.data = [
            {"index": 0, "embedding": [0.1, 0.2, 0.3]},
            {"index": 1, "embedding": [0.4, 0.5, 0.6]},
        ]
        mock_response.usage = Usage(prompt_tokens=10, total_tokens=10)

        with patch("litellm.aembedding", return_value=mock_response):
            result = await mock_litellm_adapter._embed(["text1", "text2"])

        assert len(result.embeddings) == 2
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.embeddings[1].vector == [0.4, 0.5, 0.6]
        assert result.usage == mock_response.usage

    async def test_embed_with_dimensions(self, mock_embedding_config):
        """Test embedding with dimensions specified."""
        mock_embedding_config.properties = {"dimensions": 1536}
        adapter = LitellmEmbeddingAdapter(mock_embedding_config)

        mock_response = AsyncMock()
        mock_response.data = [{"index": 0, "embedding": [0.1] * 1536}]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch("litellm.aembedding", return_value=mock_response) as mock_aembedding:
            result = await adapter._embed(["test text"])

        # Verify litellm.aembedding was called with correct parameters
        mock_aembedding.assert_called_once_with(
            model="openai/text-embedding-3-small",
            input=["test text"],
            dimensions=1536,
        )

        assert len(result.embeddings) == 1
        assert len(result.embeddings[0].vector) == 1536
        assert result.usage == mock_response.usage

    async def test_embed_batch_size_exceeded(self, mock_litellm_adapter):
        """Test that embedding fails when batch size is exceeded."""
        large_text_list = ["text"] * (MAX_BATCH_SIZE + 1)

        with pytest.raises(ValueError, match="Text is too long"):
            await mock_litellm_adapter._embed(large_text_list)

    async def test_embed_response_length_mismatch(self, mock_litellm_adapter):
        """Test that embedding fails when response data length doesn't match input."""
        mock_response = AsyncMock()
        mock_response.data = [
            {"index": 0, "embedding": [0.1, 0.2, 0.3]}
        ]  # Only one embedding

        with patch("litellm.aembedding", return_value=mock_response):
            with pytest.raises(
                ValueError,
                match="Response data length does not match input text length",
            ):
                await mock_litellm_adapter._embed(["text1", "text2"])

    async def test_embed_litellm_exception(self, mock_litellm_adapter):
        """Test that litellm exceptions are properly raised."""
        with patch("litellm.aembedding", side_effect=Exception("litellm error")):
            with pytest.raises(Exception, match="litellm error"):
                await mock_litellm_adapter._embed(["test text"])

    async def test_embed_sorts_by_index(self, mock_litellm_adapter):
        """Test that embeddings are sorted by index."""
        mock_response = AsyncMock()
        mock_response.data = [
            {"index": 2, "embedding": [0.3, 0.4, 0.5]},
            {"index": 0, "embedding": [0.1, 0.2, 0.3]},
            {"index": 1, "embedding": [0.2, 0.3, 0.4]},
        ]
        mock_response.usage = Usage(prompt_tokens=15, total_tokens=15)

        with patch("litellm.aembedding", return_value=mock_response):
            result = await mock_litellm_adapter._embed(["text1", "text2", "text3"])

        # Verify embeddings are sorted by index
        assert len(result.embeddings) == 3
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]  # index 0
        assert result.embeddings[1].vector == [0.2, 0.3, 0.4]  # index 1
        assert result.embeddings[2].vector == [0.3, 0.4, 0.5]  # index 2

    async def test_embed_single_text(self, mock_litellm_adapter):
        """Test embedding a single text."""
        mock_response = AsyncMock()
        mock_response.data = [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch("litellm.aembedding", return_value=mock_response) as mock_aembedding:
            result = await mock_litellm_adapter._embed(["single text"])

        # The call should not include dimensions since the fixture has empty properties
        mock_aembedding.assert_called_once_with(
            model="openai/text-embedding-3-small",
            input=["single text"],
        )

        assert len(result.embeddings) == 1
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.usage == mock_response.usage

    async def test_embed_max_batch_size(self, mock_litellm_adapter):
        """Test embedding with exactly the maximum batch size."""
        mock_response = AsyncMock()
        mock_response.data = [
            {"index": i, "embedding": [0.1, 0.2, 0.3]} for i in range(MAX_BATCH_SIZE)
        ]
        mock_response.usage = Usage(
            prompt_tokens=MAX_BATCH_SIZE * 5, total_tokens=MAX_BATCH_SIZE * 5
        )

        large_text_list = ["text"] * MAX_BATCH_SIZE

        with patch("litellm.aembedding", return_value=mock_response):
            result = await mock_litellm_adapter._embed(large_text_list)

        assert len(result.embeddings) == MAX_BATCH_SIZE
        assert result.usage == mock_response.usage

    def test_embedding_config_inheritance(self, mock_embedding_config):
        """Test that the adapter properly inherits from BaseEmbeddingAdapter."""
        adapter = LitellmEmbeddingAdapter(mock_embedding_config)
        assert adapter.embedding_config == mock_embedding_config

    async def test_embed_method_integration(self, mock_litellm_adapter):
        """Test the public embed method integration."""
        mock_response = AsyncMock()
        mock_response.data = [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch("litellm.aembedding", return_value=mock_response):
            result = await mock_litellm_adapter.embed(["test text"])

        assert len(result.embeddings) == 1
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.usage == mock_response.usage


class TestLitellmEmbeddingAdapterEdgeCases:
    """Test edge cases and error conditions."""

    async def test_embed_with_none_usage(self, mock_embedding_config):
        """Test embedding when litellm returns None usage."""
        adapter = LitellmEmbeddingAdapter(mock_embedding_config)
        mock_response = AsyncMock()
        mock_response.data = [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]
        mock_response.usage = None

        with patch("litellm.aembedding", return_value=mock_response):
            result = await adapter._embed(["test text"])

        assert len(result.embeddings) == 1
        assert result.usage is None

    async def test_embed_with_empty_embedding_vector(self, mock_embedding_config):
        """Test embedding with empty vector."""
        adapter = LitellmEmbeddingAdapter(mock_embedding_config)
        mock_response = AsyncMock()
        mock_response.data = [{"index": 0, "embedding": []}]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch("litellm.aembedding", return_value=mock_response):
            result = await adapter._embed(["test text"])

        assert len(result.embeddings) == 1
        assert result.embeddings[0].vector == []

    async def test_embed_with_duplicate_indices(self, mock_embedding_config):
        """Test embedding with duplicate indices (should still work due to sorting)."""
        adapter = LitellmEmbeddingAdapter(mock_embedding_config)
        mock_response = AsyncMock()
        mock_response.data = [
            {"index": 0, "embedding": [0.1, 0.2, 0.3]},
            {"index": 0, "embedding": [0.4, 0.5, 0.6]},  # Duplicate index
        ]
        mock_response.usage = Usage(prompt_tokens=10, total_tokens=10)

        with patch("litellm.aembedding", return_value=mock_response):
            result = await adapter._embed(["text1", "text2"])

        # Both embeddings should be present and match the order in response.data
        assert len(result.embeddings) == 2
        assert result.embeddings[0].vector == [0.1, 0.2, 0.3]
        assert result.embeddings[1].vector == [0.4, 0.5, 0.6]

    def test_properties_access(self, mock_embedding_config):
        """Test that properties are correctly accessed from the config."""
        mock_embedding_config.properties = {
            "dimensions": 1536,
            "custom_property": "value",
            "numeric_property": 42,
        }
        adapter = LitellmEmbeddingAdapter(mock_embedding_config)

        assert adapter.properties == {
            "dimensions": 1536,
            "custom_property": "value",
            "numeric_property": 42,
        }

    async def test_embed_with_complex_properties(self, mock_embedding_config):
        """Test embedding with complex properties (only dimensions should be used)."""
        mock_embedding_config.properties = {
            "dimensions": 1536,
            "custom_property": "value",
            "numeric_property": 42,
            "boolean_property": True,
        }
        adapter = LitellmEmbeddingAdapter(mock_embedding_config)

        mock_response = AsyncMock()
        mock_response.data = [{"index": 0, "embedding": [0.1] * 1536}]
        mock_response.usage = Usage(prompt_tokens=5, total_tokens=5)

        with patch("litellm.aembedding", return_value=mock_response) as mock_aembedding:
            await adapter._embed(["test text"])

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
async def test_paid_embed_basic(provider, model_name, expected_dim):
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
    adapter = LitellmEmbeddingAdapter(config)
    text = ["Kiln is an open-source evaluation platform for LLMs."]
    result = await adapter.embed(text)
    assert len(result.embeddings) == 1
    assert isinstance(result.embeddings[0].vector, list)
    assert len(result.embeddings[0].vector) == expected_dim
    assert all(isinstance(x, float) for x in result.embeddings[0].vector)


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
async def test_paid_embed_with_custom_dimensions_supported(
    provider, model_name, expected_dim
):
    """
    Some models support custom dimensions - where the provider shortens the dimensions to match
    the desired custom number of dimensions. Ref: https://openai.com/index/new-embedding-models-and-api-updates/
    """
    api_key = Config.shared().open_ai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    os.environ["OPENAI_API_KEY"] = api_key
    config = EmbeddingConfig(
        name="paid-embedding",
        model_provider_name=provider,
        model_name=model_name,
        properties={"dimensions": expected_dim},
    )
    adapter = LitellmEmbeddingAdapter(config)
    text = ["Kiln is an open-source evaluation platform for LLMs."]
    result = await adapter.embed(text)
    assert len(result.embeddings) == 1
    assert isinstance(result.embeddings[0].vector, list)
    assert len(result.embeddings[0].vector) == expected_dim
    assert all(isinstance(x, float) for x in result.embeddings[0].vector)


@pytest.mark.paid
@pytest.mark.parametrize(
    "provider,model_name,expected_dim",
    [
        (ModelProviderName.gemini_api, "gemini_text_embedding_004", 256),
    ],
)
@pytest.mark.asyncio
async def test_paid_embed_with_custom_dimensions_not_supported(
    provider, model_name, expected_dim
):
    """Models that do not support custom dimensions will throw an error."""
    gemini_key = Config.shared().gemini_api_key or os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        pytest.skip("GEMINI_API_KEY not set")
    os.environ["GEMINI_API_KEY"] = gemini_key
    config = EmbeddingConfig(
        name="paid-embedding",
        model_provider_name=provider,
        model_name=model_name,
        properties={"dimensions": expected_dim},
    )
    adapter = LitellmEmbeddingAdapter(config)
    text = ["Kiln is an open-source evaluation platform for LLMs."]
    with pytest.raises(
        ValueError, match=f"The model {model_name} does not support custom dimensions"
    ):
        await adapter.embed(text)
