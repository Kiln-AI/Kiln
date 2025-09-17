from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kiln_ai.adapters.chunkers.base_chunker import BaseChunker, ChunkingResult
from kiln_ai.adapters.embedding.base_embedding_adapter import (
    BaseEmbeddingAdapter,
    EmbeddingResult,
)
from kiln_ai.adapters.extractors.base_extractor import BaseExtractor, ExtractionOutput
from kiln_ai.adapters.rag.progress import LogMessage, RagProgress
from kiln_ai.adapters.rag.rag_runners import (
    ChunkerJob,
    EmbeddingJob,
    ExtractorJob,
    GenericErrorCollector,
    RagChunkingStepRunner,
    RagEmbeddingStepRunner,
    RagExtractionStepRunner,
    RagIndexingStepRunner,
    RagStepRunnerProgress,
    RagWorkflowRunner,
    RagWorkflowRunnerConfiguration,
    RagWorkflowStepNames,
    execute_chunker_job,
    execute_embedding_job,
    execute_extractor_job,
)
from kiln_ai.datamodel.chunk import ChunkedDocument, ChunkerConfig, ChunkerType
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractorConfig,
    ExtractorType,
    OutputFormat,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.rag import RagConfig


# Test fixtures
@pytest.fixture
def mock_project():
    """Create a mock project for testing"""
    project = MagicMock(spec=Project)
    return project


@pytest.fixture
def mock_document():
    """Create a mock document for testing"""
    doc = MagicMock(spec=Document)
    doc.path = Path("test_doc.txt")
    doc.original_file = MagicMock()
    doc.original_file.attachment = MagicMock()
    doc.original_file.attachment.resolve_path.return_value = "test_file_path"
    doc.original_file.mime_type = "text/plain"
    return doc


@pytest.fixture
def mock_extractor_config():
    """Create a mock extractor config for testing"""
    config = MagicMock()
    config.id = "extractor-123"
    config.extractor_type = "test_extractor"
    return config


@pytest.fixture
def mock_chunker_config():
    """Create a mock chunker config for testing"""
    config = MagicMock(spec=ChunkerConfig)
    config.id = "chunker-123"
    config.chunker_type = "test_chunker"
    return config


@pytest.fixture
def mock_embedding_config():
    """Create a mock embedding config for testing"""
    config = MagicMock(spec=EmbeddingConfig)
    config.id = "embedding-123"
    return config


@pytest.fixture
def real_extractor_config(mock_project):
    """Create a real extractor config for workflow testing"""
    return ExtractorConfig(
        name="test-extractor",
        model_provider_name="test",
        model_name="test-model",
        extractor_type=ExtractorType.LITELLM,
        output_format=OutputFormat.MARKDOWN,
        properties={
            "prompt_document": "Transcribe the document.",
            "prompt_audio": "Transcribe the audio.",
            "prompt_video": "Transcribe the video.",
            "prompt_image": "Describe the image.",
        },
        parent=mock_project,
    )


@pytest.fixture
def real_chunker_config(mock_project):
    """Create a real chunker config for workflow testing"""
    return ChunkerConfig(
        name="test-chunker",
        chunker_type=ChunkerType.FIXED_WINDOW,
        properties={"chunk_size": 500, "chunk_overlap": 50},
        parent=mock_project,
    )


@pytest.fixture
def real_embedding_config(mock_project):
    """Create a real embedding config for workflow testing"""
    return EmbeddingConfig(
        name="test-embedding",
        model_provider_name=ModelProviderName.openai,
        model_name="text-embedding-3-small",
        properties={"dimensions": 1536},
        parent=mock_project,
    )


@pytest.fixture
def real_rag_config(mock_project):
    """Create a real RAG config for workflow testing"""
    return RagConfig(
        name="test-rag",
        extractor_config_id="extractor-123",
        chunker_config_id="chunker-123",
        embedding_config_id="embedding-123",
        vector_store_config_id="vector-store-123",
        parent=mock_project,
    )


@pytest.fixture
def mock_extraction():
    """Create a mock extraction for testing"""
    extraction = MagicMock(spec=Extraction)
    extraction.extractor_config_id = "extractor-123"
    extraction.path = Path("test_extraction.txt")
    extraction.output_content = AsyncMock(return_value="test content")
    return extraction


@pytest.fixture
def mock_chunked_document():
    """Create a mock chunked document for testing"""
    chunked_doc = MagicMock(spec=ChunkedDocument)
    chunked_doc.chunker_config_id = "chunker-123"
    chunked_doc.path = Path("test_chunked.txt")
    chunked_doc.load_chunks_text = AsyncMock(return_value=["chunk 1", "chunk 2"])
    return chunked_doc


@pytest.fixture
def mock_rag_config():
    """Create a mock RAG config for testing"""
    config = MagicMock(spec=RagConfig)
    config.id = "rag-123"
    config.tags = None
    return config


# Tests for dataclasses
class TestExtractorJob:
    def test_extractor_job_creation(self, mock_document, mock_extractor_config):
        job = ExtractorJob(doc=mock_document, extractor_config=mock_extractor_config)
        assert job.doc == mock_document
        assert job.extractor_config == mock_extractor_config


class TestChunkerJob:
    def test_chunker_job_creation(self, mock_extraction, mock_chunker_config):
        job = ChunkerJob(extraction=mock_extraction, chunker_config=mock_chunker_config)
        assert job.extraction == mock_extraction
        assert job.chunker_config == mock_chunker_config


class TestEmbeddingJob:
    def test_embedding_job_creation(self, mock_chunked_document, mock_embedding_config):
        job = EmbeddingJob(
            chunked_document=mock_chunked_document,
            embedding_config=mock_embedding_config,
        )
        assert job.chunked_document == mock_chunked_document
        assert job.embedding_config == mock_embedding_config


class TestRagStepRunnerProgress:
    def test_progress_creation_with_defaults(self):
        progress = RagStepRunnerProgress()
        assert progress.success_count is None
        assert progress.error_count is None
        assert progress.logs == []

    def test_progress_creation_with_values(self):
        logs = [LogMessage(level="info", message="test")]
        progress = RagStepRunnerProgress(success_count=5, error_count=2, logs=logs)
        assert progress.success_count == 5
        assert progress.error_count == 2
        assert progress.logs == logs


# Tests for GenericErrorCollector
class TestGenericErrorCollector:
    @pytest.fixture
    def error_collector(self):
        return GenericErrorCollector()

    @pytest.mark.asyncio
    async def test_on_success_does_nothing(self, error_collector):
        job = "test_job"
        await error_collector.on_success(job)
        assert len(error_collector.errors) == 0

    @pytest.mark.asyncio
    async def test_on_error_collects_error(self, error_collector):
        job = "test_job"
        error = Exception("test error")
        await error_collector.on_error(job, error)

        assert len(error_collector.errors) == 1
        assert error_collector.errors[0] == (job, error)

    def test_get_errors_returns_all_errors(self, error_collector):
        # Add some errors manually
        error1 = Exception("error 1")
        error2 = Exception("error 2")
        error_collector.errors = [("job1", error1), ("job2", error2)]

        errors, last_idx = error_collector.get_errors()
        assert len(errors) == 2
        assert errors[0] == ("job1", error1)
        assert errors[1] == ("job2", error2)
        assert last_idx == 2

    def test_get_errors_with_start_idx(self, error_collector):
        # Add some errors manually
        error1 = Exception("error 1")
        error2 = Exception("error 2")
        error3 = Exception("error 3")
        error_collector.errors = [("job1", error1), ("job2", error2), ("job3", error3)]

        errors, last_idx = error_collector.get_errors(start_idx=1)
        assert len(errors) == 2
        assert errors[0] == ("job2", error2)
        assert errors[1] == ("job3", error3)
        assert last_idx == 3

    def test_get_errors_negative_start_idx_raises_error(self, error_collector):
        # Add some errors
        error_collector.errors = [("job1", Exception()), ("job2", Exception())]

        with pytest.raises(ValueError, match="start_idx must be non-negative"):
            error_collector.get_errors(start_idx=-1)

    def test_get_errors_with_start_idx_zero(self, error_collector):
        # Add some errors
        error1 = Exception("error 1")
        error2 = Exception("error 2")
        error_collector.errors = [("job1", error1), ("job2", error2)]

        errors, last_idx = error_collector.get_errors(start_idx=0)
        assert len(errors) == 2
        assert errors[0] == ("job1", error1)
        assert errors[1] == ("job2", error2)
        assert last_idx == 2

    def test_get_errors_start_idx_equal_to_length(self, error_collector):
        # Add some errors
        error_collector.errors = [("job1", Exception()), ("job2", Exception())]

        # start_idx equal to length should return empty list
        errors, last_idx = error_collector.get_errors(start_idx=2)
        assert len(errors) == 0
        assert last_idx == 2

    def test_get_errors_start_idx_greater_than_length(self, error_collector):
        # Add some errors
        error_collector.errors = [("job1", Exception()), ("job2", Exception())]

        # start_idx greater than length should return empty list
        errors, last_idx = error_collector.get_errors(start_idx=5)
        assert len(errors) == 0
        assert last_idx == 5

    def test_get_errors_with_empty_error_list(self, error_collector):
        # Test with no errors and different start_idx values
        errors, last_idx = error_collector.get_errors(start_idx=0)
        assert len(errors) == 0
        assert last_idx == 0

        errors, last_idx = error_collector.get_errors(start_idx=1)
        assert len(errors) == 0
        assert last_idx == 1

    def test_get_errors_boundary_conditions(self, error_collector):
        # Test with single error
        single_error = Exception("single error")
        error_collector.errors = [("job1", single_error)]

        # Get from start
        errors, last_idx = error_collector.get_errors(start_idx=0)
        assert len(errors) == 1
        assert errors[0] == ("job1", single_error)
        assert last_idx == 1

        # Get from index 1 (equal to length)
        errors, last_idx = error_collector.get_errors(start_idx=1)
        assert len(errors) == 0
        assert last_idx == 1

    def test_get_error_count(self, error_collector):
        assert error_collector.get_error_count() == 0

        error_collector.errors = [("job1", Exception()), ("job2", Exception())]
        assert error_collector.get_error_count() == 2


# Tests for job execution functions
class TestExecuteExtractorJob:
    @pytest.mark.asyncio
    async def test_execute_extractor_job_success(
        self, mock_document, mock_extractor_config
    ):
        # Setup mocks
        job = ExtractorJob(doc=mock_document, extractor_config=mock_extractor_config)

        mock_extractor = MagicMock(spec=BaseExtractor)
        mock_output = ExtractionOutput(
            content="extracted content", content_format=OutputFormat.TEXT
        )
        mock_extractor.extract = AsyncMock(return_value=mock_output)

        with patch(
            "kiln_ai.adapters.rag.rag_runners.Extraction"
        ) as mock_extraction_class:
            mock_extraction = MagicMock()
            mock_extraction_class.return_value = mock_extraction

            result = await execute_extractor_job(job, mock_extractor)

            assert result is True
            mock_extractor.extract.assert_called_once()
            mock_extraction.save_to_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_extractor_job_no_path_raises_error(
        self, mock_extractor_config
    ):
        # Setup document without path
        mock_document = MagicMock(spec=Document)
        mock_document.path = None

        job = ExtractorJob(doc=mock_document, extractor_config=mock_extractor_config)
        mock_extractor = MagicMock(spec=BaseExtractor)

        with pytest.raises(ValueError, match="Document path is not set"):
            await execute_extractor_job(job, mock_extractor)


class TestExecuteChunkerJob:
    @pytest.mark.asyncio
    async def test_execute_chunker_job_success(
        self, mock_extraction, mock_chunker_config
    ):
        # Setup mocks
        job = ChunkerJob(extraction=mock_extraction, chunker_config=mock_chunker_config)

        mock_chunker = MagicMock(spec=BaseChunker)
        mock_chunking_result = MagicMock(spec=ChunkingResult)
        mock_chunk = MagicMock()
        mock_chunk.text = "chunk text"
        mock_chunking_result.chunks = [mock_chunk]
        mock_chunker.chunk = AsyncMock(return_value=mock_chunking_result)

        with patch(
            "kiln_ai.adapters.rag.rag_runners.ChunkedDocument"
        ) as mock_chunked_doc_class:
            mock_chunked_doc = MagicMock()
            mock_chunked_doc_class.return_value = mock_chunked_doc

            result = await execute_chunker_job(job, mock_chunker)

            assert result is True
            mock_chunker.chunk.assert_called_once_with("test content")
            mock_chunked_doc.save_to_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_chunker_job_no_content_raises_error(
        self, mock_chunker_config
    ):
        # Setup extraction without content
        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.output_content = AsyncMock(return_value=None)

        job = ChunkerJob(extraction=mock_extraction, chunker_config=mock_chunker_config)
        mock_chunker = MagicMock(spec=BaseChunker)

        with pytest.raises(ValueError, match="Extraction output content is not set"):
            await execute_chunker_job(job, mock_chunker)

    @pytest.mark.asyncio
    async def test_execute_chunker_job_no_chunking_result_raises_error(
        self, mock_extraction, mock_chunker_config
    ):
        job = ChunkerJob(extraction=mock_extraction, chunker_config=mock_chunker_config)

        mock_chunker = MagicMock(spec=BaseChunker)
        mock_chunker.chunk = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Chunking result is not set"):
            await execute_chunker_job(job, mock_chunker)


class TestExecuteEmbeddingJob:
    @pytest.mark.asyncio
    async def test_execute_embedding_job_success(
        self, mock_chunked_document, mock_embedding_config
    ):
        # Setup mocks
        job = EmbeddingJob(
            chunked_document=mock_chunked_document,
            embedding_config=mock_embedding_config,
        )

        mock_embedding_adapter = MagicMock(spec=BaseEmbeddingAdapter)
        mock_embedding_result = MagicMock(spec=EmbeddingResult)
        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]
        mock_embedding_result.embeddings = [mock_embedding]
        mock_embedding_adapter.generate_embeddings = AsyncMock(
            return_value=mock_embedding_result
        )

        with patch(
            "kiln_ai.adapters.rag.rag_runners.ChunkEmbeddings"
        ) as mock_chunk_embeddings_class:
            mock_chunk_embeddings = MagicMock()
            mock_chunk_embeddings_class.return_value = mock_chunk_embeddings

            result = await execute_embedding_job(job, mock_embedding_adapter)

            assert result is True
            mock_embedding_adapter.generate_embeddings.assert_called_once_with(
                input_texts=["chunk 1", "chunk 2"]
            )
            mock_chunk_embeddings.save_to_file.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("return_value", [None, []])
    async def test_execute_embedding_job_no_chunks_raises_error(
        self, mock_embedding_config, return_value
    ):
        # Setup chunked document without chunks
        mock_chunked_document = MagicMock(spec=ChunkedDocument, id="123")
        mock_chunked_document.load_chunks_text = AsyncMock(return_value=return_value)

        job = EmbeddingJob(
            chunked_document=mock_chunked_document,
            embedding_config=mock_embedding_config,
        )
        mock_embedding_adapter = MagicMock(spec=BaseEmbeddingAdapter)

        with pytest.raises(
            ValueError, match="Failed to load chunks for chunked document: 123"
        ):
            await execute_embedding_job(job, mock_embedding_adapter)

    @pytest.mark.asyncio
    async def test_execute_embedding_job_no_embedding_result_raises_error(
        self, mock_chunked_document, mock_embedding_config
    ):
        mock_chunked_document.id = "123"
        job = EmbeddingJob(
            chunked_document=mock_chunked_document,
            embedding_config=mock_embedding_config,
        )

        mock_embedding_adapter = MagicMock(spec=BaseEmbeddingAdapter)
        mock_embedding_adapter.generate_embeddings = AsyncMock(return_value=None)

        with pytest.raises(
            ValueError, match="Failed to generate embeddings for chunked document: 123"
        ):
            await execute_embedding_job(job, mock_embedding_adapter)


# Tests for step runners
class TestRagExtractionStepRunner:
    @pytest.fixture
    def extraction_runner(self, mock_project, mock_extractor_config):
        return RagExtractionStepRunner(
            project=mock_project, extractor_config=mock_extractor_config, concurrency=2
        )

    def test_stage_returns_extracting(self, extraction_runner):
        assert extraction_runner.stage() == RagWorkflowStepNames.EXTRACTING

    def test_has_extraction_returns_true_when_found(
        self, extraction_runner, mock_document
    ):
        # Setup mock extraction with matching config ID
        mock_extraction = MagicMock()
        mock_extraction.extractor_config_id = "extractor-123"
        mock_document.extractions.return_value = [mock_extraction]

        result = extraction_runner.has_extraction(mock_document, "extractor-123")
        assert result is True

    def test_has_extraction_returns_false_when_not_found(
        self, extraction_runner, mock_document
    ):
        # Setup mock extraction with different config ID
        mock_extraction = MagicMock()
        mock_extraction.extractor_config_id = "different-extractor"
        mock_document.extractions.return_value = [mock_extraction]

        result = extraction_runner.has_extraction(mock_document, "extractor-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_collect_jobs_returns_jobs_for_documents_without_extractions(
        self, extraction_runner
    ):
        # Setup mock documents - one with extraction, one without
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.extractions.return_value = []  # No extractions

        mock_doc2 = MagicMock(spec=Document)
        mock_extraction = MagicMock()
        mock_extraction.extractor_config_id = "extractor-123"
        mock_doc2.extractions.return_value = [
            mock_extraction
        ]  # Has matching extraction

        extraction_runner.project.documents.return_value = [mock_doc1, mock_doc2]

        jobs = await extraction_runner.collect_jobs()

        # Should only create job for doc1 (no extraction)
        assert len(jobs) == 1
        assert jobs[0].doc == mock_doc1
        assert jobs[0].extractor_config == extraction_runner.extractor_config

    @pytest.mark.asyncio
    async def test_collect_jobs_with_document_ids_filters_documents(
        self, extraction_runner
    ):
        # Setup mock documents with specific IDs
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_doc1.extractions.return_value = []  # No extractions

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_doc2.extractions.return_value = []  # No extractions

        mock_doc3 = MagicMock(spec=Document)
        mock_doc3.id = "doc-3"
        mock_doc3.extractions.return_value = []  # No extractions

        extraction_runner.project.documents.return_value = [
            mock_doc1,
            mock_doc2,
            mock_doc3,
        ]

        # Only process doc-1 and doc-3
        jobs = await extraction_runner.collect_jobs(document_ids=["doc-1", "doc-3"])

        # Should only create jobs for doc-1 and doc-3
        assert len(jobs) == 2
        job_doc_ids = {job.doc.id for job in jobs}
        assert job_doc_ids == {"doc-1", "doc-3"}

    @pytest.mark.asyncio
    async def test_collect_jobs_with_empty_document_ids_processes_all_documents(
        self, extraction_runner
    ):
        # Setup mock documents
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_doc1.extractions.return_value = []

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_doc2.extractions.return_value = []

        extraction_runner.project.documents.return_value = [mock_doc1, mock_doc2]

        # Empty list should behave like None
        jobs_empty = await extraction_runner.collect_jobs(document_ids=[])
        jobs_none = await extraction_runner.collect_jobs(document_ids=None)

        # Both should process all documents
        assert len(jobs_empty) == 2
        assert len(jobs_none) == 2

        # Should have same document IDs
        empty_doc_ids = {job.doc.id for job in jobs_empty}
        none_doc_ids = {job.doc.id for job in jobs_none}
        assert empty_doc_ids == none_doc_ids == {"doc-1", "doc-2"}

    @pytest.mark.asyncio
    async def test_run_with_document_ids_filters_documents(self, extraction_runner):
        # Setup mock documents with specific IDs
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_doc1.extractions.return_value = []
        mock_doc1.path = Path("doc1.txt")
        mock_doc1.original_file = MagicMock()
        mock_doc1.original_file.attachment = MagicMock()
        mock_doc1.original_file.attachment.resolve_path.return_value = "doc1_path"
        mock_doc1.original_file.mime_type = "text/plain"

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_doc2.extractions.return_value = []
        mock_doc2.path = Path("doc2.txt")
        mock_doc2.original_file = MagicMock()
        mock_doc2.original_file.attachment = MagicMock()
        mock_doc2.original_file.attachment.resolve_path.return_value = "doc2_path"
        mock_doc2.original_file.mime_type = "text/plain"

        extraction_runner.project.documents.return_value = [mock_doc1, mock_doc2]

        with (
            patch(
                "kiln_ai.adapters.rag.rag_runners.extractor_adapter_from_type"
            ) as mock_adapter_factory,
            patch(
                "kiln_ai.adapters.rag.rag_runners.AsyncJobRunner"
            ) as mock_job_runner_class,
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
        ):
            mock_extractor = MagicMock(spec=BaseExtractor)
            mock_adapter_factory.return_value = mock_extractor

            mock_job_runner = MagicMock()
            mock_job_runner_class.return_value = mock_job_runner

            async def mock_runner_progress():
                yield MagicMock(complete=1)

            mock_job_runner.run.return_value = mock_runner_progress()

            # Run with specific document IDs
            progress_values = []
            async for progress in extraction_runner.run(document_ids=["doc-1"]):
                progress_values.append(progress)

            # Verify job runner was created with only one job (for doc-1)
            mock_job_runner_class.assert_called_once()
            call_args = mock_job_runner_class.call_args
            jobs = call_args.kwargs["jobs"]
            assert len(jobs) == 1
            assert jobs[0].doc.id == "doc-1"

    @pytest.mark.asyncio
    async def test_run_with_empty_document_ids_behaves_like_none(
        self, extraction_runner
    ):
        # Setup mock documents
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_doc1.extractions.return_value = []
        mock_doc1.path = Path("doc1.txt")
        mock_doc1.original_file = MagicMock()
        mock_doc1.original_file.attachment = MagicMock()
        mock_doc1.original_file.attachment.resolve_path.return_value = "doc1_path"
        mock_doc1.original_file.mime_type = "text/plain"

        extraction_runner.project.documents.return_value = [mock_doc1]

        with (
            patch(
                "kiln_ai.adapters.rag.rag_runners.extractor_adapter_from_type"
            ) as mock_adapter_factory,
            patch(
                "kiln_ai.adapters.rag.rag_runners.AsyncJobRunner"
            ) as mock_job_runner_class,
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
        ):
            mock_extractor = MagicMock(spec=BaseExtractor)
            mock_adapter_factory.return_value = mock_extractor

            mock_job_runner = MagicMock()
            mock_job_runner_class.return_value = mock_job_runner

            async def mock_runner_progress():
                yield MagicMock(complete=1)

            mock_job_runner.run.return_value = mock_runner_progress()

            # Test with empty list
            jobs_with_empty = None
            async for _ in extraction_runner.run(document_ids=[]):
                pass
            call_args_empty = mock_job_runner_class.call_args
            jobs_with_empty = call_args_empty.kwargs["jobs"]

            # Reset mock
            mock_job_runner_class.reset_mock()

            # Test with None
            jobs_with_none = None
            async for _ in extraction_runner.run(document_ids=None):
                pass
            call_args_none = mock_job_runner_class.call_args
            jobs_with_none = call_args_none.kwargs["jobs"]

            # Both should have same number of jobs
            assert len(jobs_with_empty) == len(jobs_with_none) == 1


class TestRagChunkingStepRunner:
    @pytest.fixture
    def chunking_runner(self, mock_project, mock_extractor_config, mock_chunker_config):
        return RagChunkingStepRunner(
            project=mock_project,
            extractor_config=mock_extractor_config,
            chunker_config=mock_chunker_config,
            concurrency=2,
        )

    def test_stage_returns_chunking(self, chunking_runner):
        assert chunking_runner.stage() == RagWorkflowStepNames.CHUNKING

    def test_has_chunks_returns_true_when_found(self, chunking_runner, mock_extraction):
        # Setup mock chunked document with matching config ID
        mock_chunked_doc = MagicMock()
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]

        result = chunking_runner.has_chunks(mock_extraction, "chunker-123")
        assert result is True

    def test_has_chunks_returns_false_when_not_found(
        self, chunking_runner, mock_extraction
    ):
        # Setup mock chunked document with different config ID
        mock_chunked_doc = MagicMock()
        mock_chunked_doc.chunker_config_id = "different-chunker"
        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]

        result = chunking_runner.has_chunks(mock_extraction, "chunker-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_collect_jobs_returns_jobs_for_extractions_without_chunks(
        self, chunking_runner
    ):
        # Setup mock document with extractions
        mock_doc = MagicMock(spec=Document)

        # Extraction with matching extractor config but no chunks
        mock_extraction1 = MagicMock(spec=Extraction)
        mock_extraction1.extractor_config_id = "extractor-123"
        mock_extraction1.created_at = datetime(2023, 1, 1)
        mock_extraction1.chunked_documents.return_value = []

        # Extraction with matching extractor config and existing chunks
        mock_extraction2 = MagicMock(spec=Extraction)
        mock_extraction2.extractor_config_id = "extractor-123"
        mock_extraction2.created_at = datetime(2023, 1, 2)
        mock_chunked_doc = MagicMock()
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_extraction2.chunked_documents.return_value = [mock_chunked_doc]

        # Extraction with different extractor config
        mock_extraction3 = MagicMock(spec=Extraction)
        mock_extraction3.extractor_config_id = "different-extractor"
        mock_extraction3.created_at = datetime(2023, 1, 3)
        mock_extraction3.chunked_documents.return_value = []

        mock_doc.extractions.return_value = [
            mock_extraction1,
            mock_extraction2,
            mock_extraction3,
        ]
        chunking_runner.project.documents.return_value = [mock_doc]

        jobs = await chunking_runner.collect_jobs()

        # Should only create job for extraction1 (matching extractor, no chunks)
        assert len(jobs) == 1
        assert jobs[0].extraction == mock_extraction1
        assert jobs[0].chunker_config == chunking_runner.chunker_config

    @pytest.mark.asyncio
    async def test_collect_jobs_with_document_ids_filters_documents(
        self, chunking_runner
    ):
        # Setup mock documents with specific IDs
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_extraction1 = MagicMock(spec=Extraction)
        mock_extraction1.extractor_config_id = "extractor-123"
        mock_extraction1.created_at = datetime(2023, 1, 1)
        mock_extraction1.chunked_documents.return_value = []
        mock_doc1.extractions.return_value = [mock_extraction1]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_extraction2 = MagicMock(spec=Extraction)
        mock_extraction2.extractor_config_id = "extractor-123"
        mock_extraction2.created_at = datetime(2023, 1, 2)
        mock_extraction2.chunked_documents.return_value = []
        mock_doc2.extractions.return_value = [mock_extraction2]

        mock_doc3 = MagicMock(spec=Document)
        mock_doc3.id = "doc-3"
        mock_extraction3 = MagicMock(spec=Extraction)
        mock_extraction3.extractor_config_id = "extractor-123"
        mock_extraction3.created_at = datetime(2023, 1, 3)
        mock_extraction3.chunked_documents.return_value = []
        mock_doc3.extractions.return_value = [mock_extraction3]

        chunking_runner.project.documents.return_value = [
            mock_doc1,
            mock_doc2,
            mock_doc3,
        ]

        # Only process doc-1 and doc-3
        jobs = await chunking_runner.collect_jobs(document_ids=["doc-1", "doc-3"])

        # Should only create jobs for doc-1 and doc-3
        assert len(jobs) == 2
        job_doc_ids = {job.extraction.extractor_config_id for job in jobs}
        assert job_doc_ids == {
            "extractor-123"
        }  # Both should have matching extractor config

        # Verify the extractions come from the right documents
        extraction_times = {job.extraction.created_at for job in jobs}
        assert extraction_times == {datetime(2023, 1, 1), datetime(2023, 1, 3)}

    @pytest.mark.asyncio
    async def test_collect_jobs_with_empty_document_ids_processes_all_documents(
        self, chunking_runner
    ):
        # Setup mock documents
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_extraction1 = MagicMock(spec=Extraction)
        mock_extraction1.extractor_config_id = "extractor-123"
        mock_extraction1.created_at = datetime(2023, 1, 1)
        mock_extraction1.chunked_documents.return_value = []
        mock_doc1.extractions.return_value = [mock_extraction1]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_extraction2 = MagicMock(spec=Extraction)
        mock_extraction2.extractor_config_id = "extractor-123"
        mock_extraction2.created_at = datetime(2023, 1, 2)
        mock_extraction2.chunked_documents.return_value = []
        mock_doc2.extractions.return_value = [mock_extraction2]

        chunking_runner.project.documents.return_value = [mock_doc1, mock_doc2]

        # Empty list should behave like None
        jobs_empty = await chunking_runner.collect_jobs(document_ids=[])
        jobs_none = await chunking_runner.collect_jobs(document_ids=None)

        # Both should process all documents
        assert len(jobs_empty) == 2
        assert len(jobs_none) == 2

        # Should have same extraction times
        empty_times = {job.extraction.created_at for job in jobs_empty}
        none_times = {job.extraction.created_at for job in jobs_none}
        assert empty_times == none_times == {datetime(2023, 1, 1), datetime(2023, 1, 2)}


class TestRagEmbeddingStepRunner:
    @pytest.fixture
    def embedding_runner(
        self,
        mock_project,
        mock_extractor_config,
        mock_chunker_config,
        mock_embedding_config,
    ):
        return RagEmbeddingStepRunner(
            project=mock_project,
            extractor_config=mock_extractor_config,
            chunker_config=mock_chunker_config,
            embedding_config=mock_embedding_config,
            concurrency=2,
        )

    def test_stage_returns_embedding(self, embedding_runner):
        assert embedding_runner.stage() == RagWorkflowStepNames.EMBEDDING

    def test_has_embeddings_returns_true_when_found(
        self, embedding_runner, mock_chunked_document
    ):
        # Setup mock chunk embeddings with matching config ID
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunked_document.chunk_embeddings.return_value = [mock_chunk_embeddings]

        result = embedding_runner.has_embeddings(mock_chunked_document, "embedding-123")
        assert result is True

    def test_has_embeddings_returns_false_when_not_found(
        self, embedding_runner, mock_chunked_document
    ):
        # Setup mock chunk embeddings with different config ID
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "different-embedding"
        mock_chunked_document.chunk_embeddings.return_value = [mock_chunk_embeddings]

        result = embedding_runner.has_embeddings(mock_chunked_document, "embedding-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_collect_jobs_returns_jobs_for_chunked_documents_without_embeddings(
        self, embedding_runner
    ):
        # Setup mock document with extraction and chunked documents
        mock_doc = MagicMock(spec=Document)

        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.extractor_config_id = "extractor-123"
        mock_extraction.created_at = datetime(2023, 1, 1)

        # Chunked document with matching chunker config but no embeddings
        mock_chunked_doc1 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc1.chunker_config_id = "chunker-123"
        mock_chunked_doc1.created_at = datetime(2023, 1, 1)
        mock_chunked_doc1.chunk_embeddings.return_value = []

        # Chunked document with matching chunker config and existing embeddings
        mock_chunked_doc2 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc2.chunker_config_id = "chunker-123"
        mock_chunked_doc2.created_at = datetime(2023, 1, 2)
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunked_doc2.chunk_embeddings.return_value = [mock_chunk_embeddings]

        mock_extraction.chunked_documents.return_value = [
            mock_chunked_doc1,
            mock_chunked_doc2,
        ]
        mock_doc.extractions.return_value = [mock_extraction]
        embedding_runner.project.documents.return_value = [mock_doc]

        jobs = await embedding_runner.collect_jobs()

        # Should only create job for chunked_doc1 (matching configs, no embeddings)
        assert len(jobs) == 1
        assert jobs[0].chunked_document == mock_chunked_doc1
        assert jobs[0].embedding_config == embedding_runner.embedding_config

    @pytest.mark.asyncio
    async def test_collect_jobs_with_document_ids_filters_documents(
        self, embedding_runner
    ):
        # Setup mock documents with specific IDs
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_extraction1 = MagicMock(spec=Extraction)
        mock_extraction1.extractor_config_id = "extractor-123"
        mock_extraction1.created_at = datetime(2023, 1, 1)
        mock_chunked_doc1 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc1.chunker_config_id = "chunker-123"
        mock_chunked_doc1.created_at = datetime(2023, 1, 1)
        mock_chunked_doc1.chunk_embeddings.return_value = []
        mock_extraction1.chunked_documents.return_value = [mock_chunked_doc1]
        mock_doc1.extractions.return_value = [mock_extraction1]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_extraction2 = MagicMock(spec=Extraction)
        mock_extraction2.extractor_config_id = "extractor-123"
        mock_extraction2.created_at = datetime(2023, 1, 2)
        mock_chunked_doc2 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc2.chunker_config_id = "chunker-123"
        mock_chunked_doc2.created_at = datetime(2023, 1, 2)
        mock_chunked_doc2.chunk_embeddings.return_value = []
        mock_extraction2.chunked_documents.return_value = [mock_chunked_doc2]
        mock_doc2.extractions.return_value = [mock_extraction2]

        mock_doc3 = MagicMock(spec=Document)
        mock_doc3.id = "doc-3"
        mock_extraction3 = MagicMock(spec=Extraction)
        mock_extraction3.extractor_config_id = "extractor-123"
        mock_extraction3.created_at = datetime(2023, 1, 3)
        mock_chunked_doc3 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc3.chunker_config_id = "chunker-123"
        mock_chunked_doc3.created_at = datetime(2023, 1, 3)
        mock_chunked_doc3.chunk_embeddings.return_value = []
        mock_extraction3.chunked_documents.return_value = [mock_chunked_doc3]
        mock_doc3.extractions.return_value = [mock_extraction3]

        embedding_runner.project.documents.return_value = [
            mock_doc1,
            mock_doc2,
            mock_doc3,
        ]

        # Only process doc-1 and doc-3
        jobs = await embedding_runner.collect_jobs(document_ids=["doc-1", "doc-3"])

        # Should only create jobs for doc-1 and doc-3
        assert len(jobs) == 2
        job_doc_times = {job.chunked_document.created_at for job in jobs}
        assert job_doc_times == {datetime(2023, 1, 1), datetime(2023, 1, 3)}

    @pytest.mark.asyncio
    async def test_collect_jobs_with_empty_document_ids_processes_all_documents(
        self, embedding_runner
    ):
        # Setup mock documents
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_extraction1 = MagicMock(spec=Extraction)
        mock_extraction1.extractor_config_id = "extractor-123"
        mock_extraction1.created_at = datetime(2023, 1, 1)
        mock_chunked_doc1 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc1.chunker_config_id = "chunker-123"
        mock_chunked_doc1.created_at = datetime(2023, 1, 1)
        mock_chunked_doc1.chunk_embeddings.return_value = []
        mock_extraction1.chunked_documents.return_value = [mock_chunked_doc1]
        mock_doc1.extractions.return_value = [mock_extraction1]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_extraction2 = MagicMock(spec=Extraction)
        mock_extraction2.extractor_config_id = "extractor-123"
        mock_extraction2.created_at = datetime(2023, 1, 2)
        mock_chunked_doc2 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc2.chunker_config_id = "chunker-123"
        mock_chunked_doc2.created_at = datetime(2023, 1, 2)
        mock_chunked_doc2.chunk_embeddings.return_value = []
        mock_extraction2.chunked_documents.return_value = [mock_chunked_doc2]
        mock_doc2.extractions.return_value = [mock_extraction2]

        embedding_runner.project.documents.return_value = [mock_doc1, mock_doc2]

        # Empty list should behave like None
        jobs_empty = await embedding_runner.collect_jobs(document_ids=[])
        jobs_none = await embedding_runner.collect_jobs(document_ids=None)

        # Both should process all documents
        assert len(jobs_empty) == 2
        assert len(jobs_none) == 2

        # Should have same chunked document times
        empty_times = {job.chunked_document.created_at for job in jobs_empty}
        none_times = {job.chunked_document.created_at for job in jobs_none}
        assert empty_times == none_times == {datetime(2023, 1, 1), datetime(2023, 1, 2)}


class TestRagIndexingStepRunner:
    @pytest.fixture
    def indexing_runner(
        self,
        mock_project,
        mock_extractor_config,
        mock_chunker_config,
        mock_embedding_config,
        mock_rag_config,
    ):
        from kiln_ai.adapters.rag.rag_runners import RagIndexingStepRunner
        from kiln_ai.datamodel.vector_store import VectorStoreConfig

        # Create a mock vector store config
        mock_vector_store_config = MagicMock(spec=VectorStoreConfig)
        mock_vector_store_config.id = "vector-store-123"

        return RagIndexingStepRunner(
            project=mock_project,
            extractor_config=mock_extractor_config,
            chunker_config=mock_chunker_config,
            embedding_config=mock_embedding_config,
            vector_store_config=mock_vector_store_config,
            rag_config=mock_rag_config,
            concurrency=2,
            batch_size=5,
        )

    def test_stage_returns_indexing(self, indexing_runner):
        assert indexing_runner.stage() == RagWorkflowStepNames.INDEXING

    def test_lock_key_property(self, indexing_runner):
        expected_key = f"rag:index:{indexing_runner.vector_store_config.id}"
        assert indexing_runner.lock_key == expected_key

    @pytest.mark.asyncio
    async def test_collect_records_with_document_ids_filters_documents(
        self, indexing_runner
    ):
        # Setup mock documents with specific IDs and complete pipeline data
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_extraction1 = MagicMock(spec=Extraction)
        mock_extraction1.extractor_config_id = "extractor-123"
        mock_extraction1.created_at = datetime(2023, 1, 1)

        mock_chunked_doc1 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc1.chunker_config_id = "chunker-123"
        mock_chunked_doc1.created_at = datetime(2023, 1, 1)

        mock_chunk_embeddings1 = MagicMock()
        mock_chunk_embeddings1.embedding_config_id = "embedding-123"
        mock_chunk_embeddings1.created_at = datetime(2023, 1, 1)
        mock_chunked_doc1.chunk_embeddings.return_value = [mock_chunk_embeddings1]

        mock_extraction1.chunked_documents.return_value = [mock_chunked_doc1]
        mock_doc1.extractions.return_value = [mock_extraction1]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_extraction2 = MagicMock(spec=Extraction)
        mock_extraction2.extractor_config_id = "extractor-123"
        mock_extraction2.created_at = datetime(2023, 1, 2)

        mock_chunked_doc2 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc2.chunker_config_id = "chunker-123"
        mock_chunked_doc2.created_at = datetime(2023, 1, 2)

        mock_chunk_embeddings2 = MagicMock()
        mock_chunk_embeddings2.embedding_config_id = "embedding-123"
        mock_chunk_embeddings2.created_at = datetime(2023, 1, 2)
        mock_chunked_doc2.chunk_embeddings.return_value = [mock_chunk_embeddings2]

        mock_extraction2.chunked_documents.return_value = [mock_chunked_doc2]
        mock_doc2.extractions.return_value = [mock_extraction2]

        mock_doc3 = MagicMock(spec=Document)
        mock_doc3.id = "doc-3"
        mock_extraction3 = MagicMock(spec=Extraction)
        mock_extraction3.extractor_config_id = "extractor-123"
        mock_extraction3.created_at = datetime(2023, 1, 3)

        mock_chunked_doc3 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc3.chunker_config_id = "chunker-123"
        mock_chunked_doc3.created_at = datetime(2023, 1, 3)

        mock_chunk_embeddings3 = MagicMock()
        mock_chunk_embeddings3.embedding_config_id = "embedding-123"
        mock_chunk_embeddings3.created_at = datetime(2023, 1, 3)
        mock_chunked_doc3.chunk_embeddings.return_value = [mock_chunk_embeddings3]

        mock_extraction3.chunked_documents.return_value = [mock_chunked_doc3]
        mock_doc3.extractions.return_value = [mock_extraction3]

        indexing_runner.project.documents.return_value = [
            mock_doc1,
            mock_doc2,
            mock_doc3,
        ]

        # Collect records for doc-1 and doc-3 only
        collected_records = []
        async for records in indexing_runner.collect_records(
            batch_size=10, document_ids=["doc-1", "doc-3"]
        ):
            collected_records.extend(records)

        # Should only have records for doc-1 and doc-3
        assert len(collected_records) == 2
        record_doc_ids = {record.document_id for record in collected_records}
        assert record_doc_ids == {"doc-1", "doc-3"}

    @pytest.mark.asyncio
    async def test_collect_records_with_empty_document_ids_processes_all_documents(
        self, indexing_runner
    ):
        # Setup mock documents
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_extraction1 = MagicMock(spec=Extraction)
        mock_extraction1.extractor_config_id = "extractor-123"
        mock_extraction1.created_at = datetime(2023, 1, 1)

        mock_chunked_doc1 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc1.chunker_config_id = "chunker-123"
        mock_chunked_doc1.created_at = datetime(2023, 1, 1)

        mock_chunk_embeddings1 = MagicMock()
        mock_chunk_embeddings1.embedding_config_id = "embedding-123"
        mock_chunk_embeddings1.created_at = datetime(2023, 1, 1)
        mock_chunked_doc1.chunk_embeddings.return_value = [mock_chunk_embeddings1]

        mock_extraction1.chunked_documents.return_value = [mock_chunked_doc1]
        mock_doc1.extractions.return_value = [mock_extraction1]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_extraction2 = MagicMock(spec=Extraction)
        mock_extraction2.extractor_config_id = "extractor-123"
        mock_extraction2.created_at = datetime(2023, 1, 2)

        mock_chunked_doc2 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc2.chunker_config_id = "chunker-123"
        mock_chunked_doc2.created_at = datetime(2023, 1, 2)

        mock_chunk_embeddings2 = MagicMock()
        mock_chunk_embeddings2.embedding_config_id = "embedding-123"
        mock_chunk_embeddings2.created_at = datetime(2023, 1, 2)
        mock_chunked_doc2.chunk_embeddings.return_value = [mock_chunk_embeddings2]

        mock_extraction2.chunked_documents.return_value = [mock_chunked_doc2]
        mock_doc2.extractions.return_value = [mock_extraction2]

        indexing_runner.project.documents.return_value = [mock_doc1, mock_doc2]

        # Empty list should behave like None
        records_empty = []
        async for records in indexing_runner.collect_records(
            batch_size=10, document_ids=[]
        ):
            records_empty.extend(records)

        records_none = []
        async for records in indexing_runner.collect_records(
            batch_size=10, document_ids=None
        ):
            records_none.extend(records)

        # Both should process all documents
        assert len(records_empty) == 2
        assert len(records_none) == 2

        # Should have same document IDs
        empty_doc_ids = {record.document_id for record in records_empty}
        none_doc_ids = {record.document_id for record in records_none}
        assert empty_doc_ids == none_doc_ids == {"doc-1", "doc-2"}

    @pytest.mark.asyncio
    async def test_count_total_chunks(self, indexing_runner):
        # Setup mock documents with chunked documents
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "doc-1"
        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.extractor_config_id = "extractor-123"
        mock_extraction.created_at = datetime(2023, 1, 1)

        mock_chunked_doc = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_chunked_doc.created_at = datetime(2023, 1, 1)
        mock_chunked_doc.chunks = [MagicMock(), MagicMock(), MagicMock()]  # 3 chunks

        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunk_embeddings.created_at = datetime(2023, 1, 1)
        mock_chunked_doc.chunk_embeddings.return_value = [mock_chunk_embeddings]

        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]
        mock_doc.extractions.return_value = [mock_extraction]

        indexing_runner.project.documents.return_value = [mock_doc]

        total_chunks = await indexing_runner.count_total_chunks()
        assert total_chunks == 3

    @pytest.mark.asyncio
    async def test_run_vector_dimensions_inference(self, indexing_runner):
        # Setup mock documents with embeddings
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "doc-1"
        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.extractor_config_id = "extractor-123"
        mock_extraction.created_at = datetime(2023, 1, 1)

        mock_chunked_doc = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_chunked_doc.created_at = datetime(2023, 1, 1)
        mock_chunked_doc.chunks = [MagicMock()]

        # Mock embeddings with specific vector dimensions
        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3, 0.4, 0.5]  # 5 dimensions
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunk_embeddings.embeddings = [mock_embedding]
        mock_chunked_doc.chunk_embeddings.return_value = [mock_chunk_embeddings]

        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]
        mock_doc.extractions.return_value = [mock_extraction]

        indexing_runner.project.documents.return_value = [mock_doc]

        with (
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
            patch(
                "kiln_ai.adapters.rag.rag_runners.vector_store_adapter_for_config",
                new_callable=AsyncMock,
            ) as mock_vector_store_factory,
        ):
            mock_vector_store = MagicMock()
            mock_vector_store.add_chunks_with_embeddings = AsyncMock()
            mock_vector_store.delete_nodes_not_in_set = AsyncMock()
            mock_vector_store_factory.return_value = mock_vector_store

            progress_values = []
            async for progress in indexing_runner.run():
                progress_values.append(progress)

            # Should create vector store and process records
            mock_vector_store_factory.assert_called_once_with(
                indexing_runner.rag_config, indexing_runner.vector_store_config
            )
            assert len(progress_values) >= 2  # Initial progress + at least one batch

    @pytest.mark.asyncio
    async def test_run_successful_indexing_flow(self, indexing_runner):
        # Setup mock documents with embeddings
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "doc-1"
        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.extractor_config_id = "extractor-123"
        mock_extraction.created_at = datetime(2023, 1, 1)

        mock_chunked_doc = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_chunked_doc.created_at = datetime(2023, 1, 1)
        mock_chunked_doc.chunks = [MagicMock(), MagicMock()]  # 2 chunks

        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]  # 3 dimensions
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunk_embeddings.embeddings = [mock_embedding]
        mock_chunked_doc.chunk_embeddings.return_value = [mock_chunk_embeddings]

        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]
        mock_doc.extractions.return_value = [mock_extraction]

        indexing_runner.project.documents.return_value = [mock_doc]

        with (
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
            patch(
                "kiln_ai.adapters.rag.rag_runners.vector_store_adapter_for_config",
                new_callable=AsyncMock,
            ) as mock_vector_store_factory,
        ):
            mock_vector_store = MagicMock()
            mock_vector_store.add_chunks_with_embeddings = AsyncMock()
            mock_vector_store.delete_nodes_not_in_set = AsyncMock()
            mock_vector_store_factory.return_value = mock_vector_store

            progress_values = []
            async for progress in indexing_runner.run():
                progress_values.append(progress)

            # Should yield initial progress and success progress
            assert len(progress_values) >= 2
            # Initial progress should have 0 counts
            assert progress_values[0].success_count == 0
            assert progress_values[0].error_count == 0
            # Should have at least one success progress
            success_progress = [
                p for p in progress_values if p.success_count and p.success_count > 0
            ]
            assert len(success_progress) >= 1
            assert success_progress[0].success_count == 2  # 2 chunks

    @pytest.mark.asyncio
    async def test_run_error_handling_during_indexing(self, indexing_runner):
        # Setup mock documents with embeddings
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "doc-1"
        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.extractor_config_id = "extractor-123"
        mock_extraction.created_at = datetime(2023, 1, 1)

        mock_chunked_doc = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_chunked_doc.created_at = datetime(2023, 1, 1)
        mock_chunked_doc.chunks = [MagicMock(), MagicMock()]  # 2 chunks

        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]  # 3 dimensions
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunk_embeddings.embeddings = [mock_embedding]
        mock_chunked_doc.chunk_embeddings.return_value = [mock_chunk_embeddings]

        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]
        mock_doc.extractions.return_value = [mock_extraction]

        indexing_runner.project.documents.return_value = [mock_doc]

        with (
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
            patch(
                "kiln_ai.adapters.rag.rag_runners.vector_store_adapter_for_config",
                new_callable=AsyncMock,
            ) as mock_vector_store_factory,
        ):
            mock_vector_store = MagicMock()
            # Make the vector store raise an exception
            mock_vector_store.add_chunks_with_embeddings = AsyncMock(
                side_effect=Exception("Vector store error")
            )
            mock_vector_store.delete_nodes_not_in_set = AsyncMock()
            mock_vector_store_factory.return_value = mock_vector_store

            progress_values = []
            async for progress in indexing_runner.run():
                progress_values.append(progress)

            # Should yield initial progress and error progress
            assert len(progress_values) >= 2
            # Should have error progress with logs
            error_progress = [
                p for p in progress_values if p.error_count and p.error_count > 0
            ]
            assert len(error_progress) >= 1
            assert error_progress[0].error_count == 2  # 2 chunks failed
            assert len(error_progress[0].logs) > 0
            assert "error" in error_progress[0].logs[0].level.lower()
            assert "Vector store error" in error_progress[0].logs[0].message

    @pytest.mark.asyncio
    async def test_run_calls_delete_nodes_not_in_set_with_all_documents_no_tags(
        self, indexing_runner
    ):
        """Test that delete_nodes_not_in_set is called with all document IDs when no tags are configured"""
        # Setup mock documents
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_doc1.tags = ["tag1", "tag2"]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_doc2.tags = ["tag3"]

        mock_doc3 = MagicMock(spec=Document)
        mock_doc3.id = "doc-3"
        mock_doc3.tags = None

        all_docs = [mock_doc1, mock_doc2, mock_doc3]

        # Setup complete pipeline data for one document to satisfy vector dimension inference
        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.extractor_config_id = "extractor-123"
        mock_extraction.created_at = datetime(2023, 1, 1)

        mock_chunked_doc = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_chunked_doc.created_at = datetime(2023, 1, 1)
        mock_chunked_doc.chunks = [MagicMock()]

        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunk_embeddings.embeddings = [mock_embedding]
        mock_chunked_doc.chunk_embeddings.return_value = [mock_chunk_embeddings]

        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]
        mock_doc1.extractions.return_value = [mock_extraction]
        mock_doc2.extractions.return_value = []
        mock_doc3.extractions.return_value = []

        indexing_runner.project.documents.return_value = all_docs

        # Configure no tags in rag_config
        indexing_runner.rag_config.tags = None

        with (
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
            patch(
                "kiln_ai.adapters.rag.rag_runners.vector_store_adapter_for_config",
                new_callable=AsyncMock,
            ) as mock_vector_store_factory,
        ):
            mock_vector_store = MagicMock()
            mock_vector_store.add_chunks_with_embeddings = AsyncMock()
            mock_vector_store.delete_nodes_not_in_set = AsyncMock()
            mock_vector_store_factory.return_value = mock_vector_store

            # Run the indexing
            async for _ in indexing_runner.run():
                pass

            # Verify delete_nodes_not_in_set was called with all document IDs
            mock_vector_store.delete_nodes_not_in_set.assert_called_once_with(
                {"doc-1", "doc-2", "doc-3"}
            )

    @pytest.mark.asyncio
    async def test_run_calls_delete_nodes_not_in_set_with_tagged_documents_only(
        self, indexing_runner
    ):
        """Test that delete_nodes_not_in_set is called with only tagged document IDs when tags are configured"""
        # Setup mock documents with different tags
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_doc1.tags = ["important", "data"]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_doc2.tags = ["important", "test"]

        mock_doc3 = MagicMock(spec=Document)
        mock_doc3.id = "doc-3"
        mock_doc3.tags = ["unrelated"]

        mock_doc4 = MagicMock(spec=Document)
        mock_doc4.id = "doc-4"
        mock_doc4.tags = None

        all_docs = [mock_doc1, mock_doc2, mock_doc3, mock_doc4]

        # Setup complete pipeline data for one document to satisfy vector dimension inference
        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.extractor_config_id = "extractor-123"
        mock_extraction.created_at = datetime(2023, 1, 1)

        mock_chunked_doc = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_chunked_doc.created_at = datetime(2023, 1, 1)
        mock_chunked_doc.chunks = [MagicMock()]

        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunk_embeddings.embeddings = [mock_embedding]
        mock_chunked_doc.chunk_embeddings.return_value = [mock_chunk_embeddings]

        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]
        mock_doc1.extractions.return_value = [mock_extraction]
        mock_doc2.extractions.return_value = []
        mock_doc3.extractions.return_value = []
        mock_doc4.extractions.return_value = []

        indexing_runner.project.documents.return_value = all_docs

        # Configure tags to filter only documents with "important" tag
        indexing_runner.rag_config.tags = ["important"]

        with (
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
            patch(
                "kiln_ai.adapters.rag.rag_runners.vector_store_adapter_for_config",
                new_callable=AsyncMock,
            ) as mock_vector_store_factory,
        ):
            mock_vector_store = MagicMock()
            mock_vector_store.add_chunks_with_embeddings = AsyncMock()
            mock_vector_store.delete_nodes_not_in_set = AsyncMock()
            mock_vector_store_factory.return_value = mock_vector_store

            # Run the indexing
            async for _ in indexing_runner.run():
                pass

            # Verify delete_nodes_not_in_set was called with only "important" tagged document IDs
            mock_vector_store.delete_nodes_not_in_set.assert_called_once_with(
                {"doc-1", "doc-2"}
            )

    @pytest.mark.asyncio
    async def test_run_raises_error_when_no_documents_match_tags(self, indexing_runner):
        """Test that run raises ValueError when no documents match the tag filter"""
        # Setup mock documents that don't match the configured tags
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_doc1.tags = ["tag1"]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_doc2.tags = ["tag2"]

        all_docs = [mock_doc1, mock_doc2]

        # Setup complete pipeline data for the documents but they won't match the tag filter
        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.extractor_config_id = "extractor-123"
        mock_extraction.created_at = datetime(2023, 1, 1)

        mock_chunked_doc = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_chunked_doc.created_at = datetime(2023, 1, 1)
        mock_chunked_doc.chunks = [MagicMock()]

        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunk_embeddings.embeddings = [mock_embedding]
        mock_chunked_doc.chunk_embeddings.return_value = [mock_chunk_embeddings]

        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]
        mock_doc1.extractions.return_value = [mock_extraction]
        mock_doc2.extractions.return_value = [mock_extraction]

        indexing_runner.project.documents.return_value = all_docs

        # Configure tags that don't match any documents
        indexing_runner.rag_config.tags = ["nonexistent_tag"]

        with (
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
            patch(
                "kiln_ai.adapters.rag.rag_runners.vector_store_adapter_for_config",
                new_callable=AsyncMock,
            ) as mock_vector_store_factory,
        ):
            mock_vector_store = MagicMock()
            mock_vector_store.add_chunks_with_embeddings = AsyncMock()
            mock_vector_store.delete_nodes_not_in_set = AsyncMock()
            mock_vector_store_factory.return_value = mock_vector_store

            # Should raise ValueError when no documents match the tag filter
            with pytest.raises(ValueError, match="Vector dimensions are not set"):
                async for _ in indexing_runner.run():
                    pass

            # Should not call vector store methods since it fails before that
            mock_vector_store_factory.assert_not_called()
            mock_vector_store.delete_nodes_not_in_set.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_calls_delete_nodes_not_in_set_with_multiple_tag_filters(
        self, indexing_runner
    ):
        """Test that delete_nodes_not_in_set is called with documents matching any of multiple tags"""
        # Setup mock documents with various tag combinations
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.id = "doc-1"
        mock_doc1.tags = ["important", "data"]

        mock_doc2 = MagicMock(spec=Document)
        mock_doc2.id = "doc-2"
        mock_doc2.tags = ["urgent", "test"]

        mock_doc3 = MagicMock(spec=Document)
        mock_doc3.id = "doc-3"
        mock_doc3.tags = ["archive"]

        mock_doc4 = MagicMock(spec=Document)
        mock_doc4.id = "doc-4"
        mock_doc4.tags = ["important", "urgent", "critical"]

        all_docs = [mock_doc1, mock_doc2, mock_doc3, mock_doc4]

        # Setup complete pipeline data for one document to satisfy vector dimension inference
        mock_extraction = MagicMock(spec=Extraction)
        mock_extraction.extractor_config_id = "extractor-123"
        mock_extraction.created_at = datetime(2023, 1, 1)

        mock_chunked_doc = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_chunked_doc.created_at = datetime(2023, 1, 1)
        mock_chunked_doc.chunks = [MagicMock()]

        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]
        mock_chunk_embeddings = MagicMock()
        mock_chunk_embeddings.embedding_config_id = "embedding-123"
        mock_chunk_embeddings.embeddings = [mock_embedding]
        mock_chunked_doc.chunk_embeddings.return_value = [mock_chunk_embeddings]

        mock_extraction.chunked_documents.return_value = [mock_chunked_doc]
        mock_doc1.extractions.return_value = [mock_extraction]
        mock_doc2.extractions.return_value = []
        mock_doc3.extractions.return_value = []
        mock_doc4.extractions.return_value = []

        indexing_runner.project.documents.return_value = all_docs

        # Configure multiple tags - should match doc-1 (important), doc-2 (urgent), and doc-4 (both)
        indexing_runner.rag_config.tags = ["important", "urgent"]

        with (
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
            patch(
                "kiln_ai.adapters.rag.rag_runners.vector_store_adapter_for_config",
                new_callable=AsyncMock,
            ) as mock_vector_store_factory,
        ):
            mock_vector_store = MagicMock()
            mock_vector_store.add_chunks_with_embeddings = AsyncMock()
            mock_vector_store.delete_nodes_not_in_set = AsyncMock()
            mock_vector_store_factory.return_value = mock_vector_store

            # Run the indexing
            async for _ in indexing_runner.run():
                pass

            # Verify delete_nodes_not_in_set was called with documents having "important" OR "urgent" tags
            mock_vector_store.delete_nodes_not_in_set.assert_called_once_with(
                {"doc-1", "doc-2", "doc-4"}
            )


# Tests for workflow runner
class TestRagWorkflowRunner:
    @pytest.fixture
    def mock_step_runner(self):
        runner = MagicMock(spec=RagExtractionStepRunner)
        runner.stage.return_value = RagWorkflowStepNames.EXTRACTING

        async def mock_run():
            yield RagStepRunnerProgress(success_count=1, error_count=0)
            yield RagStepRunnerProgress(success_count=2, error_count=0)

        runner.run.return_value = mock_run()
        return runner

    @pytest.fixture
    def workflow_config(
        self,
        mock_step_runner,
        real_rag_config,
        real_extractor_config,
        real_chunker_config,
        real_embedding_config,
    ):
        return RagWorkflowRunnerConfiguration(
            step_runners=[mock_step_runner],
            initial_progress=RagProgress(
                total_document_count=10,
                total_document_extracted_count=0,
                total_document_chunked_count=0,
                total_document_embedded_count=0,
                total_document_completed_count=0,
                total_document_extracted_error_count=0,
                total_document_chunked_error_count=0,
                total_document_embedded_error_count=0,
                logs=[],
            ),
            rag_config=real_rag_config,
            extractor_config=real_extractor_config,
            chunker_config=real_chunker_config,
            embedding_config=real_embedding_config,
        )

    @pytest.fixture
    def workflow_runner(self, mock_project, workflow_config):
        return RagWorkflowRunner(project=mock_project, configuration=workflow_config)

    def test_lock_key_generation(self, workflow_runner):
        expected_key = f"rag:run:{workflow_runner.configuration.rag_config.id}"
        assert workflow_runner.lock_key == expected_key

    def test_update_workflow_progress_extracting(self, workflow_runner):
        step_progress = RagStepRunnerProgress(success_count=5, error_count=2)

        result = workflow_runner.update_workflow_progress(
            RagWorkflowStepNames.EXTRACTING, step_progress
        )

        assert result.total_document_extracted_count == 5
        assert result.total_document_extracted_error_count == 2

    def test_update_workflow_progress_chunking(self, workflow_runner):
        step_progress = RagStepRunnerProgress(success_count=3, error_count=1)

        result = workflow_runner.update_workflow_progress(
            RagWorkflowStepNames.CHUNKING, step_progress
        )

        assert result.total_document_chunked_count == 3
        assert result.total_document_chunked_error_count == 1

    def test_update_workflow_progress_embedding(self, workflow_runner):
        step_progress = RagStepRunnerProgress(success_count=2, error_count=0)

        result = workflow_runner.update_workflow_progress(
            RagWorkflowStepNames.EMBEDDING, step_progress
        )

        assert result.total_document_embedded_count == 2
        assert result.total_document_embedded_error_count == 0

    def test_update_workflow_progress_indexing(self, workflow_runner):
        step_progress = RagStepRunnerProgress(success_count=10, error_count=2)

        result = workflow_runner.update_workflow_progress(
            RagWorkflowStepNames.INDEXING, step_progress
        )

        # For indexing, success_count is added (not max) because it's chunks, not documents
        assert result.total_chunks_indexed_count == 10
        assert result.total_chunks_indexed_error_count == 2

    def test_update_workflow_progress_indexing_accumulates_chunks(
        self, workflow_runner
    ):
        # First batch of chunks
        step_progress1 = RagStepRunnerProgress(success_count=5, error_count=0)
        result1 = workflow_runner.update_workflow_progress(
            RagWorkflowStepNames.INDEXING, step_progress1
        )
        assert result1.total_chunks_indexed_count == 5

        # Second batch of chunks - should accumulate
        step_progress2 = RagStepRunnerProgress(success_count=3, error_count=1)
        result2 = workflow_runner.update_workflow_progress(
            RagWorkflowStepNames.INDEXING, step_progress2
        )
        assert result2.total_chunks_indexed_count == 8  # 5 + 3
        assert result2.total_chunks_indexed_error_count == 1  # max(0, 1)

    def test_update_workflow_progress_unknown_step_raises_error(self, workflow_runner):
        step_progress = RagStepRunnerProgress(success_count=1, error_count=0)

        with pytest.raises(ValueError, match="Unhandled enum value"):
            workflow_runner.update_workflow_progress("unknown_step", step_progress)

    def test_update_workflow_progress_calculates_completed_count(self, workflow_runner):
        # Set different counts for each step
        workflow_runner.current_progress.total_document_extracted_count = 10
        workflow_runner.current_progress.total_document_chunked_count = 8
        workflow_runner.current_progress.total_document_embedded_count = 5
        workflow_runner.current_progress.total_chunks_indexed_count = 3

        step_progress = RagStepRunnerProgress(success_count=1, error_count=0)
        result = workflow_runner.update_workflow_progress(
            RagWorkflowStepNames.EXTRACTING, step_progress
        )

        # Completed count should be the minimum of all document-related step counts
        assert result.total_document_completed_count == 5

        # chunks are tracked separately (so we can compare them against the total chunk count
        # to determine completion)
        assert result.total_chunk_completed_count == 3

    @pytest.mark.asyncio
    async def test_run_yields_initial_progress_and_step_progress(self, workflow_runner):
        with patch("kiln_ai.utils.lock.shared_async_lock_manager"):
            progress_values = []
            async for progress in workflow_runner.run():
                progress_values.append(progress)

            # Should yield initial progress plus progress from step runner
            assert len(progress_values) >= 1
            # First progress should be initial progress
            assert progress_values[0] == workflow_runner.initial_progress

    @pytest.mark.asyncio
    async def test_run_with_stages_filter(self, workflow_runner):
        # Add another step runner for chunking
        chunking_runner = MagicMock(spec=RagChunkingStepRunner)
        chunking_runner.stage.return_value = RagWorkflowStepNames.CHUNKING

        async def mock_chunking_run():
            yield RagStepRunnerProgress(success_count=1, error_count=0)

        chunking_runner.run.return_value = mock_chunking_run()
        workflow_runner.step_runners.append(chunking_runner)

        with patch("kiln_ai.utils.lock.shared_async_lock_manager"):
            progress_values = []
            # Only run extracting stage
            async for progress in workflow_runner.run(
                stages_to_run=[RagWorkflowStepNames.EXTRACTING]
            ):
                progress_values.append(progress)

            # Should only execute the extracting runner, not the chunking runner
            chunking_runner.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_with_document_ids_passes_to_step_runners(self, workflow_runner):
        # Mock the step runner to capture the document_ids parameter
        mock_step_runner = workflow_runner.step_runners[0]

        async def mock_run_with_doc_ids(document_ids=None):
            # Store the document_ids for verification
            mock_run_with_doc_ids.called_with_document_ids = document_ids
            yield RagStepRunnerProgress(success_count=1, error_count=0)

        mock_step_runner.run = mock_run_with_doc_ids

        with patch("kiln_ai.utils.lock.shared_async_lock_manager"):
            # Run with specific document IDs
            async for _ in workflow_runner.run(document_ids=["doc-1", "doc-2"]):
                pass

            # Verify the document_ids were passed to the step runner
            assert mock_run_with_doc_ids.called_with_document_ids == ["doc-1", "doc-2"]

    @pytest.mark.asyncio
    async def test_run_with_empty_document_ids_passes_empty_list_to_step_runners(
        self, workflow_runner
    ):
        # Mock the step runner to capture the document_ids parameter
        mock_step_runner = workflow_runner.step_runners[0]

        async def mock_run_with_doc_ids(document_ids=None):
            # Store the document_ids for verification
            mock_run_with_doc_ids.called_with_document_ids = document_ids
            yield RagStepRunnerProgress(success_count=1, error_count=0)

        mock_step_runner.run = mock_run_with_doc_ids

        with patch("kiln_ai.utils.lock.shared_async_lock_manager"):
            # Run with empty document IDs list
            async for _ in workflow_runner.run(document_ids=[]):
                pass

            # Verify the empty list was passed to the step runner
            assert mock_run_with_doc_ids.called_with_document_ids == []

    @pytest.mark.asyncio
    async def test_run_calls_count_total_chunks_for_indexing_step(
        self, workflow_runner
    ):
        # Add an indexing step runner
        from kiln_ai.adapters.rag.rag_runners import RagIndexingStepRunner

        indexing_runner = MagicMock(spec=RagIndexingStepRunner)
        indexing_runner.stage.return_value = RagWorkflowStepNames.INDEXING
        indexing_runner.count_total_chunks = AsyncMock(return_value=42)

        async def mock_indexing_run():
            yield RagStepRunnerProgress(success_count=1, error_count=0)

        indexing_runner.run.return_value = mock_indexing_run()
        workflow_runner.step_runners.append(indexing_runner)

        with patch("kiln_ai.utils.lock.shared_async_lock_manager"):
            progress_values = []
            async for progress in workflow_runner.run():
                progress_values.append(progress)

            # Should call count_total_chunks for indexing step
            indexing_runner.count_total_chunks.assert_called_once()
            # Should set total_chunk_count in progress
            assert workflow_runner.current_progress.total_chunk_count == 42


class TestRagWorkflowRunnerConfiguration:
    def test_configuration_creation(
        self,
        real_rag_config,
        real_extractor_config,
        real_chunker_config,
        real_embedding_config,
    ):
        mock_step_runner = MagicMock(spec=RagExtractionStepRunner)

        config = RagWorkflowRunnerConfiguration(
            step_runners=[mock_step_runner],
            initial_progress=RagProgress(),
            rag_config=real_rag_config,
            extractor_config=real_extractor_config,
            chunker_config=real_chunker_config,
            embedding_config=real_embedding_config,
        )

        assert config.step_runners == [mock_step_runner]
        assert config.rag_config == real_rag_config
        assert config.extractor_config == real_extractor_config
        assert config.chunker_config == real_chunker_config
        assert config.embedding_config == real_embedding_config
        assert isinstance(config.initial_progress, RagProgress)

    def test_configuration_with_initial_progress(
        self,
        real_rag_config,
        real_extractor_config,
        real_chunker_config,
        real_embedding_config,
    ):
        mock_step_runner = MagicMock(spec=RagExtractionStepRunner)
        initial_progress = RagProgress(
            total_document_count=5,
            total_document_extracted_count=1,
            total_document_chunked_count=0,
            total_document_embedded_count=0,
            total_document_completed_count=0,
            total_document_extracted_error_count=0,
            total_document_chunked_error_count=0,
            total_document_embedded_error_count=0,
            logs=[],
        )

        config = RagWorkflowRunnerConfiguration(
            step_runners=[mock_step_runner],
            initial_progress=initial_progress,
            rag_config=real_rag_config,
            extractor_config=real_extractor_config,
            chunker_config=real_chunker_config,
            embedding_config=real_embedding_config,
        )

        assert config.initial_progress == initial_progress


# Integration tests
class TestRagWorkflowIntegration:
    """Integration tests that test multiple components working together"""

    @pytest.mark.asyncio
    async def test_end_to_end_extraction_workflow(
        self, mock_project, mock_extractor_config
    ):
        # Setup mock documents and project
        mock_doc1 = MagicMock(spec=Document)
        mock_doc1.path = Path("doc1.txt")
        mock_doc1.original_file = MagicMock()
        mock_doc1.original_file.attachment = MagicMock()
        mock_doc1.original_file.attachment.resolve_path.return_value = "doc1_path"
        mock_doc1.original_file.mime_type = "text/plain"
        mock_doc1.extractions.return_value = []

        mock_project.documents.return_value = [mock_doc1]

        # Create extraction runner
        runner = RagExtractionStepRunner(
            project=mock_project, extractor_config=mock_extractor_config, concurrency=1
        )

        # Mock the necessary adapters and dependencies
        with (
            patch(
                "kiln_ai.adapters.rag.rag_runners.extractor_adapter_from_type"
            ) as mock_adapter_factory,
            patch(
                "kiln_ai.adapters.rag.rag_runners.AsyncJobRunner"
            ) as mock_job_runner_class,
            patch("kiln_ai.utils.lock.shared_async_lock_manager"),
        ):
            # Setup mock extractor
            mock_extractor = MagicMock(spec=BaseExtractor)
            mock_adapter_factory.return_value = mock_extractor

            # Setup mock job runner
            mock_job_runner = MagicMock()
            mock_job_runner_class.return_value = mock_job_runner

            async def mock_runner_progress():
                yield MagicMock(complete=1)

            mock_job_runner.run.return_value = mock_runner_progress()

            # Run the extraction step
            progress_values = []
            async for progress in runner.run():
                progress_values.append(progress)

            # Verify that jobs were collected and runner was created
            mock_adapter_factory.assert_called_once_with(
                mock_extractor_config.extractor_type, mock_extractor_config
            )
            mock_job_runner_class.assert_called_once()
            assert len(progress_values) > 0


class TestRagStepRunnersWithTagFiltering:
    """Test RAG step runners with document tag filtering"""

    @pytest.mark.asyncio
    async def test_extraction_runner_with_tag_filter(
        self, mock_project, mock_extractor_config
    ):
        """Test RagExtractionStepRunner filters documents by tags"""
        # Create documents with different tags
        doc1 = MagicMock(spec=Document)
        doc1.id = "doc1"
        doc1.tags = ["python", "ml"]

        doc2 = MagicMock(spec=Document)
        doc2.id = "doc2"
        doc2.tags = ["javascript", "web"]

        doc3 = MagicMock(spec=Document)
        doc3.id = "doc3"
        doc3.tags = ["python", "backend"]

        doc4 = MagicMock(spec=Document)
        doc4.id = "doc4"
        doc4.tags = None  # No tags

        mock_project.documents.return_value = [doc1, doc2, doc3, doc4]

        # Mock that none of the documents have extractions yet
        for doc in [doc1, doc2, doc3, doc4]:
            doc.extractions.return_value = []

        # Create RAG config that filters for "python" tags
        rag_config = MagicMock(spec=RagConfig)
        rag_config.tags = ["python"]

        runner = RagExtractionStepRunner(
            mock_project, mock_extractor_config, concurrency=1, rag_config=rag_config
        )

        jobs = await runner.collect_jobs()

        # Should only create jobs for doc1 and doc3 (have "python" tag)
        assert len(jobs) == 2
        job_doc_ids = {job.doc.id for job in jobs}
        assert "doc1" in job_doc_ids
        assert "doc3" in job_doc_ids
        assert "doc2" not in job_doc_ids  # javascript tag
        assert "doc4" not in job_doc_ids  # no tags

    @pytest.mark.asyncio
    async def test_chunking_runner_with_tag_filter(
        self, mock_project, mock_extractor_config, mock_chunker_config
    ):
        """Test RagChunkingStepRunner filters documents by tags"""
        # Create documents with extractions and different tags
        doc1 = MagicMock(spec=Document)
        doc1.id = "doc1"
        doc1.tags = ["rust", "systems"]
        extraction1 = MagicMock(spec=Extraction)
        extraction1.extractor_config_id = mock_extractor_config.id
        extraction1.created_at = "2024-01-01"
        extraction1.chunked_documents.return_value = []  # No chunks yet
        doc1.extractions.return_value = [extraction1]

        doc2 = MagicMock(spec=Document)
        doc2.id = "doc2"
        doc2.tags = ["python", "ml"]
        extraction2 = MagicMock(spec=Extraction)
        extraction2.extractor_config_id = mock_extractor_config.id
        extraction2.created_at = "2024-01-02"
        extraction2.chunked_documents.return_value = []  # No chunks yet
        doc2.extractions.return_value = [extraction2]

        doc3 = MagicMock(spec=Document)
        doc3.id = "doc3"
        doc3.tags = ["rust", "performance"]
        extraction3 = MagicMock(spec=Extraction)
        extraction3.extractor_config_id = mock_extractor_config.id
        extraction3.created_at = "2024-01-03"
        extraction3.chunked_documents.return_value = []  # No chunks yet
        doc3.extractions.return_value = [extraction3]

        mock_project.documents.return_value = [doc1, doc2, doc3]

        # Create RAG config that filters for "rust" tags
        rag_config = MagicMock(spec=RagConfig)
        rag_config.tags = ["rust"]

        runner = RagChunkingStepRunner(
            mock_project,
            mock_extractor_config,
            mock_chunker_config,
            concurrency=1,
            rag_config=rag_config,
        )

        jobs = await runner.collect_jobs()

        # Should only create jobs for doc1 and doc3 (have "rust" tag)
        assert len(jobs) == 2
        job_extraction_docs = {job.extraction.extractor_config_id for job in jobs}
        assert all(doc_id == mock_extractor_config.id for doc_id in job_extraction_docs)

    @pytest.mark.asyncio
    async def test_embedding_runner_with_tag_filter(
        self,
        mock_project,
        mock_extractor_config,
        mock_chunker_config,
        mock_embedding_config,
    ):
        """Test RagEmbeddingStepRunner filters documents by tags"""
        # Create document with chunked documents and specific tags
        doc1 = MagicMock(spec=Document)
        doc1.id = "doc1"
        doc1.tags = ["go", "backend"]

        chunked_doc1 = MagicMock(spec=ChunkedDocument)
        chunked_doc1.chunker_config_id = mock_chunker_config.id
        chunked_doc1.created_at = "2024-01-01"
        chunked_doc1.chunk_embeddings.return_value = []  # No embeddings yet

        extraction1 = MagicMock(spec=Extraction)
        extraction1.extractor_config_id = mock_extractor_config.id
        extraction1.created_at = "2024-01-01"
        extraction1.chunked_documents.return_value = [chunked_doc1]
        doc1.extractions.return_value = [extraction1]

        # Document with different tags
        doc2 = MagicMock(spec=Document)
        doc2.id = "doc2"
        doc2.tags = ["python", "web"]

        chunked_doc2 = MagicMock(spec=ChunkedDocument)
        chunked_doc2.chunker_config_id = mock_chunker_config.id
        chunked_doc2.created_at = "2024-01-02"
        chunked_doc2.chunk_embeddings.return_value = []  # No embeddings yet

        extraction2 = MagicMock(spec=Extraction)
        extraction2.extractor_config_id = mock_extractor_config.id
        extraction2.created_at = "2024-01-02"
        extraction2.chunked_documents.return_value = [chunked_doc2]
        doc2.extractions.return_value = [extraction2]

        mock_project.documents.return_value = [doc1, doc2]

        # Create RAG config that filters for "go" tags
        rag_config = MagicMock(spec=RagConfig)
        rag_config.tags = ["go"]

        runner = RagEmbeddingStepRunner(
            mock_project,
            mock_extractor_config,
            mock_chunker_config,
            mock_embedding_config,
            concurrency=1,
            rag_config=rag_config,
        )

        jobs = await runner.collect_jobs()

        # Should only create job for doc1 (has "go" tag)
        assert len(jobs) == 1
        assert jobs[0].chunked_document == chunked_doc1

    @pytest.mark.asyncio
    async def test_indexing_runner_collect_records_with_tag_filter(
        self,
        mock_project,
        mock_extractor_config,
        mock_chunker_config,
        mock_embedding_config,
    ):
        """Test RagIndexingStepRunner filters documents by tags"""
        # Create document with full pipeline and specific tags
        doc1 = MagicMock(spec=Document)
        doc1.id = "doc1"
        doc1.tags = ["typescript", "frontend"]

        chunk_embedding1 = MagicMock()
        chunk_embedding1.embedding_config_id = mock_embedding_config.id
        chunk_embedding1.created_at = "2024-01-01"

        chunked_doc1 = MagicMock(spec=ChunkedDocument)
        chunked_doc1.chunker_config_id = mock_chunker_config.id
        chunked_doc1.created_at = "2024-01-01"
        chunked_doc1.chunk_embeddings.return_value = [chunk_embedding1]

        extraction1 = MagicMock(spec=Extraction)
        extraction1.extractor_config_id = mock_extractor_config.id
        extraction1.created_at = "2024-01-01"
        extraction1.chunked_documents.return_value = [chunked_doc1]
        doc1.extractions.return_value = [extraction1]

        # Document with different tags
        doc2 = MagicMock(spec=Document)
        doc2.id = "doc2"
        doc2.tags = ["java", "enterprise"]

        chunk_embedding2 = MagicMock()
        chunk_embedding2.embedding_config_id = mock_embedding_config.id
        chunk_embedding2.created_at = "2024-01-02"

        chunked_doc2 = MagicMock(spec=ChunkedDocument)
        chunked_doc2.chunker_config_id = mock_chunker_config.id
        chunked_doc2.created_at = "2024-01-02"
        chunked_doc2.chunk_embeddings.return_value = [chunk_embedding2]

        extraction2 = MagicMock(spec=Extraction)
        extraction2.extractor_config_id = mock_extractor_config.id
        extraction2.created_at = "2024-01-02"
        extraction2.chunked_documents.return_value = [chunked_doc2]
        doc2.extractions.return_value = [extraction2]

        mock_project.documents.return_value = [doc1, doc2]

        # Create RAG config that filters for "typescript" tags
        rag_config = MagicMock(spec=RagConfig)
        rag_config.tags = ["typescript"]

        # Create mock vector store config
        mock_vector_store_config = MagicMock()
        mock_vector_store_config.id = "vector-store-123"

        runner = RagIndexingStepRunner(
            mock_project,
            mock_extractor_config,
            mock_chunker_config,
            mock_embedding_config,
            mock_vector_store_config,
            rag_config,
        )

        records = []
        async for record_batch in runner.collect_records(batch_size=10):
            records.extend(record_batch)

        # Should only collect records for doc1 (has "typescript" tag)
        assert len(records) == 1
        assert records[0].document_id == "doc1"

    @pytest.mark.asyncio
    async def test_step_runners_with_no_tag_filter(
        self, mock_project, mock_extractor_config
    ):
        """Test that step runners work normally when rag_config has no tags"""
        # Create documents with various tags
        doc1 = MagicMock(spec=Document)
        doc1.id = "doc1"
        doc1.tags = ["python", "ml"]
        doc1.extractions.return_value = []

        doc2 = MagicMock(spec=Document)
        doc2.id = "doc2"
        doc2.tags = ["javascript", "web"]
        doc2.extractions.return_value = []

        mock_project.documents.return_value = [doc1, doc2]

        # Create RAG config with no tag filter
        rag_config = MagicMock(spec=RagConfig)
        rag_config.tags = None

        runner = RagExtractionStepRunner(
            mock_project, mock_extractor_config, concurrency=1, rag_config=rag_config
        )

        jobs = await runner.collect_jobs()

        # Should create jobs for all documents
        assert len(jobs) == 2
        job_doc_ids = {job.doc.id for job in jobs}
        assert "doc1" in job_doc_ids
        assert "doc2" in job_doc_ids

    @pytest.mark.asyncio
    async def test_step_runners_with_empty_tag_filter(
        self, mock_project, mock_extractor_config
    ):
        """Test that step runners work normally when rag_config has empty tags list"""
        # Create documents with various tags
        doc1 = MagicMock(spec=Document)
        doc1.id = "doc1"
        doc1.tags = ["python", "ml"]
        doc1.extractions.return_value = []

        doc2 = MagicMock(spec=Document)
        doc2.id = "doc2"
        doc2.tags = ["javascript", "web"]
        doc2.extractions.return_value = []

        mock_project.documents.return_value = [doc1, doc2]

        # Create RAG config with empty tag filter
        rag_config = MagicMock(spec=RagConfig)
        rag_config.tags = []

        runner = RagExtractionStepRunner(
            mock_project, mock_extractor_config, concurrency=1, rag_config=rag_config
        )

        jobs = await runner.collect_jobs()

        # Should create jobs for all documents
        assert len(jobs) == 2
        job_doc_ids = {job.doc.id for job in jobs}
        assert "doc1" in job_doc_ids
        assert "doc2" in job_doc_ids
