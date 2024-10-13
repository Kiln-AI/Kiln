import pytest
from kiln_ai.datamodel import DataSource, DataSourceType
from pydantic import ValidationError


def test_valid_human_data_source():
    data_source = DataSource(
        type=DataSourceType.human, properties={"created_by": "John Doe"}
    )
    assert data_source.type == DataSourceType.human
    assert data_source.properties["created_by"] == "John Doe"


def test_valid_synthetic_data_source():
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "GPT-4",
            "model_provider": "OpenAI",
            "prompt_type": "completion",
        },
    )
    assert data_source.type == DataSourceType.synthetic
    assert data_source.properties["model_name"] == "GPT-4"
    assert data_source.properties["model_provider"] == "OpenAI"
    assert data_source.properties["prompt_type"] == "completion"


def test_missing_required_property():
    with pytest.raises(
        ValidationError, match="'created_by' is required for DataSourceType.human data"
    ):
        DataSource(type=DataSourceType.human)


def test_wrong_property_type():
    with pytest.raises(
        ValidationError,
        match="'model_name' must be of type str for DataSourceType.synthetic data",
    ):
        DataSource(
            type=DataSourceType.synthetic,
            properties={"model_name": 123, "model_provider": "OpenAI"},
        )


def test_not_allowed_property():
    with pytest.raises(
        ValidationError,
        match="'created_by' is not allowed for DataSourceType.synthetic data",
    ):
        DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "GPT-4",
                "model_provider": "OpenAI",
                "created_by": "John Doe",
            },
        )


def test_extra_properties():
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "GPT-4",
            "model_provider": "OpenAI",
            "temperature": 0.7,
            "max_tokens": 100,
        },
    )
    assert data_source.properties["temperature"] == 0.7
    assert data_source.properties["max_tokens"] == 100


def test_prompt_type_optional_for_synthetic():
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={"model_name": "GPT-4", "model_provider": "OpenAI"},
    )
    assert "prompt_type" not in data_source.properties


def test_prompt_type_not_allowed_for_human():
    with pytest.raises(
        ValidationError,
        match="'prompt_type' is not allowed for DataSourceType.human data",
    ):
        DataSource(
            type=DataSourceType.human,
            properties={"created_by": "John Doe", "prompt_type": "completion"},
        )