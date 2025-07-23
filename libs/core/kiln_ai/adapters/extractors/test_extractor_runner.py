from unittest.mock import AsyncMock

import pytest

from conftest import MockFileFactoryMimeType
from kiln_ai.adapters.extractors.extractor_runner import ExtractorRunner
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
        output=KilnAttachmentModel.from_data(
            "test extraction output", "text/plain", ".txt"
        ),
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
        output=KilnAttachmentModel.from_data(
            "test extraction output", "text/plain", ".txt"
        ),
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
