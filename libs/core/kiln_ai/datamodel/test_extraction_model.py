import pytest

from kiln_ai.datamodel.extraction import ExtractorConfig, ExtractorType


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


def test_extractor_config_invalid_config_type(valid_extractor_config):
    # Create an invalid config type using string
    with pytest.raises(ValueError):
        valid_extractor_config.extractor_type = "invalid_type"
