import pytest

from kiln_ai.adapters.parsers.reasoning_answer_tags_parser import (
    ReasoningAnswerTagsParser,
)
from kiln_ai.adapters.run_output import RunOutput


@pytest.fixture
def parser():
    return ReasoningAnswerTagsParser()


def test_valid_response(parser):
    response = RunOutput(
        output="",
        intermediate_outputs={
            "reasoning": "<answer>This is the answer, and yes, it is wrapped in tags inside the reasoning...</answer>",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs is None
    assert (
        parsed.output
        == "This is the answer, and yes, it is wrapped in tags inside the reasoning..."
    )


def test_already_parsed_response(parser):
    # if the provider ever fixes their format, we would be getting something like this
    response = RunOutput(
        output="This is the result",
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs is None
    assert parsed.output == "This is the result"


def test_response_with_whitespace(parser):
    response = RunOutput(
        output="",
        intermediate_outputs={
            "reasoning": """
            <answer>
                This is the answer, and yes, it is wrapped in tags inside the reasoning...
            </answer>
            """,
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs is None
    assert (
        parsed.output.strip()
        == "This is the answer, and yes, it is wrapped in tags inside the reasoning..."
    )


def test_empty_answer_content(parser):
    response = RunOutput(
        output="",
        intermediate_outputs={
            "reasoning": """
            <answer>

            </answer>
            """,
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs is None
    assert parsed.output == ""


def test_missing_start_tag(parser):
    parsed = parser.parse_output(
        RunOutput(
            output="",
            intermediate_outputs={
                "reasoning": "Some content</answer>",
            },
        )
    )

    assert parsed.intermediate_outputs is None
    assert parsed.output == "Some content"


def test_missing_end_tag(parser):
    with pytest.raises(
        RuntimeError,
        match="The response is malformed.* missing the end </answer> tag in the reasoning content",
    ):
        parser.parse_output(
            RunOutput(
                output="",
                intermediate_outputs={
                    "reasoning": "<answer>Some content",
                },
            )
        )


def test_multiple_start_tags(parser):
    with pytest.raises(
        RuntimeError,
        match="The response is malformed.* multiple <answer> tags found in the reasoning content",
    ):
        parser.parse_output(
            RunOutput(
                output="",
                intermediate_outputs={
                    "reasoning": "<answer>content1<answer>content2</answer>",
                },
            )
        )


def test_multiple_end_tags(parser):
    with pytest.raises(
        RuntimeError,
        match="The response is malformed.* multiple </answer> tags found in the reasoning content",
    ):
        parser.parse_output(
            RunOutput(
                output="",
                intermediate_outputs={
                    "reasoning": "<answer>content</answer></answer>result",
                },
            )
        )


def test_empty_reasoning_content(parser):
    response = RunOutput(
        output="",
        intermediate_outputs={
            "reasoning": "",
        },
    )

    with pytest.raises(
        RuntimeError,
        match="The response is malformed.* missing or empty reasoning content",
    ):
        parser.parse_output(response)


def test_multiline_content(parser):
    response = RunOutput(
        output="",
        intermediate_outputs={
            "reasoning": """<answer>Line 1
    Line 2
    Line 3</answer>""",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs is None
    assert "Line 1" in parsed.output
    assert "Line 2" in parsed.output
    assert "Line 3" in parsed.output


def test_special_characters(parser):
    response = RunOutput(
        output="",
        intermediate_outputs={
            "reasoning": "<answer>Content with: !@#$%^&*思()</answer>",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.intermediate_outputs is None
    assert parsed.output == "Content with: !@#$%^&*思()"


def test_strip_newlines(parser):
    # certain providers via LiteLLM for example, add newlines to the output
    # and to the reasoning. This tests that we strip those newlines.
    response = RunOutput(
        output="",
        intermediate_outputs={
            "reasoning": "\n\n<answer>\n\nSome content\nwith a linebreak inside\n\n</answer>\n\n",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.output == "Some content\nwith a linebreak inside"
    assert parsed.intermediate_outputs is None
