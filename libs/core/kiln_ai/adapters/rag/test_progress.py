from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kiln_ai.adapters.rag.progress import (
    LogMessage,
    RagProgress,
    compute_current_progress_for_rag_config,
    compute_current_progress_for_rag_configs,
    count_records_in_vector_store,
    count_records_in_vector_store_for_rag_config,
)
from kiln_ai.datamodel.chunk import ChunkedDocument
from kiln_ai.datamodel.embedding import ChunkEmbeddings
from kiln_ai.datamodel.extraction import Document, Extraction
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    return project


@pytest.fixture
def mock_project_magic():
    """This mock is more flexible than the mock_project fixture. Can mock the base model methods easily"""
    return MagicMock(spec=Project)


@pytest.fixture
def mock_vector_store_count():
    """Mock the vector store count operations to return 0 by default"""
    with patch(
        "kiln_ai.adapters.rag.progress.count_records_in_vector_store_for_rag_config",
        new_callable=AsyncMock,
        return_value=0,
    ) as mock:
        yield mock


def create_mock_embedding(embedding_config_id):
    """Helper to create a mock embedding with the specified config ID"""
    mock_embedding = MagicMock(spec=ChunkEmbeddings)
    mock_embedding.embedding_config_id = embedding_config_id
    mock_embedding.created_at = "2024-01-01T00:00:00Z"
    return mock_embedding


def create_mock_chunked_document(chunker_config_id, embeddings=None, num_chunks=1):
    """Helper to create a mock chunked document with the specified config ID and embeddings"""
    if embeddings is None:
        embeddings = []

    mock_chunked_doc = MagicMock(spec=ChunkedDocument)
    mock_chunked_doc.chunker_config_id = chunker_config_id
    mock_chunked_doc.chunk_embeddings.return_value = embeddings
    mock_chunked_doc.created_at = "2024-01-01T00:00:00Z"
    # Mock the chunks attribute to return a list with the specified number of chunks
    mock_chunked_doc.chunks = [MagicMock() for _ in range(num_chunks)]
    return mock_chunked_doc


def create_mock_extraction(extractor_config_id, chunked_documents=None):
    """Helper to create a mock extraction with the specified config ID and chunked documents"""
    if chunked_documents is None:
        chunked_documents = []

    mock_extraction = MagicMock(spec=Extraction)
    mock_extraction.extractor_config_id = extractor_config_id
    mock_extraction.chunked_documents.return_value = chunked_documents
    mock_extraction.created_at = "2024-01-01T00:00:00Z"
    return mock_extraction


def create_mock_document(extractions=None, tags=None):
    """Helper to create a mock document with the specified extractions"""
    if extractions is None:
        extractions = []

    mock_document = MagicMock(spec=Document)
    mock_document.extractions.return_value = extractions
    mock_document.tags = tags
    return mock_document


def create_mock_rag_config(
    config_id,
    extractor_config_id,
    chunker_config_id,
    embedding_config_id,
    vector_store_config_id="vector_store_1",
    tags=None,
):
    """Helper to create a mock RAG config with the specified IDs"""
    mock_rag_config = MagicMock(spec=RagConfig)
    mock_rag_config.id = config_id
    mock_rag_config.extractor_config_id = extractor_config_id
    mock_rag_config.chunker_config_id = chunker_config_id
    mock_rag_config.embedding_config_id = embedding_config_id
    mock_rag_config.vector_store_config_id = vector_store_config_id
    mock_rag_config.tags = tags
    return mock_rag_config


class TestLogMessage:
    def test_log_message_creation(self):
        log = LogMessage(level="info", message="Test message")
        assert log.level == "info"
        assert log.message == "Test message"

    def test_log_message_validation(self):
        # Test valid levels
        for level in ["info", "error", "warning"]:
            log = LogMessage(level=level, message="Test")  # type: ignore
            assert log.level == level


class TestRagProgress:
    def test_rag_progress_default_values(self):
        progress = RagProgress()
        assert progress.total_document_count == 0
        assert progress.total_document_completed_count == 0
        assert progress.total_chunk_count == 0
        assert progress.total_chunk_completed_count == 0
        assert progress.total_document_extracted_count == 0
        assert progress.total_document_extracted_error_count == 0
        assert progress.total_document_chunked_count == 0
        assert progress.total_document_chunked_error_count == 0
        assert progress.total_document_embedded_count == 0
        assert progress.total_document_embedded_error_count == 0
        assert progress.total_chunks_indexed_count == 0
        assert progress.total_chunks_indexed_error_count == 0
        assert progress.logs is None

    def test_rag_progress_with_values(self):
        logs = [LogMessage(level="info", message="Processing")]
        progress = RagProgress(
            total_document_count=10,
            total_document_completed_count=5,
            total_document_extracted_count=8,
            total_document_chunked_count=6,
            total_document_embedded_count=5,
            total_chunk_count=6,
            total_chunk_completed_count=3,
            total_chunks_indexed_count=3,
            logs=logs,
        )
        assert progress.total_document_count == 10
        assert progress.total_document_completed_count == 5
        assert progress.total_document_extracted_count == 8
        assert progress.total_document_chunked_count == 6
        assert progress.total_document_embedded_count == 5
        assert progress.total_chunk_count == 6
        assert progress.total_chunk_completed_count == 3
        assert progress.total_chunks_indexed_count == 3
        assert progress.logs is not None
        assert len(progress.logs) == 1
        assert progress.logs[0].level == "info"


class TestComputeCurrentProgressForRagConfigs:
    @pytest.mark.asyncio
    async def test_empty_project_empty_configs(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test with no documents and no RAG configs"""
        mock_project_magic.documents.return_value = []

        result = await compute_current_progress_for_rag_configs(mock_project_magic, [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_project_with_config(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test with no documents but with a RAG config"""
        rag_config = create_mock_rag_config("rag1", "ext1", "chunk1", "embed1")
        mock_project_magic.documents.return_value = []

        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config]
        )

        assert "rag1" in result
        progress = result["rag1"]
        assert progress.total_document_count == 0
        assert progress.total_document_completed_count == 0
        assert progress.total_document_extracted_count == 0
        assert progress.total_document_chunked_count == 0
        assert progress.total_document_embedded_count == 0
        assert progress.total_chunks_indexed_count == 0
        assert progress.total_chunk_count == 0
        assert progress.total_chunk_completed_count == 0

    @pytest.mark.asyncio
    async def test_documents_no_extractions(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test with documents but no extractions"""
        documents = [create_mock_document() for _ in range(3)]
        rag_config = create_mock_rag_config("rag1", "ext1", "chunk1", "embed1")
        mock_project_magic.documents.return_value = documents

        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config]
        )

        assert "rag1" in result
        progress = result["rag1"]
        assert progress.total_document_count == 3
        assert progress.total_document_completed_count == 0
        assert progress.total_document_extracted_count == 0
        assert progress.total_document_chunked_count == 0
        assert progress.total_document_embedded_count == 0
        assert progress.total_chunks_indexed_count == 0

    @pytest.mark.asyncio
    async def test_full_pipeline_single_config(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test complete pipeline with one RAG config"""
        # Create documents with separate extraction trees
        documents = []
        for i in range(2):
            # Each document gets its own unique extraction tree
            embedding = create_mock_embedding("embed1")
            chunked_doc = create_mock_chunked_document(
                "chunk1", [embedding], num_chunks=3
            )  # 3 chunks per document
            extraction = create_mock_extraction("ext1", [chunked_doc])
            document = create_mock_document([extraction])
            documents.append(document)

        rag_config = create_mock_rag_config("rag1", "ext1", "chunk1", "embed1")

        mock_project_magic.documents.return_value = documents
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config]
        )

        assert "rag1" in result
        progress = result["rag1"]
        assert progress.total_document_count == 2
        assert (
            progress.total_document_completed_count == 2
        )  # min of extraction, chunking, embedding (all complete)
        assert progress.total_document_extracted_count == 2
        assert progress.total_document_chunked_count == 2
        assert progress.total_document_embedded_count == 2
        assert progress.total_chunks_indexed_count == 0
        assert progress.total_chunk_count == 6  # 2 documents * 3 chunks each
        assert progress.total_chunk_completed_count == 0  # same as indexed count

    @pytest.mark.asyncio
    async def test_partial_pipeline_progress(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test pipeline where some steps are incomplete"""
        # Document 1: fully processed
        embedding1 = create_mock_embedding("embed1")
        chunked_doc1 = create_mock_chunked_document(
            "chunk1", [embedding1], num_chunks=2
        )
        extraction1 = create_mock_extraction("ext1", [chunked_doc1])
        doc1 = create_mock_document([extraction1])

        # Document 2: extracted and chunked but not embedded
        chunked_doc2 = create_mock_chunked_document(
            "chunk1", [], num_chunks=3
        )  # no embeddings
        extraction2 = create_mock_extraction("ext1", [chunked_doc2])
        doc2 = create_mock_document([extraction2])

        # Document 3: extracted but not chunked
        extraction3 = create_mock_extraction("ext1", [])  # no chunked docs
        doc3 = create_mock_document([extraction3])

        # Document 4: not extracted
        doc4 = create_mock_document([])  # no extractions

        rag_config = create_mock_rag_config("rag1", "ext1", "chunk1", "embed1")

        mock_project_magic.documents.return_value = [doc1, doc2, doc3, doc4]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config]
        )

        assert "rag1" in result
        progress = result["rag1"]
        assert progress.total_document_count == 4
        assert progress.total_document_extracted_count == 3  # docs 1, 2, 3
        assert progress.total_document_chunked_count == 2  # docs 1, 2
        assert progress.total_document_embedded_count == 1  # doc 1 only
        assert progress.total_chunks_indexed_count == 0  # no indexing implemented yet
        assert progress.total_chunk_count == 5  # doc1 has 2 chunks + doc2 has 3 chunks
        assert progress.total_chunk_completed_count == 0  # same as indexed count
        assert progress.total_document_completed_count == 1  # min(3,2,1) = 1

    @pytest.mark.asyncio
    async def test_multiple_rag_configs_shared_prefixes(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test multiple RAG configs that share common path prefixes"""
        # Create data that matches multiple configs
        embedding1 = create_mock_embedding("embed1")
        embedding2 = create_mock_embedding("embed2")

        chunked_doc = create_mock_chunked_document(
            "chunk1", [embedding1, embedding2], num_chunks=4
        )
        extraction = create_mock_extraction("ext1", [chunked_doc])
        document = create_mock_document([extraction])

        # Two configs that share extractor and chunker but differ in embedding
        rag_config1 = create_mock_rag_config("rag1", "ext1", "chunk1", "embed1")
        rag_config2 = create_mock_rag_config("rag2", "ext1", "chunk1", "embed2")

        mock_project_magic.documents.return_value = [document]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config1, rag_config2]
        )

        # Both configs should have same extraction and chunking counts
        assert "rag1" in result
        assert "rag2" in result

        for config_id in ["rag1", "rag2"]:
            progress = result[config_id]
            assert progress.total_document_count == 1
            assert progress.total_document_extracted_count == 1
            assert progress.total_document_chunked_count == 1
            assert progress.total_document_embedded_count == 1
            assert (
                progress.total_chunks_indexed_count == 0
            )  # no indexing implemented yet
            assert progress.total_chunk_count == 4  # 4 chunks in the document
            assert progress.total_chunk_completed_count == 0  # same as indexed count
            assert (
                progress.total_document_completed_count == 1
            )  # min of extraction, chunking, embedding

    @pytest.mark.asyncio
    async def test_multiple_rag_configs_different_extractors(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test multiple RAG configs with different extractors"""
        # Create extractions for different extractors
        embedding = create_mock_embedding("embed1")
        chunked_doc = create_mock_chunked_document("chunk1", [embedding], num_chunks=5)

        extraction1 = create_mock_extraction("ext1", [chunked_doc])
        extraction2 = create_mock_extraction("ext2", [chunked_doc])

        document = create_mock_document([extraction1, extraction2])

        # Two configs with different extractors
        rag_config1 = create_mock_rag_config("rag1", "ext1", "chunk1", "embed1")
        rag_config2 = create_mock_rag_config("rag2", "ext2", "chunk1", "embed1")

        mock_project_magic.documents.return_value = [document]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config1, rag_config2]
        )

        # Both should show progress since document has extractions for both extractors
        for config_id in ["rag1", "rag2"]:
            assert config_id in result
            progress = result[config_id]
            assert progress.total_document_count == 1
            assert progress.total_document_extracted_count == 1
            assert progress.total_document_chunked_count == 1
            assert progress.total_document_embedded_count == 1
            assert (
                progress.total_chunks_indexed_count == 0
            )  # no indexing implemented yet
            assert progress.total_chunk_count == 5  # 5 chunks in the document
            assert progress.total_chunk_completed_count == 0  # same as indexed count
            assert (
                progress.total_document_completed_count == 1
            )  # min of extraction, chunking, embedding

    @pytest.mark.asyncio
    async def test_complex_tree_structure(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test a complex tree with multiple documents, extractors, chunkers, and embeddings"""
        # Document 1: ext1 -> chunk1 -> embed1, embed2
        embedding1_1 = create_mock_embedding("embed1")
        embedding1_2 = create_mock_embedding("embed2")
        chunked_doc1_1 = create_mock_chunked_document(
            "chunk1", [embedding1_1, embedding1_2], num_chunks=2
        )
        extraction1_1 = create_mock_extraction("ext1", [chunked_doc1_1])

        # Document 1: ext2 -> chunk2 -> embed1
        embedding1_3 = create_mock_embedding("embed1")
        chunked_doc1_2 = create_mock_chunked_document(
            "chunk2", [embedding1_3], num_chunks=3
        )
        extraction1_2 = create_mock_extraction("ext2", [chunked_doc1_2])

        doc1 = create_mock_document([extraction1_1, extraction1_2])

        # Document 2: ext1 -> chunk1 -> embed1 only
        embedding2_1 = create_mock_embedding("embed1")
        chunked_doc2_1 = create_mock_chunked_document(
            "chunk1", [embedding2_1], num_chunks=4
        )
        extraction2_1 = create_mock_extraction("ext1", [chunked_doc2_1])
        doc2 = create_mock_document([extraction2_1])

        # Test various RAG config combinations
        configs = [
            create_mock_rag_config(
                "rag1", "ext1", "chunk1", "embed1"
            ),  # Should match both docs
            create_mock_rag_config(
                "rag2", "ext1", "chunk1", "embed2"
            ),  # Should match doc1 only
            create_mock_rag_config(
                "rag3", "ext2", "chunk2", "embed1"
            ),  # Should match doc1 only
        ]

        mock_project_magic.documents.return_value = [doc1, doc2]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic,
            configs,  # type: ignore
        )

        # rag1: ext1->chunk1->embed1 appears in both documents
        progress1 = result["rag1"]
        assert progress1.total_document_count == 2
        assert progress1.total_document_extracted_count == 2
        assert progress1.total_document_chunked_count == 2
        assert progress1.total_document_embedded_count == 2
        assert progress1.total_chunks_indexed_count == 0  # no indexing implemented yet
        assert progress1.total_chunk_count == 6  # doc1 has 2 chunks + doc2 has 4 chunks
        assert progress1.total_chunk_completed_count == 0  # same as indexed count
        assert (
            progress1.total_document_completed_count == 2
        )  # min of extraction, chunking, embedding

        # rag2: ext1->chunk1->embed2 appears only in doc1
        progress2 = result["rag2"]
        assert progress2.total_document_count == 2
        assert progress2.total_document_extracted_count == 2  # Both docs have ext1
        assert (
            progress2.total_document_chunked_count == 2
        )  # Both docs have ext1->chunk1
        assert (
            progress2.total_document_embedded_count == 1
        )  # Only doc1 has ext1->chunk1->embed2
        assert progress2.total_chunks_indexed_count == 0  # no indexing implemented yet
        assert progress2.total_chunk_count == 6  # doc1 has 2 chunks + doc2 has 4 chunks
        assert progress2.total_chunk_completed_count == 0  # same as indexed count
        assert progress2.total_document_completed_count == 1  # min(2,2,1) = 1

        # rag3: ext2->chunk2->embed1 appears only in doc1
        progress3 = result["rag3"]
        assert progress3.total_document_count == 2
        assert progress3.total_document_extracted_count == 1  # Only doc1 has ext2
        assert progress3.total_document_chunked_count == 1  # Only doc1 has ext2->chunk2
        assert (
            progress3.total_document_embedded_count == 1
        )  # Only doc1 has ext2->chunk2->embed1
        assert progress3.total_chunks_indexed_count == 0  # no indexing implemented yet
        assert progress3.total_chunk_count == 3  # doc1 ext2->chunk2 has 3 chunks
        assert progress3.total_chunk_completed_count == 0  # same as indexed count
        assert progress3.total_document_completed_count == 1  # min(1,1,1) = 1


class TestComputeCurrentProgressForRagConfig:
    @pytest.mark.asyncio
    async def test_single_config_success(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test computing progress for a single RAG config"""
        embedding = create_mock_embedding("embed1")
        chunked_doc = create_mock_chunked_document("chunk1", [embedding], num_chunks=3)
        extraction = create_mock_extraction("ext1", [chunked_doc])
        document = create_mock_document([extraction])

        rag_config = create_mock_rag_config("rag1", "ext1", "chunk1", "embed1")

        mock_project_magic.documents.return_value = [document]
        result = await compute_current_progress_for_rag_config(
            mock_project_magic, rag_config
        )

        assert isinstance(result, RagProgress)
        assert result.total_document_count == 1
        assert result.total_chunk_count == 3  # 3 chunks in the document
        assert result.total_chunk_completed_count == 0  # same as indexed count
        assert (
            result.total_document_completed_count == 1
        )  # min of extraction, chunking, embedding

    @pytest.mark.asyncio
    async def test_single_config_not_found_error(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test error case when RAG config is not found in results"""
        # Create a config that won't be found (this shouldn't happen in practice)
        rag_config = create_mock_rag_config("nonexistent", "ext1", "chunk1", "embed1")

        # Mock the underlying function to return empty dict to simulate the error
        with patch(
            "kiln_ai.adapters.rag.progress.compute_current_progress_for_rag_configs",
            new_callable=AsyncMock,
            return_value={},
        ):
            with pytest.raises(
                ValueError,
                match="Failed to compute progress for rag config nonexistent",
            ):
                await compute_current_progress_for_rag_config(
                    mock_project_magic, rag_config
                )


class TestCountRecordsInVectorStore:
    @pytest.mark.asyncio
    async def test_count_records_success(self):
        """Test successful counting of records in vector store"""
        mock_rag_config = MagicMock()
        mock_vector_store_config = MagicMock()
        mock_vector_store = AsyncMock()
        mock_vector_store.count_records.return_value = 42

        with patch(
            "kiln_ai.adapters.rag.progress.vector_store_adapter_for_config",
            new_callable=AsyncMock,
            return_value=mock_vector_store,
        ) as mock_adapter:
            result = await count_records_in_vector_store(
                mock_rag_config, mock_vector_store_config
            )

            assert result == 42
            mock_adapter.assert_called_once_with(
                mock_rag_config, mock_vector_store_config
            )
            mock_vector_store.count_records.assert_called_once()


class TestCountRecordsInVectorStoreForRagConfig:
    @pytest.mark.asyncio
    async def test_count_records_success(self, mock_project):
        """Test successful counting of records for RAG config"""

        mock_rag_config = MagicMock()
        mock_rag_config.id = "rag1"
        mock_rag_config.vector_store_config_id = "vector_store_1"

        mock_vector_store_config = MagicMock()

        with (
            patch(
                "kiln_ai.adapters.rag.progress.VectorStoreConfig.from_id_and_parent_path",
                return_value=mock_vector_store_config,
            ) as mock_from_id,
            patch(
                "kiln_ai.adapters.rag.progress.count_records_in_vector_store",
                new_callable=AsyncMock,
                return_value=25,
            ) as mock_count,
        ):
            result = await count_records_in_vector_store_for_rag_config(
                mock_project, mock_rag_config
            )

            assert result == 25
            mock_from_id.assert_called_once_with("vector_store_1", mock_project.path)
            mock_count.assert_called_once_with(
                mock_rag_config, mock_vector_store_config
            )

    @pytest.mark.asyncio
    async def test_count_records_no_vector_store_config_error(self, mock_project):
        """Test error case when vector store config is None"""

        mock_rag_config = MagicMock()
        mock_rag_config.id = "rag1"
        mock_rag_config.vector_store_config_id = "vector_store_1"

        with patch(
            "kiln_ai.adapters.rag.progress.VectorStoreConfig.from_id_and_parent_path",
            return_value=None,
        ) as mock_from_id:
            with pytest.raises(
                ValueError,
                match="Rag config rag1 has no vector store config",
            ):
                await count_records_in_vector_store_for_rag_config(
                    mock_project, mock_rag_config
                )

            mock_from_id.assert_called_once_with("vector_store_1", mock_project.path)


class TestComputeCurrentProgressForRagConfigsWithTags:
    """Test progress computation with document tag filtering"""

    @pytest.mark.asyncio
    async def test_rag_config_with_matching_tags(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test RAG config that filters by tags - some documents match"""
        # Create documents with different tags
        doc1 = create_mock_document([], tags=["python", "backend"])
        doc2 = create_mock_document([], tags=["javascript", "frontend"])
        doc3 = create_mock_document([], tags=["python", "ml"])
        doc4 = create_mock_document([], tags=["java", "backend"])

        # RAG config that filters for "python" tag
        rag_config = create_mock_rag_config(
            "rag1", "ext1", "chunk1", "embed1", tags=["python"]
        )

        mock_project_magic.documents.return_value = [doc1, doc2, doc3, doc4]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config]
        )

        # Should only count doc1 and doc3 (have "python" tag)
        assert len(result) == 1
        assert "rag1" in result
        assert result["rag1"].total_document_count == 2

    @pytest.mark.asyncio
    async def test_rag_config_with_multiple_tags(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test RAG config with multiple tags (OR logic)"""
        # Create documents with different tags
        doc1 = create_mock_document([], tags=["python", "backend"])
        doc2 = create_mock_document([], tags=["javascript", "frontend"])
        doc3 = create_mock_document([], tags=["rust", "systems"])
        doc4 = create_mock_document([], tags=["go", "backend"])

        # RAG config that filters for "python" OR "javascript"
        rag_config = create_mock_rag_config(
            "rag1", "ext1", "chunk1", "embed1", tags=["python", "javascript"]
        )

        mock_project_magic.documents.return_value = [doc1, doc2, doc3, doc4]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config]
        )

        # Should count doc1 (python) and doc2 (javascript)
        assert len(result) == 1
        assert "rag1" in result
        assert result["rag1"].total_document_count == 2

    @pytest.mark.asyncio
    async def test_rag_config_with_no_matching_tags(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test RAG config where no documents match the tags"""
        # Create documents with tags that don't match filter
        doc1 = create_mock_document([], tags=["python", "backend"])
        doc2 = create_mock_document([], tags=["javascript", "frontend"])

        # RAG config that filters for "rust" tag
        rag_config = create_mock_rag_config(
            "rag1", "ext1", "chunk1", "embed1", tags=["rust"]
        )

        mock_project_magic.documents.return_value = [doc1, doc2]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config]
        )

        # Should count 0 documents
        assert len(result) == 1
        assert "rag1" in result
        assert result["rag1"].total_document_count == 0

    @pytest.mark.asyncio
    async def test_rag_config_with_tags_and_extractions(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test progress calculation with tag filtering and existing extractions"""
        # Create documents with tags and extractions
        embedding1 = create_mock_embedding("embed1")
        chunked_doc1 = create_mock_chunked_document(
            "chunk1", [embedding1], num_chunks=3
        )
        extraction1 = create_mock_extraction("ext1", [chunked_doc1])
        doc1 = create_mock_document([extraction1], tags=["python", "ml"])

        # Document with different tag - should be filtered out
        embedding2 = create_mock_embedding("embed1")
        chunked_doc2 = create_mock_chunked_document(
            "chunk1", [embedding2], num_chunks=2
        )
        extraction2 = create_mock_extraction("ext1", [chunked_doc2])
        doc2 = create_mock_document([extraction2], tags=["java", "web"])

        # Document with matching tag but no extractions
        doc3 = create_mock_document([], tags=["python", "backend"])

        rag_config = create_mock_rag_config(
            "rag1", "ext1", "chunk1", "embed1", tags=["python"]
        )

        mock_project_magic.documents.return_value = [doc1, doc2, doc3]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config]
        )

        # Should only consider doc1 and doc3 (have "python" tag)
        assert len(result) == 1
        assert "rag1" in result
        progress = result["rag1"]

        assert progress.total_document_count == 2  # doc1 and doc3
        assert progress.total_document_extracted_count == 1  # only doc1 has extraction
        assert progress.total_document_chunked_count == 1  # only doc1 has chunks
        assert progress.total_document_embedded_count == 1  # only doc1 has embeddings
        assert progress.total_chunk_count == 3  # doc1 has 3 chunks

    @pytest.mark.asyncio
    async def test_multiple_rag_configs_different_tag_filters(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test multiple RAG configs with different tag filters"""
        # Create documents with various tags
        doc1 = create_mock_document([], tags=["python", "ml"])
        doc2 = create_mock_document([], tags=["javascript", "frontend"])
        doc3 = create_mock_document([], tags=["python", "web"])
        doc4 = create_mock_document([], tags=["rust", "systems"])

        # Two RAG configs with different tag filters
        rag_config1 = create_mock_rag_config(
            "rag1", "ext1", "chunk1", "embed1", tags=["python"]
        )
        rag_config2 = create_mock_rag_config(
            "rag2", "ext1", "chunk1", "embed1", tags=["javascript", "rust"]
        )

        mock_project_magic.documents.return_value = [doc1, doc2, doc3, doc4]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config1, rag_config2]
        )

        assert len(result) == 2

        # rag1 should count doc1 and doc3 (python)
        assert result["rag1"].total_document_count == 2

        # rag2 should count doc2 (javascript) and doc4 (rust)
        assert result["rag2"].total_document_count == 2

    @pytest.mark.asyncio
    async def test_rag_config_documents_with_no_tags(
        self, mock_project_magic, mock_vector_store_count
    ):
        """Test RAG config filtering when some documents have no tags"""
        # Mix of documents with and without tags
        doc1 = create_mock_document([], tags=["python", "ml"])
        doc2 = create_mock_document([], tags=None)  # No tags
        doc3 = create_mock_document([], tags=[])  # Empty tags
        doc4 = create_mock_document([], tags=["python", "web"])

        rag_config = create_mock_rag_config(
            "rag1", "ext1", "chunk1", "embed1", tags=["python"]
        )

        mock_project_magic.documents.return_value = [doc1, doc2, doc3, doc4]
        result = await compute_current_progress_for_rag_configs(
            mock_project_magic, [rag_config]
        )

        # Should only count doc1 and doc4 (have "python" tag)
        assert len(result) == 1
        assert result["rag1"].total_document_count == 2
