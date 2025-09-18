from unittest.mock import MagicMock

from kiln_ai.adapters.rag.deduplication import (
    deduplicate_chunk_embeddings,
    deduplicate_chunked_documents,
    deduplicate_extractions,
    filter_documents_by_tags,
)
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.extraction import Document, Extraction


class TestFilterDocumentsByTags:
    def test_filter_documents_by_tags_with_none_tags(self):
        """Test that None tags returns all documents"""
        doc1 = MagicMock(spec=Document)
        doc1.tags = ["tag1", "tag2"]
        doc2 = MagicMock(spec=Document)
        doc2.tags = ["tag3"]

        documents = [doc1, doc2]
        result = filter_documents_by_tags(documents, None)

        assert result == documents
        assert len(result) == 2

    def test_filter_documents_by_tags_with_empty_tags(self):
        """Test that empty tags list returns all documents"""
        doc1 = MagicMock(spec=Document)
        doc1.tags = ["tag1", "tag2"]
        doc2 = MagicMock(spec=Document)
        doc2.tags = ["tag3"]

        documents = [doc1, doc2]
        result = filter_documents_by_tags(documents, [])

        assert result == documents
        assert len(result) == 2

    def test_filter_documents_by_tags_single_matching_tag(self):
        """Test filtering with a single matching tag"""
        doc1 = MagicMock(spec=Document)
        doc1.tags = ["tag1", "tag2"]
        doc2 = MagicMock(spec=Document)
        doc2.tags = ["tag3"]
        doc3 = MagicMock(spec=Document)
        doc3.tags = ["tag1", "tag4"]

        documents = [doc1, doc2, doc3]
        result = filter_documents_by_tags(documents, ["tag1"])

        assert len(result) == 2
        assert doc1 in result
        assert doc3 in result
        assert doc2 not in result

    def test_filter_documents_by_tags_multiple_matching_tags(self):
        """Test filtering with multiple tags (OR logic)"""
        doc1 = MagicMock(spec=Document)
        doc1.tags = ["tag1", "tag2"]
        doc2 = MagicMock(spec=Document)
        doc2.tags = ["tag3"]
        doc3 = MagicMock(spec=Document)
        doc3.tags = ["tag4", "tag5"]
        doc4 = MagicMock(spec=Document)
        doc4.tags = ["tag2", "tag6"]

        documents = [doc1, doc2, doc3, doc4]
        result = filter_documents_by_tags(documents, ["tag1", "tag3"])

        assert len(result) == 2
        assert doc1 in result  # has tag1
        assert doc2 in result  # has tag3
        assert doc3 not in result
        assert doc4 not in result

    def test_filter_documents_by_tags_no_matching_documents(self):
        """Test filtering when no documents match the tags"""
        doc1 = MagicMock(spec=Document)
        doc1.tags = ["tag1", "tag2"]
        doc2 = MagicMock(spec=Document)
        doc2.tags = ["tag3"]

        documents = [doc1, doc2]
        result = filter_documents_by_tags(documents, ["tag4", "tag5"])

        assert len(result) == 0

    def test_filter_documents_by_tags_documents_with_no_tags(self):
        """Test filtering when some documents have no tags"""
        doc1 = MagicMock(spec=Document)
        doc1.tags = ["tag1", "tag2"]
        doc2 = MagicMock(spec=Document)
        doc2.tags = None
        doc3 = MagicMock(spec=Document)
        doc3.tags = []
        doc4 = MagicMock(spec=Document)
        doc4.tags = ["tag1"]

        documents = [doc1, doc2, doc3, doc4]
        result = filter_documents_by_tags(documents, ["tag1"])

        assert len(result) == 2
        assert doc1 in result
        assert doc4 in result
        assert doc2 not in result  # None tags
        assert doc3 not in result  # empty tags

    def test_filter_documents_by_tags_empty_document_list(self):
        """Test filtering with empty document list"""
        documents = []
        result = filter_documents_by_tags(documents, ["tag1"])

        assert len(result) == 0

    def test_filter_documents_by_tags_case_sensitive(self):
        """Test that tag filtering is case sensitive"""
        doc1 = MagicMock(spec=Document)
        doc1.tags = ["Tag1", "tag2"]
        doc2 = MagicMock(spec=Document)
        doc2.tags = ["tag1", "tag3"]

        documents = [doc1, doc2]
        result = filter_documents_by_tags(documents, ["tag1"])

        assert len(result) == 1
        assert doc2 in result
        assert doc1 not in result  # "Tag1" != "tag1"

    def test_filter_documents_by_tags_partial_match(self):
        """Test that only exact tag matches work, not partial matches"""
        doc1 = MagicMock(spec=Document)
        doc1.tags = ["tag1", "tag12"]
        doc2 = MagicMock(spec=Document)
        doc2.tags = ["tag", "other"]

        documents = [doc1, doc2]
        result = filter_documents_by_tags(documents, ["tag"])

        assert len(result) == 1
        assert doc2 in result
        assert doc1 not in result  # "tag1" and "tag12" don't match "tag"


class TestDeduplicationFunctions:
    """Basic tests to ensure existing deduplication functions still work"""

    def test_deduplicate_extractions_basic(self):
        """Test basic deduplication of extractions"""
        extraction1 = MagicMock(spec=Extraction)
        extraction1.extractor_config_id = "config1"
        extraction1.created_at = "2024-01-01"

        extraction2 = MagicMock(spec=Extraction)
        extraction2.extractor_config_id = "config1"
        extraction2.created_at = "2024-01-02"

        extractions = [extraction1, extraction2]
        result = deduplicate_extractions(extractions)

        assert len(result) == 1
        assert result[0] == extraction1  # earlier created_at

    def test_deduplicate_chunked_documents_basic(self):
        """Test basic deduplication of chunked documents"""
        chunked1 = MagicMock(spec=ChunkedDocument)
        chunked1.chunker_config_id = "config1"
        chunked1.created_at = "2024-01-01"

        chunked2 = MagicMock(spec=ChunkedDocument)
        chunked2.chunker_config_id = "config1"
        chunked2.created_at = "2024-01-02"

        chunked_docs = [chunked1, chunked2]
        result = deduplicate_chunked_documents(chunked_docs)

        assert len(result) == 1
        assert result[0] == chunked1  # earlier created_at

    def test_deduplicate_chunk_embeddings_basic(self):
        """Test basic deduplication of chunk embeddings"""
        embedding1 = MagicMock(spec=ChunkEmbeddings)
        embedding1.embedding_config_id = "config1"
        embedding1.created_at = "2024-01-01"

        embedding2 = MagicMock(spec=ChunkEmbeddings)
        embedding2.embedding_config_id = "config1"
        embedding2.created_at = "2024-01-02"

        embeddings = [embedding1, embedding2]
        result = deduplicate_chunk_embeddings(embeddings)

        assert len(result) == 1
        assert result[0] == embedding1  # earlier created_at
