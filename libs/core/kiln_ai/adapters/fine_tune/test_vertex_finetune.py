from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.cloud import storage
from google.cloud.aiplatform_v1beta1 import types as gca_types
from vertexai.tuning import sft

from kiln_ai.adapters.fine_tune.base_finetune import FineTuneStatusType
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat, DatasetFormatter
from kiln_ai.adapters.fine_tune.vertex_finetune import VertexFinetune
from kiln_ai.datamodel import DatasetSplit, StructuredOutputMode, Task
from kiln_ai.datamodel import Finetune as FinetuneModel
from kiln_ai.datamodel.datamodel_enums import ChatStrategy
from kiln_ai.datamodel.dataset_split import Train80Test20SplitDefinition
from kiln_ai.utils.config import Config


@pytest.fixture
def vertex_finetune(tmp_path):
    tmp_file = tmp_path / "test-finetune.kiln"
    finetune = VertexFinetune(
        datamodel=FinetuneModel(
            name="test-finetune",
            provider="vertex",
            provider_id="vertex-123",
            base_model_id="gemini-2.0-pro",
            train_split_name="train",
            dataset_split_id="dataset-123",
            system_message="Test system message",
            fine_tune_model_id="ft-123",
            path=tmp_file,
            data_strategy=ChatStrategy.single_turn,
        ),
    )
    return finetune


@pytest.fixture
def mock_response():
    # Mock SFT job response object
    response = MagicMock(spec=sft.SupervisedTuningJob)
    response.error = None
    response.state = gca_types.JobState.JOB_STATE_SUCCEEDED
    response.tuned_model_endpoint_name = "ft-123"
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


async def test_status_pending_no_provider_id(vertex_finetune):
    vertex_finetune.datamodel.provider_id = None

    status = await vertex_finetune.status()
    assert status.status == FineTuneStatusType.pending
    assert "This fine-tune has not been started" in status.message


@pytest.mark.parametrize(
    "state,expected_status,message_contains",
    [
        (
            gca_types.JobState.JOB_STATE_FAILED,
            FineTuneStatusType.failed,
            "Fine Tune Job Failed",
        ),
        (
            gca_types.JobState.JOB_STATE_EXPIRED,
            FineTuneStatusType.failed,
            "Fine Tune Job Failed",
        ),
        (
            gca_types.JobState.JOB_STATE_CANCELLED,
            FineTuneStatusType.failed,
            "Fine Tune Job Cancelled",
        ),
        (
            gca_types.JobState.JOB_STATE_CANCELLING,
            FineTuneStatusType.failed,
            "Fine Tune Job Cancelled",
        ),
        (
            gca_types.JobState.JOB_STATE_PENDING,
            FineTuneStatusType.pending,
            "Fine Tune Job Pending",
        ),
        (
            gca_types.JobState.JOB_STATE_QUEUED,
            FineTuneStatusType.pending,
            "Fine Tune Job Pending",
        ),
        (
            gca_types.JobState.JOB_STATE_RUNNING,
            FineTuneStatusType.running,
            "Fine Tune Job Running",
        ),
        (
            gca_types.JobState.JOB_STATE_SUCCEEDED,
            FineTuneStatusType.completed,
            "Fine Tune Job Completed",
        ),
        (
            gca_types.JobState.JOB_STATE_PARTIALLY_SUCCEEDED,
            FineTuneStatusType.completed,
            "Fine Tune Job Completed",
        ),
        (
            gca_types.JobState.JOB_STATE_PAUSED,
            FineTuneStatusType.unknown,
            "Unknown state",
        ),
        (
            gca_types.JobState.JOB_STATE_UPDATING,
            FineTuneStatusType.unknown,
            "Unknown state",
        ),
        (
            gca_types.JobState.JOB_STATE_UNSPECIFIED,
            FineTuneStatusType.unknown,
            "Unknown state",
        ),
        (999, FineTuneStatusType.unknown, "Unknown state"),  # Test unknown state
    ],
)
async def test_status_job_states(
    vertex_finetune,
    mock_response,
    state,
    expected_status,
    message_contains,
):
    mock_response.state = state

    with patch(
        "kiln_ai.adapters.fine_tune.vertex_finetune.sft.SupervisedTuningJob",
        return_value=mock_response,
    ):
        status = await vertex_finetune.status()
        assert status.status == expected_status
        assert message_contains in status.message


async def test_status_with_error(vertex_finetune, mock_response):
    # Set up error response
    mock_response.error = MagicMock()
    mock_response.error.code = 123
    mock_response.error.message = "Test error message"

    with patch(
        "kiln_ai.adapters.fine_tune.vertex_finetune.sft.SupervisedTuningJob",
        return_value=mock_response,
    ):
        status = await vertex_finetune.status()
        assert status.status == FineTuneStatusType.failed
        assert "Test error message [123]" in status.message


async def test_status_updates_model_id(vertex_finetune, mock_response):
    # Set initial fine-tuned model ID
    vertex_finetune.datamodel.fine_tune_model_id = "old-ft-model"

    # Set new model ID in response
    mock_response.tuned_model_endpoint_name = "new-ft-model"

    with patch(
        "kiln_ai.adapters.fine_tune.vertex_finetune.sft.SupervisedTuningJob",
        return_value=mock_response,
    ):
        status = await vertex_finetune.status()

        # Verify model ID was updated
        assert vertex_finetune.datamodel.fine_tune_model_id == "new-ft-model"

        # Verify status returned correctly
        assert status.status == FineTuneStatusType.completed
        assert status.message == "Fine Tune Job Completed"


async def test_status_updates_latest_status(vertex_finetune, mock_response):
    # Set initial status
    vertex_finetune.datamodel.latest_status = FineTuneStatusType.running

    # Set completed state in response
    mock_response.state = gca_types.JobState.JOB_STATE_SUCCEEDED

    with patch(
        "kiln_ai.adapters.fine_tune.vertex_finetune.sft.SupervisedTuningJob",
        return_value=mock_response,
    ):
        status = await vertex_finetune.status()

        # Verify status was updated in datamodel
        assert vertex_finetune.datamodel.latest_status == FineTuneStatusType.completed
        assert status.status == FineTuneStatusType.completed

        # Verify file was saved (since path exists)
        assert vertex_finetune.datamodel.path.exists()


async def test_status_model_id_update_exception(vertex_finetune, mock_response):
    # Set up response to raise an exception when accessing tuned_model_endpoint_name
    mock_response.tuned_model_endpoint_name = None

    # Create a property that raises an exception when accessed
    def raise_exception(self):
        raise Exception("Model ID error")

    type(mock_response).tuned_model_endpoint_name = property(raise_exception)

    with (
        patch(
            "kiln_ai.adapters.fine_tune.vertex_finetune.sft.SupervisedTuningJob",
            return_value=mock_response,
        ),
        patch("kiln_ai.adapters.fine_tune.vertex_finetune.logger") as mock_logger,
    ):
        status = await vertex_finetune.status()

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        assert (
            "Error updating fine-tune model ID" in mock_logger.warning.call_args[0][0]
        )

        # Status should still be returned even with the exception
        assert status.status == FineTuneStatusType.completed


@pytest.mark.parametrize(
    "data_strategy,thinking_instructions",
    [
        (ChatStrategy.two_message_cot, "Custom thinking instructions"),
        (ChatStrategy.single_turn, None),
    ],
)
async def test_generate_and_upload_jsonl(
    vertex_finetune,
    mock_dataset,
    mock_task,
    data_strategy,
    thinking_instructions,
    tmp_path,
):
    # Create finetune with specific data strategy and thinking instructions
    finetune = VertexFinetune(
        datamodel=FinetuneModel(
            name="test-finetune",
            provider="vertex",
            provider_id="vertex-123",
            base_model_id="gemini-2.0-pro",
            train_split_name="train",
            dataset_split_id="dataset-123",
            system_message="Test system message",
            path=tmp_path / "test-finetune.kiln",
            data_strategy=data_strategy,
            thinking_instructions=thinking_instructions,
        ),
    )

    mock_path = Path("mock_path.jsonl")
    expected_uri = "gs://kiln-ai-data/1234567890/mock_path.jsonl"

    # Mock the formatter
    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_formatter.dump_to_file.return_value = mock_path

    # Mock storage client and bucket operations
    mock_bucket = MagicMock()
    mock_bucket.name = "kiln-ai-data"

    mock_blob = MagicMock()
    mock_blob.name = f"1234567890/{mock_path.name}"

    mock_storage_client = MagicMock(spec=storage.Client)
    mock_storage_client.lookup_bucket.return_value = mock_bucket
    mock_storage_client.bucket.return_value = mock_bucket

    mock_bucket.blob.return_value = mock_blob

    with (
        patch(
            "kiln_ai.adapters.fine_tune.vertex_finetune.DatasetFormatter",
            return_value=mock_formatter,
        ),
        patch(
            "kiln_ai.adapters.fine_tune.vertex_finetune.storage.Client",
            return_value=mock_storage_client,
        ),
        patch(
            "kiln_ai.adapters.fine_tune.vertex_finetune.time.time",
            return_value=1234567890,
        ),
        patch.object(Config, "shared") as mock_config,
    ):
        mock_config.return_value.vertex_project_id = "test-project"
        mock_config.return_value.vertex_location = "us-central1"

        result = await finetune.generate_and_upload_jsonl(
            mock_dataset, "train", mock_task, DatasetFormat.VERTEX_GEMINI
        )

        # Verify formatter was created with correct parameters
        mock_formatter.dump_to_file.assert_called_once_with(
            "train", DatasetFormat.VERTEX_GEMINI, data_strategy
        )

        # Verify storage client was created with correct parameters
        mock_storage_client.bucket.assert_called_once_with("kiln-ai-data")

        # Verify blob was created and uploaded
        mock_bucket.blob.assert_called_once_with(f"1234567890/{mock_path.name}")
        mock_blob.upload_from_filename.assert_called_once_with(mock_path)

        # Verify GCS URI was returned
        assert result == expected_uri


async def test_generate_and_upload_jsonl_create_bucket(
    vertex_finetune, mock_dataset, mock_task
):
    mock_path = Path("mock_path.jsonl")
    expected_uri = "gs://kiln-ai-data/1234567890/mock_path.jsonl"

    # Mock the formatter
    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_formatter.dump_to_file.return_value = mock_path

    # Mock storage client and bucket operations - bucket doesn't exist
    mock_bucket = MagicMock()
    mock_bucket.name = "kiln-ai-data"

    mock_blob = MagicMock()
    mock_blob.name = f"1234567890/{mock_path.name}"

    mock_storage_client = MagicMock(spec=storage.Client)
    mock_storage_client.lookup_bucket.return_value = None  # Bucket doesn't exist
    mock_storage_client.create_bucket.return_value = mock_bucket

    mock_bucket.blob.return_value = mock_blob

    with (
        patch(
            "kiln_ai.adapters.fine_tune.vertex_finetune.DatasetFormatter",
            return_value=mock_formatter,
        ),
        patch(
            "kiln_ai.adapters.fine_tune.vertex_finetune.storage.Client",
            return_value=mock_storage_client,
        ),
        patch(
            "kiln_ai.adapters.fine_tune.vertex_finetune.time.time",
            return_value=1234567890,
        ),
        patch.object(Config, "shared") as mock_config,
    ):
        mock_config.return_value.vertex_project_id = "test-project"
        mock_config.return_value.vertex_location = "us-central1"

        result = await vertex_finetune.generate_and_upload_jsonl(
            mock_dataset, "train", mock_task, DatasetFormat.VERTEX_GEMINI
        )

        # Verify bucket was created
        mock_storage_client.create_bucket.assert_called_once_with(
            "kiln-ai-data", location="us-central1"
        )

        # Verify blob was created and uploaded
        mock_blob.upload_from_filename.assert_called_once_with(mock_path)

        # Verify GCS URI was returned
        assert result == expected_uri


@pytest.mark.parametrize(
    "output_schema,expected_mode,expected_format",
    [
        (
            '{"type": "object", "properties": {"key": {"type": "string"}}}',
            StructuredOutputMode.json_mode,
            DatasetFormat.VERTEX_GEMINI,
        ),
        (None, None, DatasetFormat.VERTEX_GEMINI),
    ],
)
async def test_start_success(
    vertex_finetune,
    mock_dataset,
    mock_task,
    output_schema,
    expected_mode,
    expected_format,
):
    # Set task for finetune
    vertex_finetune.datamodel.parent = mock_task
    mock_task.output_json_schema = output_schema

    # Mock hyperparameters
    vertex_finetune.datamodel.parameters = {
        "epochs": 3,
        "learning_rate_multiplier": 0.1,
        "adapter_size": 8,
    }

    # Mock train response
    mock_sft_job = MagicMock()
    mock_sft_job.resource_name = "vertex-ft-123"

    train_file_uri = "gs://kiln-ai-data/train.jsonl"
    validation_file_uri = "gs://kiln-ai-data/validation.jsonl"

    with (
        patch.object(
            vertex_finetune,
            "generate_and_upload_jsonl",
            side_effect=[train_file_uri, validation_file_uri],
        ) as mock_upload,
        patch("kiln_ai.adapters.fine_tune.vertex_finetune.vertexai.init") as mock_init,
        patch(
            "kiln_ai.adapters.fine_tune.vertex_finetune.sft.train",
            return_value=mock_sft_job,
        ) as mock_train,
        patch.object(Config, "shared") as mock_config,
    ):
        mock_config.return_value.vertex_project_id = "test-project"
        mock_config.return_value.vertex_location = "us-central1"

        # Only training split, no validation
        vertex_finetune.datamodel.validation_split_name = None

        await vertex_finetune._start(mock_dataset)

        # Verify initialize was called
        mock_init.assert_called_once_with(
            project="test-project", location="us-central1"
        )

        # Verify file uploads (only training file, no validation)
        mock_upload.assert_called_once_with(
            mock_dataset,
            vertex_finetune.datamodel.train_split_name,
            mock_task,
            expected_format,
        )

        # Verify train call with correct parameters
        mock_train.assert_called_once_with(
            source_model=vertex_finetune.datamodel.base_model_id,
            train_dataset=train_file_uri,
            validation_dataset=None,
            tuned_model_display_name=f"kiln_finetune_{vertex_finetune.datamodel.id}",
            epochs=3,
            adapter_size=8,
            learning_rate_multiplier=0.1,
            labels={
                "source": "kiln",
                "kiln_finetune_id": str(vertex_finetune.datamodel.id),
                "kiln_task_id": str(mock_task.id),
            },
        )

        # Verify model updates
        assert vertex_finetune.datamodel.provider_id == "vertex-ft-123"
        assert vertex_finetune.datamodel.structured_output_mode == expected_mode


async def test_start_with_validation(vertex_finetune, mock_dataset, mock_task):
    # Set task and validation split for finetune
    vertex_finetune.datamodel.parent = mock_task
    vertex_finetune.datamodel.validation_split_name = "test"

    # Mock train response
    mock_sft_job = MagicMock()
    mock_sft_job.resource_name = "vertex-ft-123"

    train_file_uri = "gs://kiln-ai-data/train.jsonl"
    validation_file_uri = "gs://kiln-ai-data/validation.jsonl"

    with (
        patch.object(
            vertex_finetune,
            "generate_and_upload_jsonl",
            side_effect=[train_file_uri, validation_file_uri],
        ) as mock_upload,
        patch("kiln_ai.adapters.fine_tune.vertex_finetune.vertexai.init"),
        patch(
            "kiln_ai.adapters.fine_tune.vertex_finetune.sft.train",
            return_value=mock_sft_job,
        ) as mock_train,
        patch.object(Config, "shared") as mock_config,
    ):
        mock_config.return_value.vertex_project_id = "test-project"
        mock_config.return_value.vertex_location = "us-central1"

        await vertex_finetune._start(mock_dataset)

        # Verify both files were uploaded
        assert mock_upload.call_count == 2
        mock_upload.assert_any_call(
            mock_dataset,
            vertex_finetune.datamodel.train_split_name,
            mock_task,
            DatasetFormat.VERTEX_GEMINI,
        )
        mock_upload.assert_any_call(
            mock_dataset,
            "test",
            mock_task,
            DatasetFormat.VERTEX_GEMINI,
        )

        # Verify validation file was included
        mock_train.assert_called_once()
        assert mock_train.call_args[1]["validation_dataset"] == validation_file_uri


async def test_start_no_task(vertex_finetune, mock_dataset):
    # No parent task set
    vertex_finetune.datamodel.parent = None

    with pytest.raises(ValueError, match="Task is required to start a fine-tune"):
        await vertex_finetune._start(mock_dataset)


def test_available_parameters():
    parameters = VertexFinetune.available_parameters()
    assert len(parameters) == 3

    # Verify parameter names and types
    param_names = [p.name for p in parameters]
    assert "learning_rate_multiplier" in param_names
    assert "epochs" in param_names
    assert "adapter_size" in param_names

    # Verify all parameters are optional
    assert all(p.optional for p in parameters)


@pytest.mark.parametrize(
    "project_id,location,should_raise",
    [
        ("test-project", "us-central1", False),
        ("", "us-central1", True),
        (None, "us-central1", True),
        ("test-project", "", True),
        ("test-project", None, True),
        (None, None, True),
    ],
)
def test_get_vertex_provider_location(project_id, location, should_raise):
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.vertex_project_id = project_id
        mock_config.return_value.vertex_location = location

        if should_raise:
            with pytest.raises(
                ValueError, match="Google Vertex project and location must be set"
            ):
                VertexFinetune.get_vertex_provider_location()
        else:
            project, loc = VertexFinetune.get_vertex_provider_location()
            assert project == project_id
            assert loc == location
