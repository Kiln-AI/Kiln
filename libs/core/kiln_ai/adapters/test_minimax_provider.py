"""Tests for MiniMax as a first-class LLM provider."""

import os
from unittest.mock import Mock, patch

import pytest

from kiln_ai.adapters.ml_model_list import (
    ModelFamily,
    ModelName,
    ModelProviderName,
    built_in_models,
)
from kiln_ai.adapters.provider_tools import (
    LiteLlmCoreConfig,
    check_provider_warnings,
    lite_llm_core_config_for_provider,
    provider_name_from_id,
    provider_warnings,
)
from kiln_ai.utils.litellm import get_litellm_provider_info


class TestMiniMaxProviderName:
    """Tests for MiniMax in the provider name mapping."""

    def test_provider_name_from_id(self):
        assert provider_name_from_id(ModelProviderName.minimax) == "MiniMax"

    def test_minimax_in_provider_warnings(self):
        assert ModelProviderName.minimax in provider_warnings
        warning = provider_warnings[ModelProviderName.minimax]
        assert "minimax_api_key" in warning.required_config_keys
        assert "api key" in warning.message.lower()

    def test_check_provider_warnings_missing_key(self):
        with patch(
            "kiln_ai.adapters.provider_tools.get_config_value", return_value=None
        ):
            with pytest.raises(ValueError, match="MiniMax"):
                check_provider_warnings(ModelProviderName.minimax)

    def test_check_provider_warnings_key_present(self):
        with patch(
            "kiln_ai.adapters.provider_tools.get_config_value",
            return_value="test-key",
        ):
            # Should not raise
            check_provider_warnings(ModelProviderName.minimax)


class TestMiniMaxLiteLlmConfig:
    """Tests for MiniMax LiteLLM core configuration."""

    def test_litellm_core_config_default_url(self):
        with patch("kiln_ai.adapters.provider_tools.Config") as mock_config:
            config_instance = Mock()
            mock_config.shared.return_value = config_instance
            config_instance.minimax_api_key = "test-minimax-key"

            config = lite_llm_core_config_for_provider(ModelProviderName.minimax)

            assert config is not None
            assert config.base_url == "https://api.minimax.io/v1"
            assert config.additional_body_options == {"api_key": "test-minimax-key"}

    @patch.dict("os.environ", {"MINIMAX_BASE_URL": "https://custom.minimax.io/v1"})
    def test_litellm_core_config_custom_url(self):
        with patch("kiln_ai.adapters.provider_tools.Config") as mock_config:
            config_instance = Mock()
            mock_config.shared.return_value = config_instance
            config_instance.minimax_api_key = "test-key"

            config = lite_llm_core_config_for_provider(ModelProviderName.minimax)

            assert config is not None
            assert config.base_url == "https://custom.minimax.io/v1"


class TestMiniMaxLiteLlmProviderInfo:
    """Tests for MiniMax in the litellm provider info mapping."""

    def test_minimax_is_custom_provider(self):
        from kiln_ai.adapters.ml_model_list import KilnModelProvider

        mp = KilnModelProvider(
            name=ModelProviderName.minimax, model_id="MiniMax-M2.7"
        )
        info = get_litellm_provider_info(mp)

        assert info.is_custom is True
        assert info.provider_name == "openai"
        assert info.litellm_model_id == "openai/MiniMax-M2.7"

    def test_minimax_m25_provider_info(self):
        from kiln_ai.adapters.ml_model_list import KilnModelProvider

        mp = KilnModelProvider(
            name=ModelProviderName.minimax, model_id="MiniMax-M2.5"
        )
        info = get_litellm_provider_info(mp)

        assert info.is_custom is True
        assert info.litellm_model_id == "openai/MiniMax-M2.5"


class TestMiniMaxModelList:
    """Tests for MiniMax models in the built-in model list."""

    def test_m2_7_model_exists(self):
        model = next(
            (m for m in built_in_models if m.name == ModelName.minimax_m2_7), None
        )
        assert model is not None
        assert model.friendly_name == "Minimax M2.7"
        assert model.family == ModelFamily.minimax

    def test_m2_7_has_direct_provider(self):
        model = next(
            (m for m in built_in_models if m.name == ModelName.minimax_m2_7), None
        )
        assert model is not None
        direct = next(
            (p for p in model.providers if p.name == ModelProviderName.minimax), None
        )
        assert direct is not None
        assert direct.model_id == "MiniMax-M2.7"
        assert direct.reasoning_capable is True
        assert direct.supports_data_gen is True

    def test_m2_7_has_openrouter_provider(self):
        model = next(
            (m for m in built_in_models if m.name == ModelName.minimax_m2_7), None
        )
        assert model is not None
        openrouter = next(
            (p for p in model.providers if p.name == ModelProviderName.openrouter),
            None,
        )
        assert openrouter is not None
        assert openrouter.model_id == "minimax/minimax-m2.7"

    def test_m2_5_has_direct_provider(self):
        model = next(
            (m for m in built_in_models if m.name == ModelName.minimax_m2_5), None
        )
        assert model is not None
        direct = next(
            (p for p in model.providers if p.name == ModelProviderName.minimax), None
        )
        assert direct is not None
        assert direct.model_id == "MiniMax-M2.5"

    def test_m2_has_direct_provider(self):
        model = next(
            (m for m in built_in_models if m.name == ModelName.minimax_m2), None
        )
        assert model is not None
        direct = next(
            (p for p in model.providers if p.name == ModelProviderName.minimax), None
        )
        assert direct is not None
        assert direct.model_id == "MiniMax-M2"

    def test_minimax_direct_provider_first_in_list(self):
        """Direct MiniMax provider should be listed first (preferred) for M2.7 and M2.5."""
        for model_name in [ModelName.minimax_m2_7, ModelName.minimax_m2_5]:
            model = next(
                (m for m in built_in_models if m.name == model_name), None
            )
            assert model is not None
            assert len(model.providers) > 0
            assert model.providers[0].name == ModelProviderName.minimax

    def test_all_minimax_direct_providers_have_r1_parser(self):
        """All direct MiniMax providers should use the r1_thinking parser."""
        from kiln_ai.adapters.ml_model_list import ModelParserID

        for model in built_in_models:
            for p in model.providers:
                if p.name == ModelProviderName.minimax:
                    assert p.parser == ModelParserID.r1_thinking, (
                        f"Model {model.name} MiniMax provider missing r1_thinking parser"
                    )
