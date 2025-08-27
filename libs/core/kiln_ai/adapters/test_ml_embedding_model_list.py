import pytest

from kiln_ai.adapters.ml_embedding_model_list import (
    EmbeddingModelName,
    KilnEmbeddingModel,
    KilnEmbeddingModelFamily,
    KilnEmbeddingModelProvider,
    built_in_embedding_models,
    built_in_embedding_models_from_provider,
    get_model_by_name,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName


class TestEmbeddingModelName:
    """Test cases for EmbeddingModelName enum"""

    def test_enum_values(self):
        """Test that enum values are correctly defined"""
        assert (
            EmbeddingModelName.openai_text_embedding_3_small
            == "openai_text_embedding_3_small"
        )
        assert (
            EmbeddingModelName.openai_text_embedding_3_large
            == "openai_text_embedding_3_large"
        )
        assert (
            EmbeddingModelName.gemini_text_embedding_004 == "gemini_text_embedding_004"
        )


class TestKilnEmbeddingModelProvider:
    """Test cases for KilnEmbeddingModelProvider model"""

    def test_basic_provider_creation(self):
        """Test creating a basic provider with required fields"""
        provider = KilnEmbeddingModelProvider(
            name=ModelProviderName.openai,
            model_id="text-embedding-3-small",
            max_input_tokens=8192,
            n_dimensions=1536,
            supports_custom_dimensions=True,
        )

        assert provider.name == ModelProviderName.openai
        assert provider.model_id == "text-embedding-3-small"
        assert provider.max_input_tokens == 8192
        assert provider.n_dimensions == 1536
        assert provider.supports_custom_dimensions is True

    def test_provider_with_optional_fields_unspecified(self):
        """Test creating a provider with optional fields not specified"""
        provider = KilnEmbeddingModelProvider(
            name=ModelProviderName.gemini_api,
            model_id="text-embedding-004",
            n_dimensions=768,
        )

        assert provider.name == ModelProviderName.gemini_api
        assert provider.model_id == "text-embedding-004"
        assert provider.max_input_tokens is None
        assert provider.n_dimensions == 768
        assert provider.supports_custom_dimensions is False


class TestKilnEmbeddingModel:
    """Test cases for KilnEmbeddingModel model"""

    def test_basic_model_creation(self):
        """Test creating a basic model with required fields"""
        providers = [
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openai,
                model_id="text-embedding-3-small",
                n_dimensions=1536,
                max_input_tokens=8192,
            )
        ]

        model = KilnEmbeddingModel(
            family=KilnEmbeddingModelFamily.openai,
            name=EmbeddingModelName.openai_text_embedding_3_small,
            friendly_name="text-embedding-3-small",
            providers=providers,
        )

        assert model.family == KilnEmbeddingModelFamily.openai
        assert model.name == EmbeddingModelName.openai_text_embedding_3_small
        assert model.friendly_name == "text-embedding-3-small"
        assert len(model.providers) == 1
        assert model.providers[0].name == ModelProviderName.openai

    def test_model_with_multiple_providers(self):
        """Test creating a model with multiple providers"""
        providers = [
            KilnEmbeddingModelProvider(
                name=ModelProviderName.openai,
                model_id="model-1",
                n_dimensions=1536,
                max_input_tokens=8192,
            ),
            KilnEmbeddingModelProvider(
                name=ModelProviderName.anthropic,
                model_id="model-1",
                n_dimensions=1536,
                max_input_tokens=8192,
            ),
        ]

        model = KilnEmbeddingModel(
            family=KilnEmbeddingModelFamily.openai,
            name=EmbeddingModelName.openai_text_embedding_3_small,
            friendly_name="text-embedding-3-small",
            providers=providers,
        )

        assert len(model.providers) == 2
        assert model.providers[0].name == ModelProviderName.openai
        assert model.providers[1].name == ModelProviderName.anthropic


class TestEmbeddingModelsList:
    """Test cases for the embedding_models list"""

    def test_embedding_models_not_empty(self):
        """Test that the embedding_models list is not empty"""
        assert len(built_in_embedding_models) > 0

    def test_all_models_have_required_fields(self):
        """Test that all models in the list have required fields"""
        for model in built_in_embedding_models:
            assert hasattr(model, "family")
            assert hasattr(model, "name")
            assert hasattr(model, "friendly_name")
            assert hasattr(model, "providers")
            assert isinstance(model.name, str)
            assert isinstance(model.friendly_name, str)
            assert isinstance(model.providers, list)
            assert len(model.providers) > 0

    def test_all_providers_have_required_fields(self):
        """Test that all providers in all models have required fields"""
        for model in built_in_embedding_models:
            for provider in model.providers:
                assert hasattr(provider, "name")
                assert isinstance(provider.name, ModelProviderName)

    def test_model_names_are_unique(self):
        """Test that all model names in the list are unique"""
        model_names = [model.name for model in built_in_embedding_models]
        assert len(model_names) == len(set(model_names))

    def test_specific_models_exist(self):
        """Test that specific expected models exist in the list"""
        model_names = [model.name for model in built_in_embedding_models]

        assert EmbeddingModelName.openai_text_embedding_3_small in model_names
        assert EmbeddingModelName.openai_text_embedding_3_large in model_names
        assert EmbeddingModelName.gemini_text_embedding_004 in model_names

    def test_openai_embedding_models(self):
        """Test specific OpenAI embedding models"""
        openai_models = [
            model
            for model in built_in_embedding_models
            if model.family == KilnEmbeddingModelFamily.openai
        ]

        assert len(openai_models) >= 2  # Should have at least 2 OpenAI models

        # Check for specific OpenAI models
        openai_model_names = [model.name for model in openai_models]
        assert EmbeddingModelName.openai_text_embedding_3_small in openai_model_names
        assert EmbeddingModelName.openai_text_embedding_3_large in openai_model_names

    def test_gemini_embedding_models(self):
        """Test specific Gemini embedding models"""
        gemini_models = [
            model
            for model in built_in_embedding_models
            if model.family == KilnEmbeddingModelFamily.gemini
        ]

        assert len(gemini_models) >= 1  # Should have at least 1 Gemini model

        # Check for specific Gemini model
        gemini_model_names = [model.name for model in gemini_models]
        assert EmbeddingModelName.gemini_text_embedding_004 in gemini_model_names

    def test_openai_text_embedding_3_small_details(self):
        """Test specific details of OpenAI text-embedding-3-small model"""
        model = get_model_by_name(EmbeddingModelName.openai_text_embedding_3_small)

        assert model.family == KilnEmbeddingModelFamily.openai
        assert model.friendly_name == "text-embedding-3-small"
        assert len(model.providers) == 1

        provider = model.providers[0]
        assert provider.name == ModelProviderName.openai
        assert provider.model_id == "text-embedding-3-small"
        assert provider.n_dimensions == 1536
        assert provider.max_input_tokens == 8192
        assert provider.supports_custom_dimensions is True

    def test_openai_text_embedding_3_large_details(self):
        """Test specific details of OpenAI text-embedding-3-large model"""
        model = get_model_by_name(EmbeddingModelName.openai_text_embedding_3_large)

        assert model.family == KilnEmbeddingModelFamily.openai
        assert model.friendly_name == "text-embedding-3-large"
        assert len(model.providers) == 1

        provider = model.providers[0]
        assert provider.name == ModelProviderName.openai
        assert provider.model_id == "text-embedding-3-large"
        assert provider.n_dimensions == 3072
        assert provider.max_input_tokens == 8192
        assert provider.supports_custom_dimensions is True

    def test_gemini_text_embedding_004_details(self):
        """Test specific details of Gemini text-embedding-004 model"""
        model = get_model_by_name(EmbeddingModelName.gemini_text_embedding_004)

        assert model.family == KilnEmbeddingModelFamily.gemini
        assert model.friendly_name == "text-embedding-004"
        assert len(model.providers) == 1

        provider = model.providers[0]
        assert provider.name == ModelProviderName.gemini_api
        assert provider.model_id == "text-embedding-004"
        assert provider.n_dimensions == 768
        assert provider.max_input_tokens == 2048
        assert provider.supports_custom_dimensions is False


class TestGetModelByName:
    """Test cases for get_model_by_name function"""

    def test_get_existing_model(self):
        """Test getting an existing model by name"""
        model = get_model_by_name(EmbeddingModelName.openai_text_embedding_3_small)
        assert model.name == EmbeddingModelName.openai_text_embedding_3_small
        assert model.family == KilnEmbeddingModelFamily.openai

    def test_get_all_existing_models(self):
        """Test getting all existing models by name"""
        for model_name in EmbeddingModelName:
            model = get_model_by_name(model_name)
            assert model.name == model_name

    def test_get_nonexistent_model_raises_error(self):
        """Test that getting a nonexistent model raises ValueError"""
        with pytest.raises(
            ValueError, match="Embedding model nonexistent_model not found"
        ):
            get_model_by_name("nonexistent_model")

    def test_get_model_with_invalid_enum_value(self):
        """Test that getting a model with invalid enum value raises ValueError"""
        with pytest.raises(ValueError, match="Embedding model invalid_enum not found"):
            get_model_by_name("invalid_enum")

    @pytest.mark.parametrize(
        "model_name,expected_family,expected_friendly_name",
        [
            (
                EmbeddingModelName.openai_text_embedding_3_small,
                KilnEmbeddingModelFamily.openai,
                "text-embedding-3-small",
            ),
            (
                EmbeddingModelName.openai_text_embedding_3_large,
                KilnEmbeddingModelFamily.openai,
                "text-embedding-3-large",
            ),
            (
                EmbeddingModelName.gemini_text_embedding_004,
                KilnEmbeddingModelFamily.gemini,
                "text-embedding-004",
            ),
        ],
    )
    def test_parametrized_model_retrieval(
        self, model_name, expected_family, expected_friendly_name
    ):
        """Test retrieving models with parametrized test cases"""
        model = get_model_by_name(model_name)
        assert model.family == expected_family
        assert model.friendly_name == expected_friendly_name


class TestBuiltInEmbeddingModelsFromProvider:
    """Test cases for built_in_embedding_models_from_provider function"""

    def test_get_existing_provider_for_model(self):
        """Test getting an existing provider for a model"""
        provider = built_in_embedding_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name=EmbeddingModelName.openai_text_embedding_3_small,
        )

        assert provider is not None
        assert provider.name == ModelProviderName.openai
        assert provider.model_id == "text-embedding-3-small"
        assert provider.n_dimensions == 1536

    def test_get_all_existing_provider_model_combinations(self):
        """Test getting all existing provider-model combinations"""
        combinations = [
            (
                ModelProviderName.openai,
                EmbeddingModelName.openai_text_embedding_3_small,
            ),
            (
                ModelProviderName.openai,
                EmbeddingModelName.openai_text_embedding_3_large,
            ),
            (
                ModelProviderName.gemini_api,
                EmbeddingModelName.gemini_text_embedding_004,
            ),
        ]

        for provider_name, model_name in combinations:
            provider = built_in_embedding_models_from_provider(
                provider_name, model_name
            )
            assert provider is not None
            assert provider.name == provider_name

    def test_get_nonexistent_provider_returns_none(self):
        """Test that getting a nonexistent provider returns None"""
        provider = built_in_embedding_models_from_provider(
            provider_name=ModelProviderName.anthropic,  # Not used for embeddings
            model_name=EmbeddingModelName.openai_text_embedding_3_small,
        )
        assert provider is None

    def test_get_nonexistent_model_returns_none(self):
        """Test that getting a nonexistent model returns None"""
        provider = built_in_embedding_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name="nonexistent_model",
        )
        assert provider is None

    def test_get_wrong_provider_for_model_returns_none(self):
        """Test that getting wrong provider for a model returns None"""
        provider = built_in_embedding_models_from_provider(
            provider_name=ModelProviderName.gemini_api,
            model_name=EmbeddingModelName.openai_text_embedding_3_small,
        )
        assert provider is None

    def test_get_openai_text_embedding_3_small_provider_details(self):
        """Test specific details of OpenAI text-embedding-3-small provider"""
        provider = built_in_embedding_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name=EmbeddingModelName.openai_text_embedding_3_small,
        )

        assert provider is not None
        assert provider.name == ModelProviderName.openai
        assert provider.model_id == "text-embedding-3-small"
        assert provider.n_dimensions == 1536
        assert provider.max_input_tokens == 8192
        assert provider.supports_custom_dimensions is True

    def test_get_openai_text_embedding_3_large_provider_details(self):
        """Test specific details of OpenAI text-embedding-3-large provider"""
        provider = built_in_embedding_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name=EmbeddingModelName.openai_text_embedding_3_large,
        )

        assert provider is not None
        assert provider.name == ModelProviderName.openai
        assert provider.model_id == "text-embedding-3-large"
        assert provider.n_dimensions == 3072
        assert provider.max_input_tokens == 8192
        assert provider.supports_custom_dimensions is True

    def test_get_gemini_text_embedding_004_provider_details(self):
        """Test specific details of Gemini text-embedding-004 provider"""
        provider = built_in_embedding_models_from_provider(
            provider_name=ModelProviderName.gemini_api,
            model_name=EmbeddingModelName.gemini_text_embedding_004,
        )

        assert provider is not None
        assert provider.name == ModelProviderName.gemini_api
        assert provider.model_id == "text-embedding-004"
        assert provider.n_dimensions == 768
        assert provider.max_input_tokens == 2048
        assert provider.supports_custom_dimensions is False

    @pytest.mark.parametrize(
        "provider_name,model_name,expected_model_id,expected_dimensions",
        [
            (
                ModelProviderName.openai,
                EmbeddingModelName.openai_text_embedding_3_small,
                "text-embedding-3-small",
                1536,
            ),
            (
                ModelProviderName.openai,
                EmbeddingModelName.openai_text_embedding_3_large,
                "text-embedding-3-large",
                3072,
            ),
            (
                ModelProviderName.gemini_api,
                EmbeddingModelName.gemini_text_embedding_004,
                "text-embedding-004",
                768,
            ),
        ],
    )
    def test_parametrized_provider_retrieval(
        self, provider_name, model_name, expected_model_id, expected_dimensions
    ):
        """Test retrieving providers with parametrized test cases"""
        provider = built_in_embedding_models_from_provider(provider_name, model_name)

        assert provider is not None
        assert provider.model_id == expected_model_id
        assert provider.n_dimensions == expected_dimensions
