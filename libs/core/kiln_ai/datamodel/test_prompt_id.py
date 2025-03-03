import pytest
from pydantic import BaseModel, ValidationError

from kiln_ai.datamodel import (
    PromptGenerators,
    PromptId,
)
from kiln_ai.datamodel.prompt_id import is_frozen_prompt


# Test model to validate the PromptId type
class ModelTester(BaseModel):
    prompt_id: PromptId


def test_valid_prompt_generator_names():
    """Test that valid prompt generator names are accepted"""
    for generator in PromptGenerators:
        model = ModelTester(prompt_id=generator.value)
        assert model.prompt_id == generator.value


def test_valid_saved_prompt_id():
    """Test that valid saved prompt IDs are accepted"""
    valid_id = "id::prompt_789"
    model = ModelTester(prompt_id=valid_id)
    assert model.prompt_id == valid_id


def test_valid_fine_tune_prompt_id():
    """Test that valid fine-tune prompt IDs are accepted"""
    valid_id = "fine_tune_prompt::ft_123456"
    model = ModelTester(prompt_id=valid_id)
    assert model.prompt_id == valid_id


@pytest.mark.parametrize(
    "invalid_id",
    [
        pytest.param("id::project_123::task_456", id="missing_prompt_id"),
        pytest.param("id::task_456::prompt_789", id="too_many_parts"),
        pytest.param("id::", id="empty_parts"),
    ],
)
def test_invalid_saved_prompt_id_format(invalid_id):
    """Test that invalid saved prompt ID formats are rejected"""
    with pytest.raises(ValidationError, match="Invalid saved prompt ID"):
        ModelTester(prompt_id=invalid_id)


@pytest.mark.parametrize(
    "invalid_id,expected_error",
    [
        ("fine_tune_prompt::", "Invalid fine-tune prompt ID: fine_tune_prompt::"),
        ("fine_tune_prompt", "Invalid prompt ID: fine_tune_prompt"),
    ],
)
def test_invalid_fine_tune_prompt_id_format(invalid_id, expected_error):
    """Test that invalid fine-tune prompt ID formats are rejected"""
    with pytest.raises(ValidationError, match=expected_error):
        ModelTester(prompt_id=invalid_id)


def test_completely_invalid_formats():
    """Test that completely invalid formats are rejected"""
    invalid_ids = [
        "",  # Empty string
        "invalid_format",  # Random string
        "id:wrong_format",  # Almost correct but wrong separator
        "fine_tune:wrong_format",  # Almost correct but wrong prefix
        ":::",  # Just separators
    ]

    for invalid_id in invalid_ids:
        with pytest.raises(ValidationError, match="Invalid prompt ID"):
            ModelTester(prompt_id=invalid_id)


def test_prompt_generator_case_sensitivity():
    """Test that prompt generator names are case sensitive"""
    # Take first generator and modify its case
    first_generator = next(iter(PromptGenerators)).value
    wrong_case = first_generator.upper()
    if wrong_case == first_generator:
        wrong_case = first_generator.lower()

    with pytest.raises(ValidationError):
        ModelTester(prompt_id=wrong_case)


@pytest.mark.parametrize(
    "valid_id",
    [
        "task_run_config::project_123::task_456::config_123",  # Valid task run config prompt ID
    ],
)
def test_valid_task_run_config_prompt_id(valid_id):
    """Test that valid eval prompt IDs are accepted"""
    model = ModelTester(prompt_id=valid_id)
    assert model.prompt_id == valid_id


@pytest.mark.parametrize(
    "invalid_id,expected_error",
    [
        ("task_run_config::", "Invalid task run config prompt ID"),
        ("task_run_config::p1", "Invalid task run config prompt ID"),
        ("task_run_config::p1::t1", "Invalid task run config prompt ID"),
        ("task_run_config::p1::t1::c1::extra", "Invalid task run config prompt ID"),
    ],
)
def test_invalid_eval_prompt_id_format(invalid_id, expected_error):
    """Test that invalid eval prompt ID formats are rejected"""
    with pytest.raises(ValidationError, match=expected_error):
        ModelTester(prompt_id=invalid_id)


@pytest.mark.parametrize(
    "id,should_be_frozen",
    [
        ("simple_prompt_builder", False),
        ("id::prompt_123", True),
        ("task_run_config::p1::t1", True),
        ("fine_tune_prompt::ft_123", True),
    ],
)
def test_is_frozen_prompt(id, should_be_frozen):
    """Test that the is_frozen_prompt function works"""
    assert is_frozen_prompt(id) == should_be_frozen
