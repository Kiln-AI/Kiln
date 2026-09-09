import pytest
from litellm.types.utils import ChoiceLogprobs

from kiln_ai.adapters.parsers.r1_parser import R1ThinkingParser
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


@pytest.fixture
def parser():
    return R1ThinkingParser()


@pytest.fixture
def trace() -> list[ChatCompletionMessageParam]:
    return [
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "<think>Adding them</think>4"},
    ]


@pytest.fixture
def logprobs() -> ChoiceLogprobs:
    return ChoiceLogprobs(content=[])


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


def test_empty_thinking_content_multiline(parser):
    response = RunOutput(
        output="""
        <think>

        </think>
            This is the result
    """,
        intermediate_outputs=None,
    )
    parsed = parser.parse_output(response)
    assert "reasoning" not in parsed.intermediate_outputs
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
    assert "reasoning" not in parsed.intermediate_outputs
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


def test_strip_newlines(parser):
    # certain providers via LiteLLM for example, add newlines to the output
    # and to the reasoning. This tests that we strip those newlines.
    response = RunOutput(
        output="\n\nSome content",
        intermediate_outputs={
            "reasoning": "\n\nSome thinking\n\n",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.output == "Some content"
    assert parsed.intermediate_outputs["reasoning"] == "Some thinking"


def test_strip_newlines_with_structured_output(parser):
    # certain providers via LiteLLM for example, add newlines to the output
    # and to the reasoning. This tests that we strip those newlines.
    response = RunOutput(
        output={"some_key": "Some content"},
        intermediate_outputs={
            "reasoning": "\n\nSome thinking\n\n",
        },
    )
    parsed = parser.parse_output(response)
    assert parsed.output == {"some_key": "Some content"}
    assert parsed.intermediate_outputs["reasoning"] == "Some thinking"


@pytest.mark.parametrize(
    "allow_missing_thinking,output,intermediate_outputs",
    [
        # The parse path: parser extracts thinking from an inline <think> tag
        (False, "<think>Adding them</think>4", None),
        # Early return: the provider already parsed reasoning for us
        (False, "4", {"reasoning": "Adding them"}),
        # Early return: no </think> tag, and the parser tolerates that
        (True, "4", None),
    ],
    ids=["parse_path", "provider_pre_parsed", "missing_thinking_allowed"],
)
def test_preserves_trace_and_logprobs(
    allow_missing_thinking, output, intermediate_outputs, trace, logprobs
):
    parsed = R1ThinkingParser(
        allow_missing_thinking=allow_missing_thinking
    ).parse_output(
        RunOutput(
            output=output,
            intermediate_outputs=intermediate_outputs,
            output_logprobs=logprobs,
            trace=trace,
        )
    )
    assert parsed.output == "4"
    assert parsed.trace is trace
    assert parsed.output_logprobs is logprobs
