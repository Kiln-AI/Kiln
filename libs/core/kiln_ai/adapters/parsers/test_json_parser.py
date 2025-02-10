import pytest

from kiln_ai.adapters.parsers.json_parser import parse_json_string


def test_parse_plain_json():
    json_str = '{"key": "value", "number": 42}'
    result = parse_json_string(json_str)
    assert result == {"key": "value", "number": 42}


def test_parse_json_with_code_block():
    json_str = """```
    {"key": "value", "number": 42}
    ```"""
    result = parse_json_string(json_str)
    assert result == {"key": "value", "number": 42}


def test_parse_json_with_language_block():
    json_str = """```json
    {"key": "value", "number": 42}
    ```"""
    result = parse_json_string(json_str)
    assert result == {"key": "value", "number": 42}


def test_parse_json_with_whitespace():
    json_str = """
        {
            "key": "value",
            "number": 42
        }
    """
    result = parse_json_string(json_str)
    assert result == {"key": "value", "number": 42}


def test_parse_invalid_json():
    json_str = '{"key": "value", invalid}'
    with pytest.raises(ValueError) as exc_info:
        parse_json_string(json_str)
    assert (
        "This task requires JSON output but the model didn't return valid JSON."
        in str(exc_info.value)
    )


def test_parse_empty_code_block():
    json_str = """```json
    ```"""
    with pytest.raises(ValueError) as exc_info:
        parse_json_string(json_str)
    assert (
        "This task requires JSON output but the model didn't return valid JSON."
        in str(exc_info.value)
    )


def test_parse_complex_json():
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
    result = parse_json_string(json_str)
    assert result == {
        "string": "hello",
        "number": 42,
        "bool": True,
        "null": None,
        "array": [1, 2, 3],
        "nested": {"inner": "value"},
    }
