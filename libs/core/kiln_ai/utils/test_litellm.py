import pytest

from kiln_ai.adapters.ml_embedding_model_list import KilnEmbeddingModelProvider
from kiln_ai.adapters.ml_model_list import KilnModelProvider
from kiln_ai.adapters.reranker_list import KilnRerankerModelProvider
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.utils.litellm import LitellmProviderInfo, get_litellm_provider_info


class TestGetLitellmProviderInfo:
    """Test cases for get_litellm_provider_info function"""

    @pytest.fixture
    def sample_model_id(self):
        """Sample model ID for testing"""
        return "test-model-id"

    @pytest.fixture
    def embedding_provider(self, sample_model_id):
        """Sample KilnEmbeddingModelProvider for testing"""
        return KilnEmbeddingModelProvider(
            name=ModelProviderName.openai,
            model_id=sample_model_id,
            n_dimensions=1536,
        )

    @pytest.fixture
    def model_provider(self, sample_model_id):
        """Sample KilnModelProvider for testing"""
        return KilnModelProvider(
            name=ModelProviderName.openai,
            model_id=sample_model_id,
        )

    @pytest.mark.parametrize(
        "model_id",
        [
            None,
            "",
        ],
    )
    def test_missing_model_id_raises_error(self, model_id):
        """Test that missing model_id raises ValueError"""
        provider = KilnModelProvider(
            name=ModelProviderName.openai,
            model_id=model_id,
        )

        with pytest.raises(
            ValueError, match="Model ID is required for OpenAI compatible models"
        ):
            get_litellm_provider_info(provider)

    @pytest.mark.parametrize(
        "provider_name,expected_litellm_name,expected_is_custom",
        [
            (ModelProviderName.openrouter, "openrouter", False),
            (ModelProviderName.openai, "openai", False),
            (ModelProviderName.groq, "groq", False),
            (ModelProviderName.anthropic, "anthropic", False),
            (ModelProviderName.gemini_api, "gemini", False),
            (ModelProviderName.fireworks_ai, "fireworks_ai", False),
            (ModelProviderName.amazon_bedrock, "bedrock", False),
            (ModelProviderName.azure_openai, "azure", False),
            (ModelProviderName.huggingface, "huggingface", False),
            (ModelProviderName.vertex, "vertex_ai", False),
            (ModelProviderName.together_ai, "together_ai", False),
            (ModelProviderName.ollama, "openai", True),
            (ModelProviderName.openai_compatible, "openai", True),
            (ModelProviderName.kiln_custom_registry, "openai", True),
            (ModelProviderName.kiln_fine_tune, "openai", True),
        ],
    )
    def test_provider_mappings_with_model_provider(
        self, provider_name, expected_litellm_name, expected_is_custom, sample_model_id
    ):
        """Test provider name mappings for KilnModelProvider"""
        provider = KilnModelProvider(
            name=provider_name,
            model_id=sample_model_id,
        )

        result = get_litellm_provider_info(provider)

        assert isinstance(result, LitellmProviderInfo)
        assert result.provider_name == expected_litellm_name
        assert result.is_custom == expected_is_custom
        assert result.litellm_model_id == f"{expected_litellm_name}/{sample_model_id}"

    @pytest.mark.parametrize(
        "provider_name,expected_litellm_name,expected_is_custom",
        [
            (ModelProviderName.openrouter, "openrouter", False),
            (ModelProviderName.openai, "openai", False),
            (ModelProviderName.groq, "groq", False),
            (ModelProviderName.anthropic, "anthropic", False),
            (ModelProviderName.gemini_api, "gemini", False),
            (ModelProviderName.fireworks_ai, "fireworks_ai", False),
            (ModelProviderName.amazon_bedrock, "bedrock", False),
            (ModelProviderName.azure_openai, "azure", False),
            (ModelProviderName.huggingface, "huggingface", False),
            (ModelProviderName.vertex, "vertex_ai", False),
            (ModelProviderName.together_ai, "together_ai", False),
            (ModelProviderName.ollama, "openai", True),
            (ModelProviderName.openai_compatible, "openai", True),
            (ModelProviderName.kiln_custom_registry, "openai", True),
            (ModelProviderName.kiln_fine_tune, "openai", True),
        ],
    )
    def test_provider_mappings_with_embedding_provider(
        self, provider_name, expected_litellm_name, expected_is_custom, sample_model_id
    ):
        """Test provider name mappings for KilnEmbeddingModelProvider"""
        provider = KilnEmbeddingModelProvider(
            name=provider_name,
            model_id=sample_model_id,
            n_dimensions=1536,
        )

        result = get_litellm_provider_info(provider)

        assert isinstance(result, LitellmProviderInfo)
        assert result.provider_name == expected_litellm_name
        assert result.is_custom == expected_is_custom
        assert result.litellm_model_id == f"{expected_litellm_name}/{sample_model_id}"

    def test_custom_providers_use_openai_format(self, sample_model_id):
        """Test that custom providers use 'openai' as the litellm provider name"""
        custom_providers = [
            ModelProviderName.ollama,
            ModelProviderName.openai_compatible,
            ModelProviderName.kiln_custom_registry,
            ModelProviderName.kiln_fine_tune,
        ]

        for provider_name in custom_providers:
            provider = KilnModelProvider(
                name=provider_name,
                model_id=sample_model_id,
            )

            result = get_litellm_provider_info(provider)

            assert result.provider_name == "openai"
            assert result.is_custom is True
            assert result.litellm_model_id == f"openai/{sample_model_id}"

    def test_non_custom_providers_use_correct_format(self, sample_model_id):
        """Test that non-custom providers use their actual provider names"""
        non_custom_providers = [
            (ModelProviderName.openai, "openai"),
            (ModelProviderName.anthropic, "anthropic"),
            (ModelProviderName.groq, "groq"),
            (ModelProviderName.gemini_api, "gemini"),
        ]

        for provider_name, expected_name in non_custom_providers:
            provider = KilnModelProvider(
                name=provider_name,
                model_id=sample_model_id,
            )

            result = get_litellm_provider_info(provider)

            assert result.provider_name == expected_name
            assert result.is_custom is False
            assert result.litellm_model_id == f"{expected_name}/{sample_model_id}"

    def test_litellm_model_id_format(self, embedding_provider):
        """Test that litellm_model_id follows the correct format"""
        result = get_litellm_provider_info(embedding_provider)

        expected_format = f"{result.provider_name}/{embedding_provider.model_id}"
        assert result.litellm_model_id == expected_format

    def test_return_type_structure(self, model_provider):
        """Test that the return type has all expected fields"""
        result = get_litellm_provider_info(model_provider)

        assert hasattr(result, "provider_name")
        assert hasattr(result, "is_custom")
        assert hasattr(result, "litellm_model_id")

        assert isinstance(result.provider_name, str)
        assert isinstance(result.is_custom, bool)
        assert isinstance(result.litellm_model_id, str)

    def test_works_with_both_provider_types(self, sample_model_id):
        """Test that function works with both KilnModelProvider and KilnEmbeddingModelProvider"""
        model_provider = KilnModelProvider(
            name=ModelProviderName.openai,
            model_id=sample_model_id,
        )

        embedding_provider = KilnEmbeddingModelProvider(
            name=ModelProviderName.openai,
            model_id=sample_model_id,
            n_dimensions=1536,
        )

        model_result = get_litellm_provider_info(model_provider)
        embedding_result = get_litellm_provider_info(embedding_provider)

        # Results should be identical for same provider name and model ID
        assert model_result.provider_name == embedding_result.provider_name
        assert model_result.is_custom == embedding_result.is_custom
        assert model_result.litellm_model_id == embedding_result.litellm_model_id

    def test_works_with_reranker_provider(self, sample_model_id):
        """Test that function works with KilnRerankerModelProvider"""
        reranker_provider = KilnRerankerModelProvider(
            name=ModelProviderName.together_ai,
            model_id=sample_model_id,
        )

        result = get_litellm_provider_info(reranker_provider)

        assert result.provider_name == "together_ai"
        assert result.is_custom is False
        assert result.litellm_model_id == f"together_ai/{sample_model_id}"
