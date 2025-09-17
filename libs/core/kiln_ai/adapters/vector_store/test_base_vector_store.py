from typing import List, Set, Tuple
from unittest.mock import MagicMock

import pytest

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    DocumentWithChunksAndEmbeddings,
    SearchResult,
    VectorStoreQuery,
)
from kiln_ai.datamodel.chunk import Chunk, ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings, Embedding
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

            async def search(self, query: VectorStoreQuery) -> List[SearchResult]:
                return []

            async def count_records(self) -> int:
                return 0

            async def destroy(self) -> None:
                pass

            async def delete_nodes_not_in_set(self, document_ids: Set[str]) -> None:
                pass

        config = MagicMock(spec=VectorStoreConfig)
        adapter = ConcreteAdapter(MagicMock(spec=RagConfig), config)
        assert adapter.vector_store_config is config


class TestVectorStoreQuery:
    """Test the VectorStoreQuery model."""

    def test_default_values(self):
        """Test that the query model has correct default values."""
        query = VectorStoreQuery()
        assert query.query_string is None
        assert query.query_embedding is None

    def test_with_query_string(self):
        """Test creating a query with a query string."""
        query = VectorStoreQuery(query_string="test query")
        assert query.query_string == "test query"
        assert query.query_embedding is None

    def test_with_query_embedding(self):
        """Test creating a query with an embedding."""
        embedding = [0.1, 0.2, 0.3]
        query = VectorStoreQuery(query_embedding=embedding)
        assert query.query_string is None
        assert query.query_embedding == embedding

    def test_with_both_values(self):
        """Test creating a query with both string and embedding."""
        embedding = [0.1, 0.2, 0.3]
        query = VectorStoreQuery(query_string="test query", query_embedding=embedding)
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


def test_document_with_chunks_and_embeddings_properties():
    """Test that DocumentWithChunksAndEmbeddings virtual properties work correctly."""
    # Create mock chunked document with chunks
    mock_chunk1 = MagicMock(spec=Chunk)
    mock_chunk2 = MagicMock(spec=Chunk)
    mock_chunked_document = MagicMock(spec=ChunkedDocument)
    mock_chunked_document.chunks = [mock_chunk1, mock_chunk2]

    # Create mock chunk embeddings with embeddings
    mock_embedding1 = MagicMock(spec=Embedding)
    mock_embedding2 = MagicMock(spec=Embedding)
    mock_chunk_embeddings = MagicMock(spec=ChunkEmbeddings)
    mock_chunk_embeddings.embeddings = [mock_embedding1, mock_embedding2]

    # Create DocumentWithChunksAndEmbeddings instance
    doc_with_chunks = DocumentWithChunksAndEmbeddings(
        document_id="test-doc-123",
        chunked_document=mock_chunked_document,
        chunk_embeddings=mock_chunk_embeddings,
    )

    # Test that properties return the correct values
    assert doc_with_chunks.document_id == "test-doc-123"
    assert doc_with_chunks.chunks == [mock_chunk1, mock_chunk2]
    assert doc_with_chunks.embeddings == [mock_embedding1, mock_embedding2]

    # Test that properties are read-only (no setters)
    with pytest.raises(AttributeError):
        doc_with_chunks.chunks = []

    with pytest.raises(AttributeError):
        doc_with_chunks.embeddings = []


def test_document_with_chunks_and_embeddings_empty_lists():
    """Test DocumentWithChunksAndEmbeddings with empty chunks and embeddings."""
    # Create mock objects with empty lists
    mock_chunked_document = MagicMock(spec=ChunkedDocument)
    mock_chunked_document.chunks = []

    mock_chunk_embeddings = MagicMock(spec=ChunkEmbeddings)
    mock_chunk_embeddings.embeddings = []

    # Create DocumentWithChunksAndEmbeddings instance
    doc_with_chunks = DocumentWithChunksAndEmbeddings(
        document_id="empty-doc",
        chunked_document=mock_chunked_document,
        chunk_embeddings=mock_chunk_embeddings,
    )

    # Test that properties return empty lists
    assert doc_with_chunks.document_id == "empty-doc"
    assert doc_with_chunks.chunks == []
    assert doc_with_chunks.embeddings == []
