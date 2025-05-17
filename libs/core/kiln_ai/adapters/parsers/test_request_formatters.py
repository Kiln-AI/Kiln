import pytest

from kiln_ai.adapters.ml_model_list import ModelFormatterID
from kiln_ai.adapters.parsers.request_formatters import (
    Qwen3StyleNoThinkFormatter,
    request_formatter_from_id,
)


@pytest.fixture
def qwen_formatter():
    return Qwen3StyleNoThinkFormatter()


def test_qwen_formatter_string_input(qwen_formatter):
    input_text = "Hello world"
    formatted = qwen_formatter.format_input(input_text)
    assert formatted == "Hello world\n\n/no_think"


def test_qwen_formatter_dict_input(qwen_formatter):
    input_dict = {"key": "value", "nested": {"inner": "data"}}
    formatted = qwen_formatter.format_input(input_dict)
    expected = """{
  "key": "value",
  "nested": {
    "inner": "data"
  }
}

/no_think"""
    assert formatted == expected


def test_qwen_formatter_empty_input(qwen_formatter):
    # Test empty string
    assert qwen_formatter.format_input("") == "\n\n/no_think"

    # Test empty dict
    assert qwen_formatter.format_input({}) == "{}\n\n/no_think"


def test_qwen_formatter_special_characters(qwen_formatter):
    input_text = "Special chars: !@#$%^&*()_+思"
    formatted = qwen_formatter.format_input(input_text)
    assert formatted == "Special chars: !@#$%^&*()_+思\n\n/no_think"


def test_qwen_formatter_multiline_string(qwen_formatter):
    input_text = """Line 1
    Line 2
    Line 3"""
    formatted = qwen_formatter.format_input(input_text)
    assert (
        formatted
        == """Line 1
    Line 2
    Line 3

/no_think"""
    )


def test_request_formatter_factory():
    # Test valid formatter ID
    formatter = request_formatter_from_id(ModelFormatterID.qwen3_style_no_think)
    assert isinstance(formatter, Qwen3StyleNoThinkFormatter)

    # Test that the formatter works
    assert formatter.format_input("test") == "test\n\n/no_think"


def test_request_formatter_factory_invalid_id():
    # Test with an invalid enum value by using a string that doesn't exist in the enum
    with pytest.raises(ValueError, match="Unhandled enum value"):
        request_formatter_from_id("invalid_formatter_id")  # type: ignore
