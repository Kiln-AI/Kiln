import time
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch

import openai
import pytest
from openai.types.fine_tuning import FineTuningJob

from kiln_ai.adapters.fine_tune.base_finetune import FineTuneStatusType
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat, DatasetFormatter
from kiln_ai.adapters.fine_tune.openai_finetune import OpenAIFinetune
from kiln_ai.datamodel import (
    DatasetSplit,
    FinetuneDataStrategy,
    StructuredOutputMode,
    Task,
)
from kiln_ai.datamodel import Finetune as FinetuneModel
from kiln_ai.datamodel.dataset_split import Train80Test20SplitDefinition
from kiln_ai.utils.config import Config


@pytest.fixture
def openai_finetune(tmp_path):
    tmp_file = tmp_path / "test-finetune.kiln"
    finetune = OpenAIFinetune(
        datamodel=FinetuneModel(
            name="test-finetune",
            provider="openai",
            provider_id="openai-123",
            base_model_id="gpt-4o",
            train_split_name="train",
            dataset_split_id="dataset-123",
            system_message="Test system message",
            fine_tune_model_id="ft-123",
            path=tmp_file,
            data_strategy=FinetuneDataStrategy.final_only,
        ),
    )
    return finetune


@pytest.fixture
def mock_response():
    response = MagicMock(spec=FineTuningJob)
    response.error = None
    response.status = "succeeded"
    response.finished_at = time.time()
    response.estimated_finish = None
    response.fine_tuned_model = "ft-123"
    response.model = "gpt-4o"
    return response


@pytest.fixture
def mock_dataset():
    return DatasetSplit(
        id="test-dataset-123",
        name="Test Dataset",
        splits=Train80Test20SplitDefinition,
        split_contents={"train": [], "test": []},
    )


@pytest.fixture
def mock_task():
    return Task(
        id="test-task-123",
        name="Test Task",
        output_json_schema=None,  # Can be modified in specific tests
        instruction="Test instruction",
    )


async def test_setup(openai_finetune):
    if not Config.shared().open_ai_api_key:
        pytest.skip("OpenAI API key not set")
    openai_finetune.provider_id = "openai-123"
    openai_finetune.provider = "openai"

    # Real API call, with fake ID
    status = await openai_finetune.status()
    # fake id fails
    assert status.status == FineTuneStatusType.unknown
    assert "Job with this ID not found. It may have been deleted." == status.message


@pytest.mark.parametrize(
    "exception,expected_status,expected_message",
    [
        (
            openai.APIConnectionError(request=MagicMock()),
            FineTuneStatusType.unknown,
            "Server connection error",
        ),
        (
            openai.RateLimitError(
                message="Rate limit exceeded", body={}, response=MagicMock()
            ),
            FineTuneStatusType.unknown,
            "Rate limit exceeded",
        ),
        (
            openai.APIStatusError(
                "Not found",
                response=MagicMock(status_code=404),
                body={},
            ),
            FineTuneStatusType.unknown,
            "Job with this ID not found",
        ),
        (
            openai.APIStatusError(
                "Server error",
                response=MagicMock(status_code=500),
                body={},
            ),
            FineTuneStatusType.unknown,
            "Unknown error",
        ),
    ],
)
async def test_status_api_errors(
    openai_finetune, exception, expected_status, expected_message
):
    with patch(
        "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.fine_tuning.jobs.retrieve",
        side_effect=exception,
    ):
        status = await openai_finetune.status()
        assert status.status == expected_status
        assert expected_message in status.message


@pytest.mark.parametrize(
    "job_status,expected_status,message_contains",
    [
        ("failed", FineTuneStatusType.failed, "Job failed"),
        ("cancelled", FineTuneStatusType.failed, "Job cancelled"),
        ("succeeded", FineTuneStatusType.completed, "Training job completed"),
        ("running", FineTuneStatusType.running, "Fine tune job is running"),
        ("queued", FineTuneStatusType.running, "Fine tune job is running"),
        (
            "validating_files",
            FineTuneStatusType.running,
            "Fine tune job is running",
        ),
        ("unknown_status", FineTuneStatusType.unknown, "Unknown status"),
    ],
)
async def test_status_job_states(
    openai_finetune,
    mock_response,
    job_status,
    expected_status,
    message_contains,
):
    mock_response.status = job_status

    with patch(
        "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.fine_tuning.jobs.retrieve",
        return_value=mock_response,
    ):
        status = await openai_finetune.status()
        assert status.status == expected_status
        assert message_contains in status.message


async def test_status_with_error_response(openai_finetune, mock_response):
    mock_response.error = MagicMock()
    mock_response.error.message = "Something went wrong"

    with patch(
        "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.fine_tuning.jobs.retrieve",
        return_value=mock_response,
    ):
        status = await openai_finetune.status()
        assert status.status == FineTuneStatusType.failed
        assert status.message.startswith("Something went wrong [Code:")


async def test_status_with_estimated_finish_time(openai_finetune, mock_response):
    current_time = time.time()
    mock_response.status = "running"
    mock_response.estimated_finish = current_time + 300  # 5 minutes from now

    with patch(
        "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.fine_tuning.jobs.retrieve",
        return_value=mock_response,
    ):
        status = await openai_finetune.status()
        assert status.status == FineTuneStatusType.running
        assert (
            "Estimated finish time: 299 seconds" in status.message
        )  # non zero time passes


async def test_status_empty_response(openai_finetune):
    with patch(
        "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.fine_tuning.jobs.retrieve",
        return_value=mock_response,
    ):
        status = await openai_finetune.status()
        assert status.status == FineTuneStatusType.unknown
        assert "Invalid response from OpenAI" in status.message


async def test_generate_and_upload_jsonl_success(
    openai_finetune, mock_dataset, mock_task
):
    mock_path = Path("mock_path.jsonl")
    mock_file_id = "file-123"

    # Mock the formatter
    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_formatter.dump_to_file.return_value = mock_path

    # Mock the file response
    mock_file_response = MagicMock()
    mock_file_response.id = mock_file_id

    with (
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.DatasetFormatter",
            return_value=mock_formatter,
        ) as mock_formatter_class,
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.files.create",
            return_value=mock_file_response,
        ) as mock_create,
        patch("builtins.open") as mock_open,
    ):
        result = await openai_finetune.generate_and_upload_jsonl(
            mock_dataset,
            "train",
            mock_task,
            DatasetFormat.OPENAI_CHAT_JSONL,
        )

        # Verify formatter was created with correct parameters
        mock_formatter_class.assert_called_once_with(
            mock_dataset, openai_finetune.datamodel.system_message, None
        )

        # Verify correct format was used
        mock_formatter.dump_to_file.assert_called_once_with(
            "train",
            DatasetFormat.OPENAI_CHAT_JSONL,
            FinetuneDataStrategy.final_only,
        )

        # Verify file was opened and uploaded
        mock_open.assert_called_once_with(mock_path, "rb")
        mock_create.assert_called_once()

        assert result == mock_file_id


async def test_generate_and_upload_jsonl_schema_success(
    openai_finetune, mock_dataset, mock_task
):
    mock_path = Path("mock_path.jsonl")
    mock_file_id = "file-123"
    mock_task.output_json_schema = '{"type": "object", "properties": {"key": {"type": "string"}}}'  # Add JSON schema

    # Mock the formatter
    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_formatter.dump_to_file.return_value = mock_path

    # Mock the file response
    mock_file_response = MagicMock()
    mock_file_response.id = mock_file_id

    with (
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.DatasetFormatter",
            return_value=mock_formatter,
        ) as mock_formatter_class,
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.files.create",
            return_value=mock_file_response,
        ) as mock_create,
        patch("builtins.open") as mock_open,
    ):
        result = await openai_finetune.generate_and_upload_jsonl(
            mock_dataset,
            "train",
            mock_task,
            DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL,
        )

        # Verify formatter was created with correct parameters
        mock_formatter_class.assert_called_once_with(
            mock_dataset, openai_finetune.datamodel.system_message, None
        )

        # Verify correct format was used
        mock_formatter.dump_to_file.assert_called_once_with(
            "train",
            DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL,
            FinetuneDataStrategy.final_only,
        )

        # Verify file was opened and uploaded
        mock_open.assert_called_once_with(mock_path, "rb")
        mock_create.assert_called_once()

        assert result == mock_file_id


async def test_generate_and_upload_jsonl_upload_failure(
    openai_finetune, mock_dataset, mock_task
):
    mock_path = Path("mock_path.jsonl")

    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_formatter.dump_to_file.return_value = mock_path

    # Mock response with no ID
    mock_file_response = MagicMock()
    mock_file_response.id = None

    with (
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.DatasetFormatter",
            return_value=mock_formatter,
        ),
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.files.create",
            return_value=mock_file_response,
        ),
        patch("builtins.open"),
    ):
        with pytest.raises(ValueError, match="Failed to upload file to OpenAI"):
            await openai_finetune.generate_and_upload_jsonl(
                mock_dataset, "train", mock_task, DatasetFormat.OPENAI_CHAT_JSONL
            )


async def test_generate_and_upload_jsonl_api_error(
    openai_finetune, mock_dataset, mock_task
):
    mock_path = Path("mock_path.jsonl")

    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_formatter.dump_to_file.return_value = mock_path

    with (
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.DatasetFormatter",
            return_value=mock_formatter,
        ),
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.files.create",
            side_effect=openai.APIError(
                message="API error", request=MagicMock(), body={}
            ),
        ),
        patch("builtins.open"),
    ):
        with pytest.raises(openai.APIError):
            await openai_finetune.generate_and_upload_jsonl(
                mock_dataset, "train", mock_task, DatasetFormat.OPENAI_CHAT_JSONL
            )


@pytest.mark.parametrize(
    "output_schema,expected_mode,expected_format",
    [
        (
            '{"type": "object", "properties": {"key": {"type": "string"}}}',
            StructuredOutputMode.json_schema,
            DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL,
        ),
        (None, None, DatasetFormat.OPENAI_CHAT_JSONL),
    ],
)
async def test_start_success(
    openai_finetune,
    mock_dataset,
    mock_task,
    output_schema,
    expected_mode,
    expected_format,
):
    openai_finetune.datamodel.parent = mock_task

    mock_task.output_json_schema = output_schema

    # Mock parameters
    openai_finetune.datamodel.parameters = {
        "n_epochs": 3,
        "learning_rate_multiplier": 0.1,
        "batch_size": 4,
        "ignored_param": "value",
    }

    # Mock the fine-tuning response
    mock_ft_response = MagicMock()
    mock_ft_response.id = "ft-123"
    mock_ft_response.fine_tuned_model = None
    mock_ft_response.model = "gpt-4o-mini-2024-07-18"

    with (
        patch.object(
            openai_finetune,
            "generate_and_upload_jsonl",
            side_effect=["train-file-123", "val-file-123"],
        ) as mock_upload,
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.fine_tuning.jobs.create",
            return_value=mock_ft_response,
        ) as mock_create,
    ):
        await openai_finetune._start(mock_dataset)

        # Verify file uploads
        assert mock_upload.call_count == 1  # Only training file
        mock_upload.assert_called_with(
            mock_dataset,
            openai_finetune.datamodel.train_split_name,
            mock_task,
            expected_format,
        )

        # Verify fine-tune creation
        mock_create.assert_called_once_with(
            training_file="train-file-123",
            model="gpt-4o",
            validation_file=None,
            seed=None,
            hyperparameters={
                "n_epochs": 3,
                "learning_rate_multiplier": 0.1,
                "batch_size": 4,
            },
            suffix=f"kiln_ai.{openai_finetune.datamodel.id}",
        )

        # Verify model updates
        assert openai_finetune.datamodel.provider_id == "ft-123"
        assert openai_finetune.datamodel.base_model_id == "gpt-4o-mini-2024-07-18"
        assert openai_finetune.datamodel.structured_output_mode == expected_mode


async def test_start_with_validation(openai_finetune, mock_dataset, mock_task):
    openai_finetune.datamodel.parent = mock_task
    openai_finetune.datamodel.validation_split_name = "validation"

    mock_ft_response = MagicMock()
    mock_ft_response.id = "ft-123"
    mock_ft_response.fine_tuned_model = None
    mock_ft_response.model = "gpt-4o-mini-2024-07-18"

    with (
        patch.object(
            openai_finetune,
            "generate_and_upload_jsonl",
            side_effect=["train-file-123", "val-file-123"],
        ) as mock_upload,
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.fine_tuning.jobs.create",
            return_value=mock_ft_response,
        ) as mock_create,
    ):
        await openai_finetune._start(mock_dataset)

        # Verify both files were uploaded
        assert mock_upload.call_count == 2
        mock_upload.assert_has_calls(
            [
                mock.call(
                    mock_dataset,
                    openai_finetune.datamodel.train_split_name,
                    mock_task,
                    DatasetFormat.OPENAI_CHAT_JSONL,
                ),
                mock.call(
                    mock_dataset,
                    "validation",
                    mock_task,
                    DatasetFormat.OPENAI_CHAT_JSONL,
                ),
            ]
        )

        # Verify validation file was included
        mock_create.assert_called_once()
        assert mock_create.call_args[1]["validation_file"] == "val-file-123"


async def test_start_no_task(openai_finetune, mock_dataset):
    openai_finetune.datamodel.parent = None
    openai_finetune.datamodel.path = None

    with pytest.raises(ValueError, match="Task is required to start a fine-tune"):
        await openai_finetune._start(mock_dataset)


async def test_status_updates_model_ids(openai_finetune, mock_response):
    # Set up initial model IDs
    openai_finetune.datamodel.fine_tune_model_id = "old-ft-model"
    openai_finetune.datamodel.base_model_id = "old-base-model"

    # Configure mock response with different model IDs
    mock_response.fine_tuned_model = "new-ft-model"
    mock_response.model = "new-base-model"
    mock_response.status = "succeeded"

    with (
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.fine_tuning.jobs.retrieve",
            return_value=mock_response,
        ),
    ):
        status = await openai_finetune.status()

        # Verify model IDs were updated
        assert openai_finetune.datamodel.fine_tune_model_id == "new-ft-model"
        assert openai_finetune.datamodel.base_model_id == "new-base-model"

        # Verify save was called
        # This isn't properly mocked, so not checking
        # assert openai_finetune.datamodel.save.called

        # Verify status is still returned correctly
        assert status.status == FineTuneStatusType.completed
        assert status.message == "Training job completed"


async def test_status_updates_latest_status(openai_finetune, mock_response):
    # Set initial status
    openai_finetune.datamodel.latest_status = FineTuneStatusType.running
    assert openai_finetune.datamodel.latest_status == FineTuneStatusType.running
    mock_response.status = "succeeded"

    with (
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.fine_tuning.jobs.retrieve",
            return_value=mock_response,
        ),
    ):
        status = await openai_finetune.status()

        # Verify status was updated in datamodel
        assert openai_finetune.datamodel.latest_status == FineTuneStatusType.completed
        assert status.status == FineTuneStatusType.completed
        assert status.message == "Training job completed"

        # Verify file was saved
        assert openai_finetune.datamodel.path.exists()


@pytest.mark.parametrize(
    "data_strategy,thinking_instructions",
    [
        (FinetuneDataStrategy.final_and_intermediate, "Custom thinking instructions"),
        (FinetuneDataStrategy.final_only, None),
    ],
)
async def test_generate_and_upload_jsonl_with_data_strategy(
    mock_dataset, mock_task, data_strategy, thinking_instructions, tmp_path
):
    mock_path = Path("mock_path.jsonl")
    mock_file_id = "file-123"

    openai_finetune = OpenAIFinetune(
        datamodel=FinetuneModel(
            name="test-finetune",
            provider="openai",
            provider_id="openai-123",
            base_model_id="gpt-4o",
            train_split_name="train",
            dataset_split_id="dataset-123",
            system_message="Test system message",
            fine_tune_model_id="ft-123",
            path=tmp_path / "test-finetune.kiln",
            data_strategy=data_strategy,
            thinking_instructions=thinking_instructions,
        ),
    )

    # Mock the formatter
    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_formatter.dump_to_file.return_value = mock_path

    # Mock the file response
    mock_file_response = MagicMock()
    mock_file_response.id = mock_file_id

    with (
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.DatasetFormatter",
            return_value=mock_formatter,
        ),
        patch(
            "kiln_ai.adapters.fine_tune.openai_finetune.oai_client.files.create",
            return_value=mock_file_response,
        ),
        patch("builtins.open"),
    ):
        result = await openai_finetune.generate_and_upload_jsonl(
            mock_dataset, "train", mock_task, DatasetFormat.OPENAI_CHAT_JSONL
        )

        # Verify formatter was created with correct parameters
        mock_formatter.dump_to_file.assert_called_once_with(
            "train",
            DatasetFormat.OPENAI_CHAT_JSONL,
            data_strategy,  # Verify data_strategy is passed through
        )

        assert result == mock_file_id
