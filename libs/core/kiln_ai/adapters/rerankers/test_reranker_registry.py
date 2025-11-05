import pytest
from kiln_ai.adapters.rerankers.litellm_reranker_adapter import LitellmRerankerAdapter
from kiln_ai.adapters.rerankers.reranker_registry import reranker_adapter_from_config
from kiln_ai.datamodel.reranker import RerankerConfig, RerankerType


def make_basic_config() -> RerankerConfig:
    return RerankerConfig(
        name="test_config",
        top_n=5,
        model_provider_name="openai",
        model_name="rerank-small",
        properties={"type": RerankerType.COHERE_COMPATIBLE},
    )


def test_returns_litellm_adapter_for_cohere_type():
    config = make_basic_config()

    adapter = reranker_adapter_from_config(config)

    assert isinstance(adapter, LitellmRerankerAdapter)
    assert adapter.reranker_config == config


def test_raises_value_error_for_unknown_type():
    config = make_basic_config()
    # Force an invalid value to exercise the exhaustive error branch
    config.properties["type"] = "unknown_type"  # type: ignore[index,assignment]

    with pytest.raises(ValueError) as exc:
        reranker_adapter_from_config(config)

    assert "Unhandled enum value" in str(exc.value)
