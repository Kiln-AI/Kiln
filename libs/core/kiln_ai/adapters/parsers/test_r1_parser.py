import pytest

from kiln_ai.adapters.parsers.r1_parser import R1ThinkingParser
from kiln_ai.adapters.run_output import RunOutput


@pytest.fixture
def parser():
    return R1ThinkingParser()


def test_valid_response(parser):
    response = RunOutput(
        output="<think>This is thinking content</think>This is the result",
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs["reasoning"] == "This is thinking content"
    assert parsed.output == "This is the result"


def test_already_parsed_response(parser):
    response = RunOutput(
        output="This is the result",
        intermediate_outputs={"reasoning": "This is thinking content"},
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs["reasoning"] == "This is thinking content"
    assert parsed.output == "This is the result"


def test_response_with_whitespace(parser):
    response = RunOutput(
        output="""
        <think>
            This is thinking content
        </think>
            This is the result
    """,
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert (
        parsed.intermediate_outputs["reasoning"].strip() == "This is thinking content"
    )
    assert parsed.output.strip() == "This is the result"


def test_missing_start_tag(parser):
    parsed = parser.parse_output(
        RunOutput(output="Some content</think>result", intermediate_outputs=None)
    )

    assert parsed.intermediate_outputs["reasoning"] == "Some content"
    assert parsed.output == "result"


def test_missing_end_tag(parser):
    with pytest.raises(ValueError, match="Missing </think> tag"):
        parser.parse_output(
            RunOutput(output="<think>Some content", intermediate_outputs=None)
        )


def test_multiple_start_tags(parser):
    with pytest.raises(ValueError, match="Multiple thinking tags found"):
        parser.parse_output(
            RunOutput(
                output="<think>content1<think>content2</think>result",
                intermediate_outputs=None,
            )
        )


def test_multiple_end_tags(parser):
    with pytest.raises(ValueError, match="Multiple thinking tags found"):
        parser.parse_output(
            RunOutput(
                output="<think>content</think></think>result", intermediate_outputs=None
            )
        )


def test_empty_thinking_content(parser):
    response = RunOutput(
        output="<think></think>This is the result", intermediate_outputs=None
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs == {"reasoning": ""}
    assert parsed.output == "This is the result"


def test_missing_result(parser):
    with pytest.raises(ValueError, match="No content found after </think> tag"):
        parser.parse_output(
            RunOutput(output="<think>Some content</think>", intermediate_outputs=None)
        )


def test_multiline_content(parser):
    response = RunOutput(
        output="""<think>Line 1
    Line 2
    Line 3</think>Final result""",
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert "Line 1" in parsed.intermediate_outputs["reasoning"]
    assert "Line 2" in parsed.intermediate_outputs["reasoning"]
    assert "Line 3" in parsed.intermediate_outputs["reasoning"]
    assert parsed.output == "Final result"


def test_special_characters(parser):
    response = RunOutput(
        output="<think>Content with: !@#$%^&*思()</think>Result with: !@#$%^&*思()",
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs["reasoning"] == "Content with: !@#$%^&*思()"
    assert parsed.output == "Result with: !@#$%^&*思()"


def test_non_string_input(parser):
    with pytest.raises(ValueError, match="Response must be a string for R1 parser"):
        parser.parse_output(RunOutput(output={}, intermediate_outputs=None))


def test_intermediate_outputs(parser):
    # append to existing intermediate outputs
    out = parser.parse_output(
        RunOutput(
            output="<think>Some content</think>result",
            intermediate_outputs={"existing": "data"},
        )
    )
    assert out.intermediate_outputs["reasoning"] == "Some content"
    assert out.intermediate_outputs["existing"] == "data"

    # empty dict is allowed
    out = parser.parse_output(
        RunOutput(
            output="<think>Some content</think>result",
            intermediate_outputs={},
        )
    )
    assert out.intermediate_outputs["reasoning"] == "Some content"

    # None is allowed
    out = parser.parse_output(
        RunOutput(
            output="<think>Some content</think>result",
            intermediate_outputs=None,
        )
    )
    assert out.intermediate_outputs["reasoning"] == "Some content"
