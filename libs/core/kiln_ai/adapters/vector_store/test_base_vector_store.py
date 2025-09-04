from typing import List, Tuple
from unittest.mock import MagicMock

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    KilnVectorStoreQuery,
    SearchResult,
)
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.rag import RagConfig
from kiln_ai.datamodel.vector_store import VectorStoreConfig


class TestBaseVectorStoreAdapter:
    """Test the base vector store adapter abstract class."""

    def test_init_stores_config(self):
        """Test that the adapter stores the vector store config."""

        # Create a concrete implementation for testing
        class ConcreteAdapter(BaseVectorStoreAdapter):
            async def add_chunks_with_embeddings(
                self,
                records: List[Tuple[str, ChunkedDocument, ChunkEmbeddings]],
            ) -> None:
                pass

            async def delete_chunks_by_document_id(self, document_id: str) -> None:
                pass

            async def search(self, query: KilnVectorStoreQuery) -> List[SearchResult]:
                return []

            async def count_records(self) -> int:
                return 0

            async def destroy(self) -> None:
                pass

        config = MagicMock(spec=VectorStoreConfig)
        adapter = ConcreteAdapter(MagicMock(spec=RagConfig), config)
        assert adapter.vector_store_config is config


class TestKilnVectorStoreQuery:
    """Test the KilnVectorStoreQuery model."""

    def test_default_values(self):
        """Test that the query model has correct default values."""
        query = KilnVectorStoreQuery()
        assert query.query_string is None
        assert query.query_embedding is None

    def test_with_query_string(self):
        """Test creating a query with a query string."""
        query = KilnVectorStoreQuery(query_string="test query")
        assert query.query_string == "test query"
        assert query.query_embedding is None

    def test_with_query_embedding(self):
        """Test creating a query with an embedding."""
        embedding = [0.1, 0.2, 0.3]
        query = KilnVectorStoreQuery(query_embedding=embedding)
        assert query.query_string is None
        assert query.query_embedding == embedding

    def test_with_both_values(self):
        """Test creating a query with both string and embedding."""
        embedding = [0.1, 0.2, 0.3]
        query = KilnVectorStoreQuery(
            query_string="test query", query_embedding=embedding
        )
        assert query.query_string == "test query"
        assert query.query_embedding == embedding


class TestSearchResult:
    """Test the SearchResult model."""

    def test_required_fields(self):
        """Test creating a search result with required fields."""
        result = SearchResult(
            document_id="doc123",
            chunk_text="This is a test chunk",
            similarity=0.95,
            chunk_idx=0,
        )
        assert result.document_id == "doc123"
        assert result.chunk_text == "This is a test chunk"
        assert result.similarity == 0.95

    def test_optional_similarity(self):
        """Test that similarity can be None."""
        result = SearchResult(
            document_id="doc123",
            chunk_text="This is a test chunk",
            similarity=None,
            chunk_idx=0,
        )
        assert result.document_id == "doc123"
        assert result.chunk_text == "This is a test chunk"
        assert result.similarity is None
