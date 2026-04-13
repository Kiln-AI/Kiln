from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import MockFileFactoryMimeType
from kiln_ai.adapters.extractors.base_extractor import BaseExtractor, ExtractionOutput
from kiln_ai.adapters.extractors.extractor_runner import ExtractorJob, ExtractorRunner
from kiln_ai.datamodel.basemodel import KilnAttachmentModel
from kiln_ai.datamodel.extraction import (
    Document,
    Extraction,
    ExtractionSource,
    ExtractorConfig,
    ExtractorType,
    FileInfo,
    Kind,
    OutputFormat,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.utils.git_sync_protocols import default_save_context


@pytest.fixture
def mock_project(tmp_path):
    project = Project(
        name="test",
        description="test",
        path=tmp_path / "project.kiln",
    )
    project.save_to_file()
    return project


@pytest.fixture
def mock_extractor_config(mock_project):
    extractor_config = ExtractorConfig(
        name="test",
        description="test",
        output_format=OutputFormat.TEXT,
        passthrough_mimetypes=[],
        extractor_type=ExtractorType.LITELLM,
        model_provider_name="gemini_api",
        model_name="gemini-2.0-flash",
        parent=mock_project,
        properties={
            "extractor_type": ExtractorType.LITELLM,
            "prompt_document": "Extract the text from the document",
            "prompt_image": "Extract the text from the image",
            "prompt_video": "Extract the text from the video",
            "prompt_audio": "Extract the text from the audio",
        },
    )
    extractor_config.save_to_file()
    return extractor_config


@pytest.fixture
def mock_document(mock_project, mock_file_factory) -> Document:
    test_pdf_file = mock_file_factory(MockFileFactoryMimeType.PDF)
    document = Document(
        name="test",
        description="test",
        kind=Kind.DOCUMENT,
        original_file=FileInfo(
            filename="test.pdf",
            size=100,
            mime_type="application/pdf",
            attachment=KilnAttachmentModel.from_file(test_pdf_file),
        ),
        parent=mock_project,
    )
    document.save_to_file()
    return document


@pytest.fixture
def mock_extractor_runner(mock_extractor_config, mock_document):
    return ExtractorRunner(
        extractor_configs=[mock_extractor_config],
        documents=[mock_document],
    )


# Test with and without concurrency
@pytest.mark.parametrize("concurrency", [1, 25])
@pytest.mark.asyncio
async def test_async_extractor_runner_status_updates(
    mock_extractor_runner, concurrency
):
    # Real async testing!

    job_count = 50
    # Job objects are not the right type, but since we're mocking run_job, it doesn't matter
    jobs = [{} for _ in range(job_count)]

    # Mock collect_tasks to return our fake jobs
    mock_extractor_runner.collect_jobs = lambda: jobs

    # Mock run_job to return True immediately
    mock_extractor_runner.run_job = AsyncMock(return_value=True)

    # Expect the status updates in order, and 1 for each job
    expected_completed_count = 0
    async for progress in mock_extractor_runner.run(concurrency=concurrency):
        assert progress.complete == expected_completed_count
        expected_completed_count += 1
        assert progress.errors == 0
        assert progress.total == job_count

    # Verify last status update was complete
    assert expected_completed_count == job_count + 1

    # Verify run_job was called for each job
    assert mock_extractor_runner.run_job.call_count == job_count


def test_collect_jobs_excludes_already_run_extraction(
    mock_extractor_runner, mock_document, mock_extractor_config
):
    """Test that already run documents are excluded"""
    Extraction(
        parent=mock_document,
        source=ExtractionSource.PROCESSED,
        extractor_config_id="other-extractor-config-id",
        output=KilnAttachmentModel.from_data("test extraction output", "text/plain"),
    ).save_to_file()

    # should get the one job, since the document was not already extracted with this extractor config
    jobs = mock_extractor_runner.collect_jobs()
    assert len(jobs) == 1
    assert jobs[0].doc.id == mock_document.id
    assert jobs[0].extractor_config.id == mock_extractor_config.id

    # Create an extraction for this document
    Extraction(
        parent=mock_document,
        source=ExtractionSource.PROCESSED,
        extractor_config_id=mock_extractor_config.id,
        output=KilnAttachmentModel.from_data("test extraction output", "text/plain"),
    ).save_to_file()

    jobs = mock_extractor_runner.collect_jobs()

    # should now get no jobs since the document was already extracted with this extractor config
    assert len(jobs) == 0


def test_collect_jobs_multiple_extractor_configs(
    mock_extractor_runner,
    mock_document,
    mock_extractor_config,
    mock_project,
):
    """Test handling multiple extractor configs"""
    second_config = ExtractorConfig(
        name="test2",
        description="test2",
        output_format=OutputFormat.TEXT,
        passthrough_mimetypes=[],
        extractor_type=ExtractorType.LITELLM,
        parent=mock_project,
        model_provider_name="gemini_api",
        model_name="gemini-2.0-flash",
        properties={
            "extractor_type": ExtractorType.LITELLM,
            "prompt_document": "Extract the text from the document",
            "prompt_image": "Extract the text from the image",
            "prompt_video": "Extract the text from the video",
            "prompt_audio": "Extract the text from the audio",
        },
    )
    second_config.save_to_file()

    runner = ExtractorRunner(
        extractor_configs=[mock_extractor_config, second_config],
        documents=[mock_document],
    )
    jobs = runner.collect_jobs()

    # Should get 2 jobs, one for each config
    assert len(jobs) == 2
    assert {job.extractor_config.id for job in jobs} == {
        second_config.id,
        mock_extractor_config.id,
    }


class _RecordingSaveContext:
    """Records enter/exit events and exception info for assertion in tests."""

    def __init__(self):
        self.enter_count = 0
        self.exit_count = 0
        self.last_exit_exc_type: type | None = None
        self.last_save_called_before_exit: bool | None = None

    def __call__(self):
        @asynccontextmanager
        async def cm() -> AsyncIterator[None]:
            self.enter_count += 1
            try:
                yield
            except BaseException as exc:
                self.last_exit_exc_type = type(exc)
                self.exit_count += 1
                raise
            else:
                self.exit_count += 1

        return cm()


def test_extractor_runner_defaults_to_default_save_context(
    mock_extractor_config, mock_document
):
    runner = ExtractorRunner(
        documents=[mock_document],
        extractor_configs=[mock_extractor_config],
    )
    assert runner._save_context is default_save_context


def test_extractor_runner_accepts_custom_save_context(
    mock_extractor_config, mock_document
):
    recorder = _RecordingSaveContext()
    runner = ExtractorRunner(
        documents=[mock_document],
        extractor_configs=[mock_extractor_config],
        save_context=recorder,
    )
    assert runner._save_context is recorder


def _make_extractor_job(mock_document, mock_extractor_config) -> ExtractorJob:
    return ExtractorJob(doc=mock_document, extractor_config=mock_extractor_config)


@pytest.mark.asyncio
async def test_run_job_default_save_context_saves_extraction(
    mock_extractor_runner, mock_document, mock_extractor_config
):
    fake_extractor = MagicMock(spec=BaseExtractor)
    fake_extractor.extract = AsyncMock(
        return_value=ExtractionOutput(
            content="hello world",
            content_format=OutputFormat.TEXT,
            is_passthrough=False,
        )
    )

    with (
        patch(
            "kiln_ai.adapters.extractors.extractor_runner.extractor_adapter_from_type",
            return_value=fake_extractor,
        ),
        patch(
            "kiln_ai.adapters.extractors.extractor_runner.Extraction"
        ) as mock_extraction_class,
    ):
        mock_extraction = MagicMock()
        mock_extraction_class.return_value = mock_extraction

        job = _make_extractor_job(mock_document, mock_extractor_config)
        result = await mock_extractor_runner.run_job(job)

    assert result is True
    mock_extraction.save_to_file.assert_called_once()


@pytest.mark.asyncio
async def test_run_job_custom_save_context_wraps_save(
    mock_extractor_config, mock_document
):
    recorder = _RecordingSaveContext()
    runner = ExtractorRunner(
        documents=[mock_document],
        extractor_configs=[mock_extractor_config],
        save_context=recorder,
    )

    fake_extractor = MagicMock(spec=BaseExtractor)
    fake_extractor.extract = AsyncMock(
        return_value=ExtractionOutput(
            content="hello world",
            content_format=OutputFormat.TEXT,
            is_passthrough=False,
        )
    )

    with (
        patch(
            "kiln_ai.adapters.extractors.extractor_runner.extractor_adapter_from_type",
            return_value=fake_extractor,
        ),
        patch(
            "kiln_ai.adapters.extractors.extractor_runner.Extraction"
        ) as mock_extraction_class,
    ):
        mock_extraction = MagicMock()

        def check_context_open_at_save(*args, **kwargs):
            # Assert the context was entered by the time save is called.
            assert recorder.enter_count == 1
            assert recorder.exit_count == 0

        mock_extraction.save_to_file.side_effect = check_context_open_at_save
        mock_extraction_class.return_value = mock_extraction

        job = _make_extractor_job(mock_document, mock_extractor_config)
        result = await runner.run_job(job)

    assert result is True
    assert recorder.enter_count == 1
    assert recorder.exit_count == 1
    assert recorder.last_exit_exc_type is None


@pytest.mark.asyncio
async def test_run_job_save_context_sees_save_exception(
    mock_extractor_config, mock_document
):
    recorder = _RecordingSaveContext()
    runner = ExtractorRunner(
        documents=[mock_document],
        extractor_configs=[mock_extractor_config],
        save_context=recorder,
    )

    fake_extractor = MagicMock(spec=BaseExtractor)
    fake_extractor.extract = AsyncMock(
        return_value=ExtractionOutput(
            content="hello world",
            content_format=OutputFormat.TEXT,
            is_passthrough=False,
        )
    )

    with (
        patch(
            "kiln_ai.adapters.extractors.extractor_runner.extractor_adapter_from_type",
            return_value=fake_extractor,
        ),
        patch(
            "kiln_ai.adapters.extractors.extractor_runner.Extraction"
        ) as mock_extraction_class,
    ):
        mock_extraction = MagicMock()
        mock_extraction.save_to_file.side_effect = RuntimeError("disk full")
        mock_extraction_class.return_value = mock_extraction

        job = _make_extractor_job(mock_document, mock_extractor_config)
        result = await runner.run_job(job)

    # The outer try/except swallows and returns False, but the save_context must
    # have seen the exception so it can roll back.
    assert result is False
    assert recorder.enter_count == 1
    assert recorder.exit_count == 1
    assert recorder.last_exit_exc_type is RuntimeError
