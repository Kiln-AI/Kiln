import pytest
from kiln_ai.adapters.rerankers.base_reranker import (
    BaseReranker,
    RerankDocument,
    RerankResponse,
    RerankResult,
)
from kiln_ai.datamodel.reranker import RerankerConfig, RerankerType
from pydantic import ValidationError


class TestRerankDocument:
    """Test cases for RerankDocument model."""

    def test_rerank_document_creation(self):
        """Test creating a RerankDocument with valid data."""
        doc = RerankDocument(id="doc1", text="Sample document text")
        assert doc.id == "doc1"
        assert doc.text == "Sample document text"

    def test_rerank_document_validation(self):
        """Test RerankDocument field validation."""
        # Test with missing required fields
        with pytest.raises(ValidationError):
            RerankDocument()

        # Test with empty string id - this should work as Pydantic doesn't validate empty strings
        doc = RerankDocument(id="", text="text")
        assert doc.id == ""
        assert doc.text == "text"

        # Test with empty string text - this should work as Pydantic doesn't validate empty strings
        doc = RerankDocument(id="doc1", text="")
        assert doc.id == "doc1"
        assert doc.text == ""


class TestRerankResult:
    """Test cases for RerankResult model."""

    def test_rerank_result_creation(self):
        """Test creating a RerankResult with valid data."""
        doc = RerankDocument(id="doc1", text="Sample document text")
        result = RerankResult(index=0, document=doc, relevance_score=0.95)
        assert result.index == 0
        assert result.document == doc
        assert result.relevance_score == 0.95

    def test_rerank_result_validation(self):
        """Test RerankResult field validation."""
        doc = RerankDocument(id="doc1", text="Sample document text")

        # Test with negative index
        with pytest.raises(ValidationError):
            RerankResult(index=-1, document=doc, relevance_score=0.95)

        # Test with invalid relevance score - this should work as there's no validation constraint
        result = RerankResult(index=0, document=doc, relevance_score=-0.1)
        assert result.relevance_score == -0.1

        result = RerankResult(index=0, document=doc, relevance_score=1.1)
        assert result.relevance_score == 1.1


class TestRerankResponse:
    """Test cases for RerankResponse model."""

    def test_rerank_response_creation(self):
        """Test creating a RerankResponse with valid data."""
        doc = RerankDocument(id="doc1", text="Sample document text")
        result = RerankResult(index=0, document=doc, relevance_score=0.95)
        response = RerankResponse(results=[result])
        assert len(response.results) == 1
        assert response.results[0] == result

    def test_rerank_response_empty_results(self):
        """Test creating a RerankResponse with empty results."""
        response = RerankResponse(results=[])
        assert len(response.results) == 0


class TestBaseReranker:
    """Test cases for BaseReranker abstract base class."""

    def test_base_reranker_is_abstract(self):
        """Test that BaseReranker cannot be instantiated directly."""
        config = RerankerConfig(
            name="test_config",
            top_n=5,
            model_provider_name="test_provider",
            model_name="test_model",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )

        with pytest.raises(TypeError):
            BaseReranker(config)

    def test_base_reranker_has_abstract_method(self):
        """Test that BaseReranker has the required abstract method."""
        assert hasattr(BaseReranker, "rerank")
        assert getattr(BaseReranker.rerank, "__isabstractmethod__", False)

    def test_concrete_reranker_implementation(self):
        """Test that a concrete implementation works correctly."""
        config = RerankerConfig(
            name="test_config",
            top_n=5,
            model_provider_name="test_provider",
            model_name="test_model",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )

        class ConcreteReranker(BaseReranker):
            async def rerank(
                self, query: str, documents: list[RerankDocument]
            ) -> RerankResponse:
                return RerankResponse(results=[])

        reranker = ConcreteReranker(config)
        assert reranker.reranker_config == config
        assert isinstance(reranker, BaseReranker)

    def test_concrete_reranker_missing_implementation(self):
        """Test that incomplete concrete implementation raises error."""
        config = RerankerConfig(
            name="test_config",
            top_n=5,
            model_provider_name="test_provider",
            model_name="test_model",
            properties={"type": RerankerType.COHERE_COMPATIBLE},
        )

        class IncompleteReranker(BaseReranker):
            pass

        with pytest.raises(TypeError):
            IncompleteReranker(config)
