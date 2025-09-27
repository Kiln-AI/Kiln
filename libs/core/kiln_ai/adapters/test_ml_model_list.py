from collections import Counter

import pytest

from kiln_ai.adapters.ml_model_list import (
    ModelName,
    built_in_models,
    built_in_models_from_provider,
    default_structured_output_mode_for_model_provider,
    get_model_by_name,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode


class TestDefaultStructuredOutputModeForModelProvider:
    """Test cases for default_structured_output_mode_for_model_provider function"""

    def test_valid_model_and_provider_returns_provider_mode(self):
        """Test that valid model and provider returns the provider's structured output mode"""
        # GPT 4.1 has OpenAI provider with json_schema mode
        result = default_structured_output_mode_for_model_provider(
            model_name="gpt_4_1",
            provider=ModelProviderName.openai,
        )
        assert result == StructuredOutputMode.json_schema

    def test_valid_model_different_provider_modes(self):
        """Test that different providers for the same model return different modes"""
        # Claude 3.5 Sonnet has different modes for different providers
        # Anthropic provider uses function_calling
        result_anthropic = default_structured_output_mode_for_model_provider(
            model_name="claude_3_5_sonnet",
            provider=ModelProviderName.anthropic,
        )
        assert result_anthropic == StructuredOutputMode.function_calling

        # Vertex provider uses function_calling_weak
        result_vertex = default_structured_output_mode_for_model_provider(
            model_name="claude_3_5_sonnet",
            provider=ModelProviderName.vertex,
        )
        assert result_vertex == StructuredOutputMode.function_calling_weak

    def test_invalid_model_name_returns_default(self):
        """Test that invalid model name returns the default value"""
        result = default_structured_output_mode_for_model_provider(
            model_name="invalid_model_name",
            provider=ModelProviderName.openai,
        )
        assert result == StructuredOutputMode.default

    def test_invalid_model_name_returns_custom_default(self):
        """Test that invalid model name returns custom default when specified"""
        custom_default = StructuredOutputMode.json_instructions
        result = default_structured_output_mode_for_model_provider(
            model_name="invalid_model_name",
            provider=ModelProviderName.openai,
            default=custom_default,
        )
        assert result == custom_default

    def test_valid_model_invalid_provider_returns_default(self):
        """Test that valid model but invalid provider returns default"""
        result = default_structured_output_mode_for_model_provider(
            model_name="gpt_4_1",
            provider=ModelProviderName.gemini_api,  # GPT 4.1 doesn't have gemini_api provider
        )
        assert result == StructuredOutputMode.default

    def test_disallowed_modes_returns_default(self):
        """Test that when provider's mode is in disallowed_modes, returns default"""
        # GPT 4.1 OpenAI provider uses json_schema, but we disallow it
        result = default_structured_output_mode_for_model_provider(
            model_name="gpt_4_1",
            provider=ModelProviderName.openai,
            disallowed_modes=[StructuredOutputMode.json_schema],
        )
        assert result == StructuredOutputMode.default

    def test_disallowed_modes_with_custom_default(self):
        """Test disallowed modes with custom default value"""
        custom_default = StructuredOutputMode.json_instructions
        result = default_structured_output_mode_for_model_provider(
            model_name="gpt_4_1",
            provider=ModelProviderName.openai,
            default=custom_default,
            disallowed_modes=[StructuredOutputMode.json_schema],
        )
        assert result == custom_default

    def test_empty_disallowed_modes_list(self):
        """Test that empty disallowed_modes list works correctly"""
        result = default_structured_output_mode_for_model_provider(
            model_name="gpt_4_1",
            provider=ModelProviderName.openai,
            disallowed_modes=[],
        )
        assert result == StructuredOutputMode.json_schema

    def test_multiple_disallowed_modes(self):
        """Test with multiple disallowed modes"""
        result = default_structured_output_mode_for_model_provider(
            model_name="gpt_4_1",
            provider=ModelProviderName.openai,
            disallowed_modes=[
                StructuredOutputMode.json_schema,
                StructuredOutputMode.function_calling,
            ],
        )
        assert result == StructuredOutputMode.default

    def test_reasoning_model_with_different_providers(self):
        """Test reasoning models that have different structured output modes"""
        # DeepSeek R1 uses json_instructions for reasoning
        result = default_structured_output_mode_for_model_provider(
            model_name="deepseek_r1",
            provider=ModelProviderName.openrouter,
        )
        assert result == StructuredOutputMode.json_instructions

    @pytest.mark.parametrize(
        "model_name,provider,expected_mode",
        [
            ("gpt_4o", ModelProviderName.openai, StructuredOutputMode.json_schema),
            (
                "claude_3_5_haiku",
                ModelProviderName.anthropic,
                StructuredOutputMode.function_calling,
            ),
            (
                "gemini_2_5_pro",
                ModelProviderName.gemini_api,
                StructuredOutputMode.json_schema,
            ),
            ("llama_3_1_8b", ModelProviderName.groq, StructuredOutputMode.default),
            (
                "qwq_32b",
                ModelProviderName.together_ai,
                StructuredOutputMode.json_instructions,
            ),
        ],
    )
    def test_parametrized_valid_combinations(self, model_name, provider, expected_mode):
        """Test multiple valid model/provider combinations"""
        result = default_structured_output_mode_for_model_provider(
            model_name=model_name,
            provider=provider,
        )
        assert result == expected_mode

    def test_model_with_single_provider(self):
        """Test model that only has one provider"""
        # Find a model with only one provider for this test
        model = get_model_by_name(ModelName.gpt_4_1_nano)
        assert len(model.providers) >= 1  # Verify it has providers

        first_provider = model.providers[0]
        result = default_structured_output_mode_for_model_provider(
            model_name="gpt_4_1_nano",
            provider=first_provider.name,
        )
        assert result == first_provider.structured_output_mode


class TestBuiltInModelsFromProvider:
    """Test cases for built_in_models_from_provider function"""

    def test_valid_model_and_provider_returns_provider(self):
        """Test that valid model and provider returns the correct provider configuration"""
        # GPT 4.1 has OpenAI provider
        result = built_in_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name="gpt_4_1",
        )
        assert result is not None
        assert result.name == ModelProviderName.openai
        assert result.model_id == "gpt-4.1"
        assert result.supports_logprobs is True
        assert result.suggested_for_data_gen is True

    def test_valid_model_different_provider_returns_correct_provider(self):
        """Test that different providers for the same model return different configurations"""
        # GPT 4.1 has multiple providers with different configurations
        openai_provider = built_in_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name="gpt_4_1",
        )
        openrouter_provider = built_in_models_from_provider(
            provider_name=ModelProviderName.openrouter,
            model_name="gpt_4_1",
        )

        assert openai_provider is not None
        assert openrouter_provider is not None
        assert openai_provider.name == ModelProviderName.openai
        assert openrouter_provider.name == ModelProviderName.openrouter
        assert openai_provider.model_id == "gpt-4.1"
        assert openrouter_provider.model_id == "openai/gpt-4.1"

    def test_invalid_model_name_returns_none(self):
        """Test that invalid model name returns None"""
        result = built_in_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name="invalid_model_name",
        )
        assert result is None

    def test_valid_model_invalid_provider_returns_none(self):
        """Test that valid model but invalid provider returns None"""
        result = built_in_models_from_provider(
            provider_name=ModelProviderName.gemini_api,  # GPT 4.1 doesn't have gemini_api provider
            model_name="gpt_4_1",
        )
        assert result is None

    def test_model_with_single_provider(self):
        """Test model that only has one provider"""
        # Find a model with only one provider for this test
        model = get_model_by_name(ModelName.gpt_4_1_nano)
        assert len(model.providers) >= 1  # Verify it has providers

        first_provider = model.providers[0]
        result = built_in_models_from_provider(
            provider_name=first_provider.name,
            model_name="gpt_4_1_nano",
        )
        assert result is not None
        assert result.name == first_provider.name
        assert result.model_id == first_provider.model_id

    def test_model_with_multiple_providers(self):
        """Test model that has multiple providers"""
        # GPT 4.1 has multiple providers
        openai_result = built_in_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name="gpt_4_1",
        )
        openrouter_result = built_in_models_from_provider(
            provider_name=ModelProviderName.openrouter,
            model_name="gpt_4_1",
        )
        azure_result = built_in_models_from_provider(
            provider_name=ModelProviderName.azure_openai,
            model_name="gpt_4_1",
        )

        assert openai_result is not None
        assert openrouter_result is not None
        assert azure_result is not None
        assert openai_result.name == ModelProviderName.openai
        assert openrouter_result.name == ModelProviderName.openrouter
        assert azure_result.name == ModelProviderName.azure_openai

    def test_case_sensitive_model_name(self):
        """Test that model name matching is case sensitive"""
        # Should return None for case-mismatched model name
        result = built_in_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name="GPT_4_1",  # Wrong case
        )
        assert result is None

    def test_provider_specific_attributes(self):
        """Test that provider-specific attributes are correctly returned"""
        # Test a provider with specific attributes like multimodal_capable
        result = built_in_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name="gpt_4_1",
        )
        assert result is not None
        assert result.multimodal_capable is True
        assert result.supports_doc_extraction is True
        assert result.multimodal_mime_types is not None
        assert len(result.multimodal_mime_types) > 0

    def test_provider_without_special_attributes(self):
        """Test provider that doesn't have special attributes"""
        # Test a simpler provider configuration
        result = built_in_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name="gpt_4_1_nano",
        )
        assert result is not None
        assert result.multimodal_capable is False  # Should be False for nano
        assert result.supports_doc_extraction is False

    @pytest.mark.parametrize(
        "model_name,provider,expected_model_id",
        [
            ("gpt_4o", ModelProviderName.openai, "gpt-4o"),
            (
                "claude_3_5_haiku",
                ModelProviderName.anthropic,
                "claude-3-5-haiku-20241022",
            ),
            ("gemini_2_5_pro", ModelProviderName.gemini_api, "gemini-2.5-pro"),
            ("llama_3_1_8b", ModelProviderName.groq, "llama-3.1-8b-instant"),
        ],
    )
    def test_parametrized_valid_combinations(
        self, model_name, provider, expected_model_id
    ):
        """Test multiple valid model/provider combinations"""
        result = built_in_models_from_provider(
            provider_name=provider,
            model_name=model_name,
        )
        assert result is not None
        assert result.name == provider
        assert result.model_id == expected_model_id

    def test_empty_string_model_name(self):
        """Test that empty string model name returns None"""
        result = built_in_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name="",
        )
        assert result is None

    def test_none_model_name(self):
        """Test that None model name returns None"""
        result = built_in_models_from_provider(
            provider_name=ModelProviderName.openai,
            model_name=None,  # type: ignore
        )
        assert result is None

    def test_all_built_in_models_have_valid_providers(self):
        """Test that all built-in models have at least one valid provider"""
        for model in built_in_models:
            assert len(model.providers) > 0, f"Model {model.name} has no providers"
            for provider in model.providers:
                # Test that we can retrieve each provider
                result = built_in_models_from_provider(
                    provider_name=provider.name,
                    model_name=model.name,
                )
                assert result is not None, (
                    f"Could not retrieve provider {provider.name} for model {model.name}"
                )
                assert result.name == provider.name
                assert result.model_id == provider.model_id


def test_uncensored():
    """Test that uncensored is set correctly"""
    model = get_model_by_name(ModelName.grok_3_mini)
    for provider in model.providers:
        assert provider.uncensored
        assert not provider.suggested_for_uncensored_data_gen

    model = get_model_by_name(ModelName.gpt_4_1_nano)
    for provider in model.providers:
        assert not provider.uncensored
        assert not provider.suggested_for_uncensored_data_gen

    model = get_model_by_name(ModelName.grok_4)
    for provider in model.providers:
        assert provider.uncensored
        assert provider.suggested_for_uncensored_data_gen


def test_no_empty_multimodal_mime_types():
    """Ensure that multimodal fields are self-consistent as they are interdependent"""
    for model in built_in_models:
        for provider in model.providers:
            # a multimodal model should always have mime types it supports
            if provider.multimodal_capable:
                assert provider.multimodal_mime_types is not None
                assert len(provider.multimodal_mime_types) > 0

            # a model that specifies mime types is necessarily multimodal
            if (
                provider.multimodal_mime_types is not None
                and len(provider.multimodal_mime_types) > 0
            ):
                assert provider.multimodal_capable

            # a model that supports doc extraction is necessarily multimodal
            if provider.supports_doc_extraction:
                assert provider.multimodal_capable


def test_no_reasoning_for_structured_output():
    """Test that no reasoning is returned for structured output"""
    # get all models
    for model in built_in_models:
        for provider in model.providers:
            if provider.reasoning_optional_for_structured_output is not None:
                assert provider.reasoning_capable, (
                    f"{model.name} {provider.name} has reasoning_optional_for_structured_output but is not reasoning capable. This field should only be defined for models that are reasoning capable."
                )


def test_unique_providers_per_model():
    """Test that each model can only have one entry per provider"""
    for model in built_in_models:
        provider_names = [provider.name for provider in model.providers]
        unique_provider_names = set(provider_names)

        if len(provider_names) != len(unique_provider_names):
            # Find which providers have duplicates
            provider_counts = Counter(provider_names)
            duplicates = {
                name: count for name, count in provider_counts.items() if count > 1
            }

            # Show details about duplicates
            duplicate_details = []
            for provider_name, count in duplicates.items():
                duplicate_providers = [
                    p for p in model.providers if p.name == provider_name
                ]
                model_ids = [p.model_id for p in duplicate_providers]
                duplicate_details.append(
                    f"{provider_name} (appears {count} times with model_ids: {model_ids})"
                )

            assert False, (
                f"Model {model.name} has duplicate providers:\n"
                f"Expected: 1 entry per provider\n"
                f"Found: {len(provider_names)} total entries, {len(unique_provider_names)} unique providers\n"
                f"Duplicates: {', '.join(duplicate_details)}\n"
                f"This suggests either:\n"
                f"1. A bug where the same provider is accidentally duplicated, or\n"
                f"2. Intentional design where the same provider offers different model variants\n"
                f"If this is intentional, the test should be updated to allow multiple entries per provider."
            )
