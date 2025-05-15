import pytest
from pydantic import BaseModel, Field, ValidationError, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.extraction import (
    ExtractorConfig,
    ExtractorType,
    Kind,
    format_properties_errors,
)


@pytest.fixture
def valid_extractor_config_data():
    return {
        "name": "Test Extractor Config",
        "extractor_type": ExtractorType.gemini,
        "properties": {
            "prompt_for_kind": {
                "document": "Transcribe the document.",
                "audio": "Transcribe the audio.",
                "video": "Transcribe the video.",
                "image": "Describe the image.",
            },
            "model_name": "gemini-2.0-flash",
        },
    }


@pytest.fixture
def valid_extractor_config(valid_extractor_config_data):
    return ExtractorConfig(**valid_extractor_config_data)


def test_extractor_config_kind_coercion(valid_extractor_config):
    # check that the string values are coerced to the correct kind
    gemini_config = valid_extractor_config.gemini_properties()
    assert (
        gemini_config.prompt_for_kind.get(Kind.DOCUMENT) == "Transcribe the document."
    )
    assert gemini_config.prompt_for_kind.get(Kind.AUDIO) == "Transcribe the audio."
    assert gemini_config.prompt_for_kind.get(Kind.VIDEO) == "Transcribe the video."
    assert gemini_config.prompt_for_kind.get(Kind.IMAGE) == "Describe the image."


def test_extractor_config_valid(valid_extractor_config):
    assert valid_extractor_config.name == "Test Extractor Config"
    assert valid_extractor_config.extractor_type == ExtractorType.gemini
    assert valid_extractor_config.properties["prompt_for_kind"] == {
        "document": "Transcribe the document.",
        "audio": "Transcribe the audio.",
        "video": "Transcribe the video.",
        "image": "Describe the image.",
    }
    assert valid_extractor_config.properties["model_name"] == "gemini-2.0-flash"


def test_extractor_config_empty_properties(valid_extractor_config):
    with pytest.raises(ValueError, match="prompt_for_kind: Field required."):
        valid_extractor_config.properties = {}


def test_extractor_config_missing_model_name(
    valid_extractor_config, valid_extractor_config_data
):
    with pytest.raises(ValueError, match="model_name: Field required."):
        valid_extractor_config.properties = {
            "prompt_for_kind": valid_extractor_config_data["properties"][
                "prompt_for_kind"
            ],
        }


def test_extractor_config_missing_prompt_for_kind(valid_extractor_config):
    with pytest.raises(
        ValueError,
        match="prompt_for_kind: Field required.",
    ):
        valid_extractor_config.properties = {"model_name": "gemini-2.0-flash"}


def test_extractor_config_invalid_json(
    valid_extractor_config, valid_extractor_config_data
):
    class InvalidClass:
        pass

    with pytest.raises(ValueError, match="Properties must be JSON serializable"):
        valid_extractor_config.properties = {
            "prompt_for_kind": valid_extractor_config_data["properties"][
                "prompt_for_kind"
            ],
            "model_name": "gemini-2.0-flash",
            "invalid_key": InvalidClass(),
        }


def test_extractor_config_invalid_prompt_for_kind(valid_extractor_config):
    with pytest.raises(
        ValueError,
        match="prompt_for_kind: Input should be a valid dictionary.",
    ):
        valid_extractor_config.properties = {
            "prompt_for_kind": "not a dict",
            "model_name": "gemini-2.0-flash",
        }


def test_extractor_config_incomplete_prompt_for_kind(valid_extractor_config):
    with pytest.raises(
        ValueError,
        match="Prompt for kind image is required.",
    ):
        valid_extractor_config.properties = {
            "prompt_for_kind": {
                "document": "Transcribe the document.",
                "audio": "Transcribe the audio.",
                "video": "Transcribe the video.",
                # missing image
            },
            "model_name": "gemini-2.0-flash",
        }


def test_extractor_config_invalid_config_type(valid_extractor_config):
    # Create an invalid config type using string
    with pytest.raises(ValueError):
        valid_extractor_config.extractor_type = "invalid_type"


def test_format_properties_errors():
    class SomeModel(BaseModel):
        name: str = Field(description="The name of the user.")
        city: str = Field(description="The city of the user.")
        age: int = Field(description="The age of the user.")

        @model_validator(mode="after")
        def validate_city(self) -> Self:
            if self.city == "New York City":
                raise ValueError("Cannot be New York City")
            return self

    # errors raised from inside a custom validator
    try:
        SomeModel.model_validate(
            {
                "name": "John",
                "city": "New York City",
                "age": 30,
            }
        )
    except ValidationError as e:
        s = format_properties_errors(e)
        assert s == "Value error, Cannot be New York City."

    # missing required field
    try:
        SomeModel.model_validate(
            {
                "name": "John",
                "age": 30,
            }
        )
    except ValidationError as e:
        s = format_properties_errors(e)
        assert s == "city: Field required."

    # invalid type
    try:
        SomeModel.model_validate(
            {
                "name": "John",
                "city": "Pittsburgh",
                "age": "30",
            }
        )  # type: ignore
    except ValidationError as e:
        s = format_properties_errors(e)
        assert (
            s
            == "age: Input should be a valid integer, unable to parse string as an integer."
        )

    # multiple errors
    try:
        SomeModel.model_validate(
            {
                "name": "John",
            }
        )
    except ValidationError as e:
        s = format_properties_errors(e)
        assert s == "city: Field required.\nage: Field required."
