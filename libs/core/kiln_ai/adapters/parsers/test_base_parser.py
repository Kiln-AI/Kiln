import pytest

from kiln_ai.adapters.parsers.base_parser import BaseParser
from kiln_ai.adapters.run_output import RunOutput


@pytest.fixture
def parser():
    return BaseParser()


def test_strip_string_output(parser):
    """Test that string output gets stripped of whitespace."""
    response = RunOutput(
        output="  \n\n  This is the result  \n\n  ",
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert parsed.output == "This is the result"


def test_strip_intermediate_outputs(parser):
    """Test that string values in intermediate_outputs get stripped."""
    response = RunOutput(
        output="This is the result",
        intermediate_outputs={
            "reasoning": "  \n\n  This is thinking content  \n\n  ",
            "step1": "  Step 1 content  ",
            "step2": "Step 2 content",  # No whitespace to strip
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs["reasoning"] == "This is thinking content"
    assert parsed.intermediate_outputs["step1"] == "Step 1 content"
    assert parsed.intermediate_outputs["step2"] == "Step 2 content"
    assert parsed.output == "This is the result"


def test_non_string_output_unchanged(parser):
    """Test that non-string outputs are not modified."""
    response = RunOutput(
        output={"key": "value", "number": 42},
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert parsed.output == {"key": "value", "number": 42}


def test_non_string_intermediate_outputs_unchanged(parser):
    """Test that non-string values in intermediate_outputs are not modified."""
    # Note: RunOutput.intermediate_outputs only accepts Dict[str, str], so we can't test
    # non-string values directly. This test verifies the BaseParser doesn't modify
    # the intermediate_outputs structure.
    response = RunOutput(
        output="result",
        intermediate_outputs={
            "string_value": "  stripped  ",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs["string_value"] == "stripped"


def test_none_output_unchanged(parser):
    """Test that None output is not modified."""
    # RunOutput doesn't accept None for output, so we test with empty string
    response = RunOutput(
        output="",
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert parsed.output == ""


def test_none_intermediate_outputs_unchanged(parser):
    """Test that None intermediate_outputs is not modified."""
    response = RunOutput(
        output="result",
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs is None


def test_empty_string_output(parser):
    """Test that empty string output gets stripped to empty string."""
    response = RunOutput(
        output="   \n\n   ",
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert parsed.output == ""


def test_empty_string_intermediate_outputs(parser):
    """Test that empty string values in intermediate_outputs get stripped."""
    response = RunOutput(
        output="result",
        intermediate_outputs={
            "empty": "   \n\n   ",
            "whitespace_only": "  \t  \n  ",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs["empty"] == ""
    assert parsed.intermediate_outputs["whitespace_only"] == ""


def test_mixed_content_types(parser):
    """Test handling of mixed string and non-string content."""
    response = RunOutput(
        output="  main result  ",
        intermediate_outputs={
            "string": "  string content  ",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.output == "main result"
    assert parsed.intermediate_outputs["string"] == "string content"


def test_dict_output_unchanged(parser):
    """Test that dict output is not modified."""
    response = RunOutput(
        output={"key": "value", "nested": {"inner": "data"}},
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert parsed.output == {"key": "value", "nested": {"inner": "data"}}


def test_multiple_intermediate_outputs(parser):
    """Test that all string values in intermediate_outputs get stripped."""
    response = RunOutput(
        output="result",
        intermediate_outputs={
            "reasoning": "  \n\n  Thinking process  \n\n  ",
            "analysis": "  Analysis content  ",
            "conclusion": "Conclusion",  # No whitespace
            "empty": "   \n\n   ",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs["reasoning"] == "Thinking process"
    assert parsed.intermediate_outputs["analysis"] == "Analysis content"
    assert parsed.intermediate_outputs["conclusion"] == "Conclusion"
    assert parsed.intermediate_outputs["empty"] == ""
