from unittest.mock import Mock, patch

import pytest

from kiln_ai.adapters.fine_tune.finetune_run_config_id import (
    finetune_from_finetune_run_config_id,
    finetune_run_config_id,
)
from kiln_ai.datamodel import Finetune


def test_finetune_run_config_id():
    """Test that finetune_run_config_id builds the correct ID format"""
    project_id = "project-123"
    task_id = "task-456"
    finetune_id = "finetune-789"

    result = finetune_run_config_id(project_id, task_id, finetune_id)

    assert result == "finetune_run_config::project-123::task-456::finetune-789"


@patch("kiln_ai.adapters.fine_tune.finetune_run_config_id.finetune_from_id")
def test_finetune_from_finetune_run_config_id_valid(mock_finetune_from_id):
    """Test that finetune_from_finetune_run_config_id correctly parses valid IDs"""
    mock_finetune = Mock(spec=Finetune)
    mock_finetune_from_id.return_value = mock_finetune

    finetune_run_config_id_str = (
        "finetune_run_config::project-123::task-456::finetune-789"
    )
    result = finetune_from_finetune_run_config_id(finetune_run_config_id_str)

    mock_finetune_from_id.assert_called_once_with("project-123::task-456::finetune-789")
    assert result == mock_finetune


@pytest.mark.parametrize(
    "invalid_id",
    [
        "invalid_format",
        "wrong_prefix::project::task::finetune",
        "",
    ],
)
@patch("kiln_ai.adapters.fine_tune.finetune_run_config_id.finetune_from_id")
def test_finetune_from_finetune_run_config_id_invalid(
    mock_finetune_from_id, invalid_id
):
    """Test that finetune_from_finetune_run_config_id raises ValueError for invalid IDs"""
    with pytest.raises(ValueError, match="Invalid finetune run config ID"):
        finetune_from_finetune_run_config_id(invalid_id)

    mock_finetune_from_id.assert_not_called()
