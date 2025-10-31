from unittest.mock import patch

import pytest
from pydantic import ValidationError

from kiln_ai.adapters.reranker_list import (
    KilnRerankerModel,
    KilnRerankerModelProvider,
    RerankerModelName,
    built_in_reranker_models_from_provider,
    get_model_by_name,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName


class TestKilnRerankerModelProvider:
    """Test cases for KilnRerankerModelProvider model."""

    def test_valid_provider_creation(self):
        """Test creating a valid provider."""
        provider = KilnRerankerModelProvider(
            name=ModelProviderName.together_ai, model_id="Salesforce/Llama-Rank-V1"
        )
        assert provider.name == ModelProviderName.together_ai
        assert provider.model_id == "Salesforce/Llama-Rank-V1"

    def test_provider_with_different_providers(self):
        """Test creating providers with different provider names."""
        providers = [
            KilnRerankerModelProvider(name=ModelProviderName.openai, model_id="gpt-4"),
            KilnRerankerModelProvider(
                name=ModelProviderName.anthropic, model_id="claude-3"
            ),
            KilnRerankerModelProvider(
                name=ModelProviderName.together_ai, model_id="Salesforce/Llama-Rank-V1"
            ),
        ]

        for provider in providers:
            assert isinstance(provider.name, ModelProviderName)
            assert isinstance(provider.model_id, str)
            assert len(provider.model_id) > 0

    def test_provider_model_id_validation(self):
        """Test that model_id cannot be created with empty string."""
        with pytest.raises(ValidationError):
            KilnRerankerModelProvider(
                name=ModelProviderName.together_ai,
                model_id="",
            )


class TestKilnRerankerModel:
    """Test cases for KilnRerankerModel model."""

    def test_valid_model_creation(self):
        """Test creating a valid reranker model."""
        provider = KilnRerankerModelProvider(
            name=ModelProviderName.together_ai, model_id="Salesforce/Llama-Rank-V1"
        )

        model = KilnRerankerModel(
            family="llama_rank",
            name="llama_rank",
            friendly_name="LlamaRank",
            providers=[provider],
        )

        assert model.family == "llama_rank"
        assert model.name == "llama_rank"
        assert model.friendly_name == "LlamaRank"
        assert len(model.providers) == 1
        assert model.providers[0] == provider

    def test_model_with_multiple_providers(self):
        """Test creating a model with multiple providers."""

        model = KilnRerankerModel(
            family="llama_rank",
            name="llama_rank",
            friendly_name="LlamaRank",
            providers=[
                KilnRerankerModelProvider(
                    name=ModelProviderName.together_ai,
                    model_id="Salesforce/Llama-Rank-V1",
                ),
                KilnRerankerModelProvider(
                    name=ModelProviderName.openai, model_id="gpt-4-rerank"
                ),
            ],
        )

        assert len(model.providers) == 2
        assert model.providers[0].name == ModelProviderName.together_ai
        assert model.providers[1].name == ModelProviderName.openai

    def test_model_empty_providers_list(self):
        """Test creating a model with empty providers list."""
        model = KilnRerankerModel(
            family="test_family",
            name="test_name",
            friendly_name="Test Model",
            providers=[],
        )

        assert model.family == "test_family"
        assert model.name == "test_name"
        assert model.friendly_name == "Test Model"
        assert len(model.providers) == 0


class TestGetModelByName:
    """Test cases for get_model_by_name function."""

    def test_get_existing_model(self):
        """Test getting an existing model by name."""
        model = get_model_by_name(RerankerModelName.llama_rank)
        assert isinstance(model, KilnRerankerModel)
        assert model.name == RerankerModelName.llama_rank
        assert model.family == "llama_rank"
        assert model.friendly_name == "LlamaRank"

    def test_get_nonexistent_model(self):
        """Test getting a non-existent model raises ValueError."""
        with pytest.raises(
            ValueError,
            match=r"Reranker model .* not found in the list of built-in models",
        ):
            get_model_by_name("nonexistent_model")

    def test_get_model_with_string_name(self):
        """Test getting model with string name instead of enum."""
        # This should work since the function compares model.name (string) with the input
        model = get_model_by_name("llama_rank")
        assert isinstance(model, KilnRerankerModel)
        assert model.name == "llama_rank"

    @patch("kiln_ai.adapters.reranker_list.built_in_rerankers")
    def test_get_model_with_empty_list(self, mock_built_in_rerankers):
        """Test getting model when built_in_rerankers is empty."""
        mock_built_in_rerankers.__iter__ = lambda self: iter([])

        with pytest.raises(
            ValueError,
            match=r"Reranker model .* not found in the list of built-in models",
        ):
            get_model_by_name(RerankerModelName.llama_rank)


class TestBuiltInRerankerModelsFromProvider:
    """Test cases for built_in_reranker_models_from_provider function."""

    def test_get_existing_provider(self):
        """Test getting an existing provider."""
        provider = built_in_reranker_models_from_provider(
            ModelProviderName.together_ai, "llama_rank"
        )

        assert provider is not None
        assert isinstance(provider, KilnRerankerModelProvider)
        assert provider.name == ModelProviderName.together_ai
        assert provider.model_id == "Salesforce/Llama-Rank-V1"

    def test_get_nonexistent_model(self):
        """Test getting provider for non-existent model."""
        provider = built_in_reranker_models_from_provider(
            ModelProviderName.together_ai, "nonexistent_model"
        )

        assert provider is None

    def test_get_nonexistent_provider(self):
        """Test getting non-existent provider for existing model."""
        provider = built_in_reranker_models_from_provider(
            ModelProviderName.openai,  # This provider doesn't exist for llama_rank
            "llama_rank",
        )

        assert provider is None

    def test_get_provider_with_string_provider_name(self):
        """Test getting provider with string provider name."""
        provider = built_in_reranker_models_from_provider(
            "together_ai",  # String instead of enum
            "llama_rank",
        )

        assert provider is not None
        assert provider.name == ModelProviderName.together_ai

    @patch("kiln_ai.adapters.reranker_list.built_in_rerankers")
    def test_get_provider_with_empty_list(self, mock_built_in_rerankers):
        """Test getting provider when built_in_rerankers is empty."""
        mock_built_in_rerankers.__iter__ = lambda self: iter([])

        provider = built_in_reranker_models_from_provider(
            ModelProviderName.together_ai, "llama_rank"
        )

        assert provider is None

    @patch("kiln_ai.adapters.reranker_list.built_in_rerankers")
    def test_get_provider_with_multiple_models(self, mock_built_in_rerankers):
        """Test getting provider when multiple models exist."""
        # Create mock models
        provider1 = KilnRerankerModelProvider(
            name=ModelProviderName.together_ai, model_id="Salesforce/Llama-Rank-V1"
        )
        provider2 = KilnRerankerModelProvider(
            name=ModelProviderName.openai, model_id="gpt-4-rerank"
        )

        model1 = KilnRerankerModel(
            family="llama_rank",
            name="llama_rank",
            friendly_name="LlamaRank",
            providers=[provider1],
        )

        model2 = KilnRerankerModel(
            family="test_family",
            name="test_model",
            friendly_name="Test Model",
            providers=[provider2],
        )

        mock_built_in_rerankers.__iter__ = lambda self: iter([model1, model2])

        # Test getting provider from first model
        provider = built_in_reranker_models_from_provider(
            ModelProviderName.together_ai, "llama_rank"
        )

        assert provider is not None
        assert provider.name == ModelProviderName.together_ai
        assert provider.model_id == "Salesforce/Llama-Rank-V1"

        # Test getting provider from second model
        provider = built_in_reranker_models_from_provider(
            ModelProviderName.openai, "test_model"
        )

        assert provider is not None
        assert provider.name == ModelProviderName.openai
        assert provider.model_id == "gpt-4-rerank"
