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
        properties={},
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
        mock_extraction1.chunked_documents.return_value = []

        # Extraction with matching extractor config and existing chunks
        mock_extraction2 = MagicMock(spec=Extraction)
        mock_extraction2.extractor_config_id = "extractor-123"
        mock_chunked_doc = MagicMock()
        mock_chunked_doc.chunker_config_id = "chunker-123"
        mock_extraction2.chunked_documents.return_value = [mock_chunked_doc]

        # Extraction with different extractor config
        mock_extraction3 = MagicMock(spec=Extraction)
        mock_extraction3.extractor_config_id = "different-extractor"
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

        # Chunked document with matching chunker config but no embeddings
        mock_chunked_doc1 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc1.chunker_config_id = "chunker-123"
        mock_chunked_doc1.chunk_embeddings.return_value = []

        # Chunked document with matching chunker config and existing embeddings
        mock_chunked_doc2 = MagicMock(spec=ChunkedDocument)
        mock_chunked_doc2.chunker_config_id = "chunker-123"
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
