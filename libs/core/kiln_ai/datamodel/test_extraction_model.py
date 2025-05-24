import pytest

from kiln_ai.datamodel.extraction import (
    ExtractorConfig,
    ExtractorType,
    Kind,
    OutputFormat,
    validate_model_name,
    validate_prompt_for_kind,
)


@pytest.fixture
def valid_extractor_config_data():
    return {
        "name": "Test Extractor Config",
        "description": "Test description",
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
    prompt_for_kind = valid_extractor_config.prompt_for_kind()
    assert prompt_for_kind.get(Kind.DOCUMENT) == "Transcribe the document."
    assert prompt_for_kind.get(Kind.AUDIO) == "Transcribe the audio."
    assert prompt_for_kind.get(Kind.VIDEO) == "Transcribe the video."
    assert prompt_for_kind.get(Kind.IMAGE) == "Describe the image."


def test_extractor_config_description_empty(valid_extractor_config_data):
    # should not raise an error when description is None
    valid_extractor_config_data["description"] = None
    valid_extractor_config = ExtractorConfig(**valid_extractor_config_data)
    assert valid_extractor_config.description is None


def test_extractor_config_valid(valid_extractor_config):
    assert valid_extractor_config.name == "Test Extractor Config"
    assert valid_extractor_config.description == "Test description"
    assert valid_extractor_config.extractor_type == ExtractorType.gemini
    assert valid_extractor_config.properties["prompt_for_kind"] == {
        "document": "Transcribe the document.",
        "audio": "Transcribe the audio.",
        "video": "Transcribe the video.",
        "image": "Describe the image.",
    }
    assert valid_extractor_config.properties["model_name"] == "gemini-2.0-flash"


def test_extractor_config_empty_properties(valid_extractor_config):
    with pytest.raises(ValueError, match="prompt_for_kind must be a dictionary"):
        valid_extractor_config.properties = {}


def test_extractor_config_missing_model_name(
    valid_extractor_config, valid_extractor_config_data
):
    with pytest.raises(ValueError, match="model_name must be a string"):
        valid_extractor_config.properties = {
            "prompt_for_kind": valid_extractor_config_data["properties"][
                "prompt_for_kind"
            ],
        }


def test_extractor_config_empty_model_name(
    valid_extractor_config, valid_extractor_config_data
):
    with pytest.raises(ValueError, match="model_name cannot be empty"):
        valid_extractor_config.properties = {
            "prompt_for_kind": valid_extractor_config_data["properties"][
                "prompt_for_kind"
            ],
            "model_name": "",
        }


def test_extractor_config_missing_prompt_for_kind(valid_extractor_config):
    with pytest.raises(
        ValueError,
        match="prompt_for_kind must be a dictionary",
    ):
        valid_extractor_config.properties = {"model_name": "gemini-2.0-flash"}


def test_extractor_config_invalid_json(
    valid_extractor_config, valid_extractor_config_data
):
    class InvalidClass:
        pass

    with pytest.raises(ValueError, match="validation errors for ExtractorConfig"):
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
        match="prompt_for_kind must be a dictionary",
    ):
        valid_extractor_config.properties = {
            "prompt_for_kind": "not a dict",
            "model_name": "gemini-2.0-flash",
        }


def test_extractor_config_incomplete_prompt_for_kind(valid_extractor_config):
    with pytest.raises(
        ValueError,
        match="Missing prompt for kind: image",
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


@pytest.mark.parametrize(
    "passthrough_mimetypes",
    [
        [OutputFormat.TEXT],
        [OutputFormat.MARKDOWN],
        [OutputFormat.TEXT, OutputFormat.MARKDOWN],
    ],
)
def test_valid_passthrough_mimetypes(
    valid_extractor_config_data, passthrough_mimetypes
):
    config_data = valid_extractor_config_data.copy()
    config_data["passthrough_mimetypes"] = passthrough_mimetypes
    config = ExtractorConfig(**config_data)
    assert config.passthrough_mimetypes == passthrough_mimetypes


@pytest.mark.parametrize(
    "passthrough_mimetypes",
    [
        ["invalid_format"],
        ["another_invalid"],
        [OutputFormat.TEXT, "invalid_format"],
    ],
)
def test_invalid_passthrough_mimetypes(
    valid_extractor_config_data, passthrough_mimetypes
):
    config_data = valid_extractor_config_data.copy()
    config_data["passthrough_mimetypes"] = passthrough_mimetypes
    with pytest.raises(ValueError):
        ExtractorConfig(**config_data)


def test_validate_prompt_for_kind_valid():
    # check should not raise an error
    validate_prompt_for_kind(
        {
            "document": "string",
            "audio": "string",
            "video": "string",
            "image": "string",
        }
    )


@pytest.mark.parametrize(
    "prompt_for_kind, expected_error_message",
    [
        ("not a dict", "prompt_for_kind must be a dictionary"),
        ({"invalid_kind": "not a prompt"}, "'invalid_kind' is not a valid Kind"),
        (
            {"document": 123},
            "Invalid prompt for kind: document. Prompt must be a string.",
        ),
        (
            {
                "document": "string",
                "audio": "string",
                "video": "string",
                # missing image
            },
            "Missing prompt for kind: image",
        ),
        (
            {
                "document": "string",
                "audio": "string",
                "video": "string",
                "image": "string",
                "invalid_kind": "string",
            },
            "'invalid_kind' is not a valid Kind",
        ),
    ],
)
def test_validate_prompt_for_kind_errors(prompt_for_kind, expected_error_message):
    with pytest.raises(ValueError, match=expected_error_message):
        validate_prompt_for_kind(prompt_for_kind)


def test_validate_model_name_valid():
    # check should not raise an error
    validate_model_name("gemini-2.0-flash")


@pytest.mark.parametrize(
    "model_name, expected_error_message",
    [
        ("", "model_name cannot be empty"),
        (123, "model_name must be a string"),
    ],
)
def test_validate_model_name_invalid(model_name, expected_error_message):
    with pytest.raises(ValueError, match=expected_error_message):
        validate_model_name(model_name)
