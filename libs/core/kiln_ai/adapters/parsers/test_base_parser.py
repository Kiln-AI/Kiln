import pytest
from kiln_ai.adapters.parsers.base_parser import BaseParser


@pytest.fixture
def parser():
    return BaseParser()


def test_parse_plain_json(parser):
    json_str = '{"key": "value", "number": 42}'
    result = parser.parse_json_string(json_str)
    assert result == {"key": "value", "number": 42}


def test_parse_json_with_code_block(parser):
    json_str = """```
    {"key": "value", "number": 42}
    ```"""
    result = parser.parse_json_string(json_str)
    assert result == {"key": "value", "number": 42}


def test_parse_json_with_language_block(parser):
    json_str = """```json
    {"key": "value", "number": 42}
    ```"""
    result = parser.parse_json_string(json_str)
    assert result == {"key": "value", "number": 42}


def test_parse_json_with_whitespace(parser):
    json_str = """
        {
            "key": "value",
            "number": 42
        }
    """
    result = parser.parse_json_string(json_str)
    assert result == {"key": "value", "number": 42}


def test_parse_invalid_json(parser):
    json_str = '{"key": "value", invalid}'
    with pytest.raises(ValueError) as exc_info:
        parser.parse_json_string(json_str)
    assert "Failed to parse JSON" in str(exc_info.value)


def test_parse_empty_code_block(parser):
    json_str = """```json
    ```"""
    with pytest.raises(ValueError) as exc_info:
        parser.parse_json_string(json_str)
    assert "Failed to parse JSON" in str(exc_info.value)


def test_parse_complex_json(parser):
    json_str = """```json
    {
        "string": "hello",
        "number": 42,
        "bool": true,
        "null": null,
        "array": [1, 2, 3],
        "nested": {
            "inner": "value"
        }
    }
    ```"""
    result = parser.parse_json_string(json_str)
    assert result == {
        "string": "hello",
        "number": 42,
        "bool": True,
        "null": None,
        "array": [1, 2, 3],
        "nested": {"inner": "value"},
    }
