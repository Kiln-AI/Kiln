from typing import List, Tuple

import pytest
from kiln_ai.adapters.reranker_list import RerankerModelName, built_in_rerankers
from kiln_ai.adapters.rerankers.base_reranker import BaseReranker, RerankDocument
from kiln_ai.adapters.rerankers.reranker_registry import reranker_adapter_from_config
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.reranker import RerankerConfig, RerankerType


async def run_reranker_integration_test(
    adapter: BaseReranker,
) -> None:
    result = await adapter.rerank(
        "san francisco",
        [
            RerankDocument(id="seoul", text="Seoul is in South Korea"),
            RerankDocument(id="sf", text="San Francisco is in California"),
            RerankDocument(id="sd", text="San Diego is in California"),
            RerankDocument(
                id="irrelevant",
                text="Plumbing is a trade that involves the installation and repair of pipes and fixtures.",
            ),
        ],
    )

    assert len(result.results) == 3

    # flaky but obvious enough to work consistently; we expect this ranking:
    # 1. San Francisco
    # 2. San Diego
    # 3. Seoul
    # 4. Irrelevant -> should get filtered out due to top_n=3
    assert result.results[0].index == 1  # index in original list of documents
    assert result.results[0].document.id == "sf"
    assert result.results[0].document.text == "San Francisco is in California"

    assert result.results[1].index == 2  # index in original list of documents
    assert result.results[1].document.id == "sd"
    assert result.results[1].document.text == "San Diego is in California"

    assert result.results[2].index == 0  # index in original list of documents
    assert result.results[2].document.id == "seoul"
    assert result.results[2].document.text == "Seoul is in South Korea"

    for hit in result.results:
        assert isinstance(hit.relevance_score, float)
        assert hit.relevance_score is not None


def get_all_reranker_model_combinations() -> List[
    Tuple[ModelProviderName, RerankerModelName]
]:
    reranker_model_combinations = []
    for reranker in built_in_rerankers:
        for provider in reranker.providers:
            reranker_model_combinations.append((provider.name, reranker.name))
    return reranker_model_combinations


class TestRerankerIntegrationSuccess:
    """Test cases for Reranker integration success."""

    @pytest.mark.paid
    @pytest.mark.parametrize(
        "model_provider_name, model_name", get_all_reranker_model_combinations()
    )
    async def test_reranker_integration_success(self, model_provider_name, model_name):
        """Paid test: Test that the reranker integration is successful."""
        adapter = reranker_adapter_from_config(
            RerankerConfig(
                name="test_config",
                top_n=3,
                model_provider_name=model_provider_name,
                model_name=model_name,
                properties={"type": RerankerType.COHERE_COMPATIBLE},
            )
        )
        await run_reranker_integration_test(adapter)
