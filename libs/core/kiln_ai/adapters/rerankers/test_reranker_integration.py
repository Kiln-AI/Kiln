import pytest
from kiln_ai.adapters.rerankers.base_reranker import RerankDocument
from kiln_ai.adapters.rerankers.litellm_reranker_adapter import LitellmRerankerAdapter
from kiln_ai.datamodel.reranker import RerankerConfig, RerankerType


class TestRerankerIntegrationSuccess:
    """Test cases for Reranker integration success."""

    @pytest.mark.paid
    async def test_reranker_integration_success(self):
        """Paid test: Test that the reranker integration is successful."""
        config = RerankerConfig(
            name="test_config",
            top_n=3,
            model_provider_name="together_ai",
            model_name="llama_rank",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )
        adapter = LitellmRerankerAdapter(config)
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
