from typing import List

import pytest

from kiln_ai.adapters.embedding.embedding_registry import embedding_adapter_from_type
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
from kiln_ai.datamodel.embedding import EmbeddingConfig


@pytest.fixture
def litellm_adapter():
    adapter = embedding_adapter_from_type(
        EmbeddingConfig(
            name="test-embedding",
            model_provider_name=ModelProviderName.openai,
            model_name=EmbeddingModelName.openai_text_embedding_3_small,
            properties={},
        )
    )
    return adapter


def get_all_embedding_models_and_providers() -> List[tuple[str, str]]:
    return [
        (model.name, provider.name)
        for model in built_in_embedding_models
        for provider in model.providers
    ]


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
            friendly_name="Text Embedding 3 Small",
            providers=providers,
        )

        assert model.family == KilnEmbeddingModelFamily.openai
        assert model.name == EmbeddingModelName.openai_text_embedding_3_small
        assert model.friendly_name == "Text Embedding 3 Small"
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


class TestGetModelByName:
    def test_get_nonexistent_model_raises_error(self):
        """Test that getting a nonexistent model raises ValueError"""
        with pytest.raises(
            ValueError, match="Embedding model nonexistent_model not found"
        ):
            get_model_by_name("nonexistent_model")  # type: ignore

    @pytest.mark.parametrize(
        "model_name",
        [model.name for model in built_in_embedding_models],
    )
    def test_model_retrieval(self, model_name):
        """Test retrieving models with parametrized test cases"""
        model = get_model_by_name(model_name)
        assert model.family == model.family
        assert model.friendly_name == model.friendly_name


class TestBuiltInEmbeddingModelsFromProvider:
    @pytest.mark.parametrize(
        "model_name,provider_name", get_all_embedding_models_and_providers()
    )
    def test_get_all_existing_models_and_providers(self, model_name, provider_name):
        provider = built_in_embedding_models_from_provider(provider_name, model_name)

        assert provider is not None
        assert provider.name == provider_name
        assert provider.model_id == provider.model_id
        assert provider.n_dimensions == provider.n_dimensions
        assert provider.max_input_tokens == provider.max_input_tokens
        assert (
            provider.supports_custom_dimensions == provider.supports_custom_dimensions
        )

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


class TestGenerateEmbedding:
    """Test cases for generate_embedding function"""

    @pytest.mark.parametrize(
        "model_name,provider_name", get_all_embedding_models_and_providers()
    )
    @pytest.mark.paid
    async def test_generate_embedding(self, model_name, provider_name):
        """Test generating an embedding"""
        model_provider = built_in_embedding_models_from_provider(
            provider_name, model_name
        )
        assert model_provider is not None

        embedding = embedding_adapter_from_type(
            EmbeddingConfig(
                name="test-embedding",
                model_provider_name=provider_name,
                model_name=model_name,
                properties={},
            )
        )
        embedding = await embedding.generate_embeddings(["Hello, world!"])
        assert len(embedding.embeddings) == 1
        assert len(embedding.embeddings[0].vector) == model_provider.n_dimensions

    @pytest.mark.parametrize(
        "model_name,provider_name", get_all_embedding_models_and_providers()
    )
    @pytest.mark.paid
    async def test_generate_embedding_with_user_supplied_dimensions(
        self, model_name, provider_name
    ):
        """Test generating an embedding with user supplied dimensions"""
        model_provider = built_in_embedding_models_from_provider(
            provider_name=provider_name,
            model_name=model_name,
        )
        assert model_provider is not None

        if not model_provider.supports_custom_dimensions:
            pytest.skip("Model does not support custom dimensions")

        # max dim
        max_dimensions = model_provider.n_dimensions
        dimensions_target = max_dimensions // 2

        embedding = embedding_adapter_from_type(
            EmbeddingConfig(
                name="test-embedding",
                model_provider_name=provider_name,
                model_name=model_name,
                properties={"dimensions": dimensions_target},
            )
        )
        embedding = await embedding.generate_embeddings(["Hello, world!"])
        assert len(embedding.embeddings) == 1
        assert len(embedding.embeddings[0].vector) == dimensions_target
