import pytest
from pydantic import ValidationError

from kiln_ai.datamodel import DataSource, DataSourceType


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
            "prompt_builder_name": "completion",
            "adapter_name": "langchain",
        },
    )
    assert data_source.type == DataSourceType.synthetic
    assert data_source.properties["model_name"] == "GPT-4"
    assert data_source.properties["model_provider"] == "OpenAI"
    assert data_source.properties["prompt_builder_name"] == "completion"
    assert data_source.properties["adapter_name"] == "langchain"


def test_missing_required_property():
    with pytest.raises(ValidationError, match="'created_by' is required for"):
        DataSource(type=DataSourceType.human)


def test_wrong_property_type():
    with pytest.raises(
        ValidationError,
        match="'model_name' must be of type str for",
    ):
        DataSource(
            type=DataSourceType.synthetic,
            properties={"model_name": 123, "model_provider": "OpenAI"},
        )


def test_not_allowed_property():
    with pytest.raises(
        ValidationError,
        match="'created_by' is not allowed for",
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
            "adapter_name": "langchain",
            "temperature": 0.7,
            "max_tokens": 100,
        },
    )
    assert data_source.properties["temperature"] == 0.7
    assert data_source.properties["max_tokens"] == 100


def test_prompt_type_optional_for_synthetic():
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "GPT-4",
            "model_provider": "OpenAI",
            "adapter_name": "langchain",
        },
    )
    assert "prompt_builder_name" not in data_source.properties


def test_private_data_source_properties_not_serialized():
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "GPT-4",
            "model_provider": "OpenAI",
            "adapter_name": "langchain",
        },
    )
    serialized = data_source.model_dump()
    assert "_data_source_properties" not in serialized
    assert "properties" in serialized
    assert serialized["properties"] == {
        "model_name": "GPT-4",
        "model_provider": "OpenAI",
        "adapter_name": "langchain",
    }
