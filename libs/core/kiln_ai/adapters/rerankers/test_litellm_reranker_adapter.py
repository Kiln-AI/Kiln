from unittest.mock import AsyncMock, Mock, patch

import litellm
import pytest
from kiln_ai.adapters.provider_tools import LiteLlmCoreConfig
from kiln_ai.adapters.reranker_list import KilnRerankerModelProvider
from kiln_ai.adapters.rerankers.base_reranker import RerankDocument, RerankResponse
from kiln_ai.adapters.rerankers.litellm_reranker_adapter import LitellmRerankerAdapter
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.reranker import RerankerConfig, RerankerType


class TestLitellmRerankerAdapterInitialization:
    """Test cases for LitellmRerankerAdapter initialization."""

    def litellm_provider_config(self):
        """Create a test LiteLLM provider config."""
        return LiteLlmCoreConfig(
            base_url="https://api.litellm.com",
            default_headers={"Authorization": "Bearer test-token"},
            additional_body_options={"temperature": "0.5"},
        )

    def test_init_with_valid_config(self):
        """Test initialization with valid reranker config."""
        config = RerankerConfig(
            name="test_config",
            top_n=5,
            model_provider_name="together_ai",
            model_name="llama_rank",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )

        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.built_in_reranker_models_from_provider"
        ) as mock_provider:
            mock_provider.return_value = KilnRerankerModelProvider(
                name=ModelProviderName.together_ai, model_id="Salesforce/Llama-Rank-V1"
            )

            adapter = LitellmRerankerAdapter(
                config, litellm_provider_config=self.litellm_provider_config()
            )
            assert adapter.reranker_config == config

    def test_init_with_invalid_model(self):
        """Test initialization with invalid model name."""
        config = RerankerConfig(
            name="test_config",
            top_n=5,
            model_provider_name="together_ai",
            model_name="invalid_model",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )

        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.built_in_reranker_models_from_provider"
        ) as mock_provider:
            mock_provider.return_value = None

            adapter = LitellmRerankerAdapter(
                config, litellm_provider_config=self.litellm_provider_config()
            )
            # The error should be raised when accessing the model_provider property
            with pytest.raises(
                ValueError, match="Reranker model invalid_model not found"
            ):
                _ = adapter.model_provider


class TestLitellmRerankerAdapterProperties:
    """Test cases for LitellmRerankerAdapter properties."""

    def litellm_provider_config(self):
        """Create a test LiteLLM provider config."""
        return LiteLlmCoreConfig(
            base_url="https://api.litellm.com",
            default_headers={"Authorization": "Bearer test-token"},
            additional_body_options={"temperature": "0.5"},
        )

    @pytest.fixture
    def adapter(self):
        """Create a test adapter with mocked dependencies."""
        config = RerankerConfig(
            name="test_config",
            top_n=5,
            model_provider_name="together_ai",
            model_name="llama_rank",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )

        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.built_in_reranker_models_from_provider"
        ) as mock_provider:
            mock_provider.return_value = KilnRerankerModelProvider(
                name=ModelProviderName.together_ai, model_id="Salesforce/Llama-Rank-V1"
            )

            return LitellmRerankerAdapter(
                config, litellm_provider_config=self.litellm_provider_config()
            )

    def test_model_provider_property(self, adapter):
        """Test model_provider property returns correct provider."""
        provider = adapter.model_provider
        assert isinstance(provider, KilnRerankerModelProvider)
        assert provider.name == ModelProviderName.together_ai
        assert provider.model_id == "Salesforce/Llama-Rank-V1"

    def test_model_provider_cached(self, adapter):
        """Test that model_provider property is cached."""
        provider1 = adapter.model_provider
        provider2 = adapter.model_provider
        assert provider1 is provider2

    def test_litellm_model_slug_property(self, adapter):
        """Test litellm_model_slug property."""
        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.get_litellm_provider_info"
        ) as mock_get_info:
            mock_provider_info = Mock()
            mock_provider_info.litellm_model_id = "together_ai/Salesforce/Llama-Rank-V1"
            mock_get_info.return_value = mock_provider_info

            slug = adapter.litellm_model_slug
            assert slug == "together_ai/Salesforce/Llama-Rank-V1"
            mock_get_info.assert_called_once_with(adapter.model_provider)

    def test_litellm_model_slug_cached(self, adapter):
        """Test that litellm_model_slug property is cached."""
        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.get_litellm_provider_info"
        ) as mock_get_info:
            mock_provider_info = Mock()
            mock_provider_info.litellm_model_id = "together_ai/Salesforce/Llama-Rank-V1"
            mock_get_info.return_value = mock_provider_info

            slug1 = adapter.litellm_model_slug
            slug2 = adapter.litellm_model_slug
            assert slug1 is slug2
            mock_get_info.assert_called_once()


class TestLitellmRerankerAdapterRerank:
    """Test cases for LitellmRerankerAdapter rerank method."""

    def litellm_provider_config(self):
        """Create a test LiteLLM provider config."""
        return LiteLlmCoreConfig(
            base_url="https://api.litellm.com",
            default_headers={"Authorization": "Bearer test-token"},
            additional_body_options={"temperature": "0.5"},
        )

    @pytest.fixture
    def adapter(self):
        """Create a test adapter with mocked dependencies."""
        config = RerankerConfig(
            name="test_config",
            top_n=3,
            model_provider_name="together_ai",
            model_name="llama_rank",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )

        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.built_in_reranker_models_from_provider"
        ) as mock_provider:
            mock_provider.return_value = KilnRerankerModelProvider(
                name=ModelProviderName.together_ai, model_id="Salesforce/Llama-Rank-V1"
            )

            return LitellmRerankerAdapter(
                config, litellm_provider_config=self.litellm_provider_config()
            )

    @pytest.fixture
    def sample_documents(self):
        """Create sample documents for testing."""
        return [
            RerankDocument(id="doc1", text="First document about cats"),
            RerankDocument(id="doc2", text="Second document about dogs"),
            RerankDocument(id="doc3", text="Third document about birds"),
        ]

    async def test_rerank_with_empty_documents(self, adapter):
        """Test rerank with empty document list."""
        result = await adapter.rerank("test query", [])
        assert result == RerankResponse(results=[])

    async def test_rerank_success(self, adapter, sample_documents):
        """Test successful reranking."""
        # Create a proper mock that behaves like litellm.RerankResponse
        mock_litellm_response = Mock(spec=litellm.RerankResponse)
        mock_litellm_response.results = [
            {"index": 1, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.87},
            {"index": 2, "relevance_score": 0.72},
        ]

        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.litellm.arerank",
            new_callable=AsyncMock,
        ) as mock_arerank:
            mock_arerank.return_value = mock_litellm_response

            result = await adapter.rerank("test query", sample_documents)

            assert len(result.results) == 3
            assert result.results[0].index == 1
            assert result.results[0].relevance_score == 0.95
            assert result.results[0].document == sample_documents[1]

            mock_arerank.assert_called_once_with(
                model="together_ai/Salesforce/Llama-Rank-V1",
                query="test query",
                documents=[
                    "First document about cats",
                    "Second document about dogs",
                    "Third document about birds",
                ],
                top_n=3,
                base_url="https://api.litellm.com",
                default_headers={"Authorization": "Bearer test-token"},
                temperature="0.5",
            )

    async def test_rerank_with_invalid_response_type(self, adapter, sample_documents):
        """Test rerank with invalid response type from litellm."""
        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.litellm.arerank",
            new_callable=AsyncMock,
        ) as mock_arerank:
            mock_arerank.return_value = "invalid_response"

            with pytest.raises(
                ValueError, match="Expected RerankResponse, got <class 'str'>"
            ):
                await adapter.rerank("test query", sample_documents)

    async def test_rerank_with_no_results(self, adapter, sample_documents):
        """Test rerank with no results from litellm."""
        # Create a proper mock that behaves like litellm.RerankResponse
        mock_litellm_response = Mock(spec=litellm.RerankResponse)
        mock_litellm_response.results = []

        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.litellm.arerank",
            new_callable=AsyncMock,
        ) as mock_arerank:
            mock_arerank.return_value = mock_litellm_response

            with pytest.raises(ValueError, match="No results returned from LiteLLM"):
                await adapter.rerank("test query", sample_documents)


class TestLitellmRerankerAdapterConvertToRerankResponse:
    """Test cases for convert_to_rerank_response method."""

    def litellm_provider_config(self):
        """Create a test LiteLLM provider config."""
        return LiteLlmCoreConfig(
            base_url="https://api.litellm.com",
            default_headers={"Authorization": "Bearer test-token"},
            additional_body_options={"temperature": "0.5"},
        )

    @pytest.fixture
    def adapter(self):
        """Create a test adapter with mocked dependencies."""
        config = RerankerConfig(
            name="test_config",
            top_n=3,
            model_provider_name="together_ai",
            model_name="llama_rank",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )

        with patch(
            "kiln_ai.adapters.rerankers.litellm_reranker_adapter.built_in_reranker_models_from_provider"
        ) as mock_provider:
            mock_provider.return_value = KilnRerankerModelProvider(
                name=ModelProviderName.together_ai, model_id="Salesforce/Llama-Rank-V1"
            )

            return LitellmRerankerAdapter(
                config, litellm_provider_config=self.litellm_provider_config()
            )

    @pytest.fixture
    def sample_documents(self):
        """Create sample documents for testing."""
        return [
            RerankDocument(id="doc1", text="First document"),
            RerankDocument(id="doc2", text="Second document"),
            RerankDocument(id="doc3", text="Third document"),
        ]

    def test_convert_to_rerank_response_success(self, adapter, sample_documents):
        """Test successful conversion of litellm response."""
        # Create a proper mock that behaves like litellm.RerankResponse
        mock_litellm_response = Mock(spec=litellm.RerankResponse)
        mock_litellm_response.results = [
            {"index": 1, "relevance_score": 0.95},
            {"index": 0, "relevance_score": 0.87},
        ]

        result = adapter.convert_to_rerank_response(
            sample_documents, mock_litellm_response
        )

        assert len(result.results) == 2
        assert result.results[0].index == 1
        assert result.results[0].relevance_score == 0.95
        assert result.results[0].document == sample_documents[1]
        assert result.results[1].index == 0
        assert result.results[1].relevance_score == 0.87
        assert result.results[1].document == sample_documents[0]

    def test_convert_to_rerank_response_empty_results(self, adapter, sample_documents):
        """Test conversion with empty results."""
        # Create a proper mock that behaves like litellm.RerankResponse
        mock_litellm_response = Mock(spec=litellm.RerankResponse)
        mock_litellm_response.results = []

        with pytest.raises(ValueError, match="No results returned from LiteLLM"):
            adapter.convert_to_rerank_response(sample_documents, mock_litellm_response)

    def test_convert_to_rerank_response_invalid_index(self, adapter, sample_documents):
        """Test conversion with invalid index in results."""
        # Create a proper mock that behaves like litellm.RerankResponse
        mock_litellm_response = Mock(spec=litellm.RerankResponse)
        mock_litellm_response.results = [
            {"index": 5, "relevance_score": 0.95},  # Index out of bounds
        ]

        with pytest.raises(ValueError, match="Reranker returned invalid index 5"):
            adapter.convert_to_rerank_response(sample_documents, mock_litellm_response)


class TestLitellmRerankerAdapterIntegration:
    """Integration test cases for LitellmRerankerAdapter."""

    def litellm_provider_config(self):
        """Create a test LiteLLM provider config."""
        return LiteLlmCoreConfig(
            base_url="https://api.litellm.com",
            default_headers={"Authorization": "Bearer test-token"},
            additional_body_options={"temperature": "0.5"},
        )

    async def test_full_rerank_workflow(self):
        """Test the complete rerank workflow with mocked external dependencies."""
        config = RerankerConfig(
            name="test_config",
            top_n=2,
            model_provider_name="together_ai",
            model_name="llama_rank",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )

        documents = [
            RerankDocument(id="doc1", text="Document about machine learning"),
            RerankDocument(id="doc2", text="Document about artificial intelligence"),
            RerankDocument(id="doc3", text="Document about cooking recipes"),
        ]

        # Mock all external dependencies
        with (
            patch(
                "kiln_ai.adapters.rerankers.litellm_reranker_adapter.built_in_reranker_models_from_provider"
            ) as mock_provider,
            patch(
                "kiln_ai.adapters.rerankers.litellm_reranker_adapter.get_litellm_provider_info"
            ) as mock_get_info,
            patch(
                "kiln_ai.adapters.rerankers.litellm_reranker_adapter.litellm.arerank",
                new_callable=AsyncMock,
            ) as mock_arerank,
        ):
            # Setup mocks
            mock_provider.return_value = KilnRerankerModelProvider(
                name=ModelProviderName.together_ai, model_id="Salesforce/Llama-Rank-V1"
            )

            mock_provider_info = Mock()
            mock_provider_info.litellm_model_id = "together_ai/Salesforce/Llama-Rank-V1"
            mock_get_info.return_value = mock_provider_info

            mock_litellm_response = Mock(spec=litellm.RerankResponse)
            mock_litellm_response.results = [
                {"index": 1, "relevance_score": 0.95},  # AI document
                {"index": 0, "relevance_score": 0.87},  # ML document
            ]
            mock_arerank.return_value = mock_litellm_response

            # Test the workflow
            adapter = LitellmRerankerAdapter(
                config, litellm_provider_config=self.litellm_provider_config()
            )
            result = await adapter.rerank("artificial intelligence", documents)

            # Verify results
            assert len(result.results) == 2
            assert (
                result.results[0].document.id == "doc2"
            )  # AI document should be first
            assert result.results[0].relevance_score == 0.95
            assert (
                result.results[1].document.id == "doc1"
            )  # ML document should be second
            assert result.results[1].relevance_score == 0.87

            # Verify litellm was called correctly
            mock_arerank.assert_called_once_with(
                model="together_ai/Salesforce/Llama-Rank-V1",
                query="artificial intelligence",
                documents=[
                    "Document about machine learning",
                    "Document about artificial intelligence",
                    "Document about cooking recipes",
                ],
                top_n=2,
                base_url="https://api.litellm.com",
                default_headers={"Authorization": "Bearer test-token"},
                temperature="0.5",
            )
