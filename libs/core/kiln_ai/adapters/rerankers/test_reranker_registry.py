from unittest.mock import patch

import pytest
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.adapters.rerankers.litellm_reranker_adapter import LitellmRerankerAdapter
from kiln_ai.adapters.rerankers.reranker_registry import reranker_adapter_from_config
from kiln_ai.datamodel.reranker import RerankerConfig, RerankerType


def make_basic_config() -> RerankerConfig:
    return RerankerConfig(
        name="test_config",
        top_n=5,
        model_provider_name="together_ai",
        model_name="fake",
        properties={"type": RerankerType.COHERE_COMPATIBLE},
    )


@pytest.fixture
def config():
    with patch(
        "kiln_ai.adapters.rerankers.reranker_registry.lite_llm_core_config_for_provider"
    ) as mock_provider:
        mock_provider.return_value = LiteLlmCoreConfig(
            base_url="https://api.fake.com",
            default_headers={"Authorization": "Bearer test-token"},
            additional_body_options={"temperature": "0.5"},
        )
        yield make_basic_config()


def test_returns_litellm_adapter_for_cohere_type(config):
    adapter = reranker_adapter_from_config(config)
    assert isinstance(adapter, LitellmRerankerAdapter)
    assert adapter.reranker_config == config


def test_raises_value_error_for_unknown_type(config):
    # Force an invalid value to exercise the exhaustive error branch
    config.properties["type"] = "unknown_type"  # type: ignore[index,assignment]
    with pytest.raises(ValueError) as exc:
        reranker_adapter_from_config(config)
    assert "Unhandled enum value" in str(exc.value)
