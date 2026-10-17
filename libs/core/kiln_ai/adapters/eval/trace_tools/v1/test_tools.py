import asyncio
import json
from unittest.mock import patch

import pytest
from litellm.types.utils import ModelResponse

from kiln_ai import datamodel
from kiln_ai.adapters.eval.trace_tools.v1 import TOOLSET_V1
from kiln_ai.adapters.eval.trace_tools.v1.definitions import TOOL_DEFINITIONS
from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.render import (
    PreviewArgs,
    ReadArgs,
    TextArgs,
    render_overview,
)
from kiln_ai.adapters.eval.trace_tools.v1.search import SearchArgs
from kiln_ai.adapters.eval.trace_tools.v1.tools import build_tools, parse_args
from kiln_ai.adapters.eval.trace_tools.v1.view import build_view
from kiln_ai.adapters.ml_model_list import KilnModelProvider
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.json_schema import validate_tool_parameters_schema
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.tools.base_tool import ToolCallError, ToolCallResult

TOOL_NAMES = [
    "trace_overview",
    "preview_messages",
    "read_messages",
    "read_message_text",
    "search_trace",
]


@pytest.fixture
def coding_tools(coding_view):
    return dict(zip(TOOL_NAMES, build_tools(coding_view)))


async def test_tool_definitions_order_and_ids(coding_view):
    tools = build_tools(coding_view)
    assert [await tool.name() for tool in tools] == TOOL_NAMES
    assert [await tool.id() for tool in tools] == [
        f"kiln_unmanaged::trace_v1_{name}" for name in TOOL_NAMES
    ]
    for tool, definition in zip(tools, TOOL_DEFINITIONS):
        tool_definition = await tool.toolcall_definition()
        assert tool_definition["function"]["description"] == definition.description
        validate_tool_parameters_schema(tool_definition["function"]["parameters"])
        assert (
            tool_definition["function"]["parameters"]["additionalProperties"] is False
        )


async def test_tool_schema_is_a_copy(coding_view):
    first, second = build_tools(coding_view)[1], build_tools(coding_view)[1]
    schema = (await first.toolcall_definition())["function"]["parameters"]
    schema["properties"]["start"]["minimum"] = 99
    schema["properties"].clear()
    assert (await second.toolcall_definition())["function"]["parameters"]["properties"]
    assert TOOL_DEFINITIONS[1].parameters["properties"]["start"]["minimum"] == 1


@pytest.mark.parametrize(
    "tool_name, kwargs, expected",
    [
        ("trace_overview", {}, None),
        ("preview_messages", {}, PreviewArgs()),
        (
            "preview_messages",
            {"start": 2.0, "end": 5, "roles": ["user", "tool"], "preview_chars": 0},
            PreviewArgs(start=2, end=5, roles=("user", "tool"), preview_chars=0),
        ),
        ("read_messages", {}, ReadArgs()),
        (
            "read_messages",
            {"numbers": [3.0, 1], "parts": ["reasoning"], "max_chars": 40000},
            ReadArgs(numbers=(3, 1), parts=("reasoning",), max_chars=40_000),
        ),
        ("read_message_text", {"number": 4}, TextArgs(number=4)),
        (
            "read_message_text",
            {"number": 4, "part": "tool_calls", "offset": 10, "max_chars": 1},
            TextArgs(number=4, part="tool_calls", offset=10, max_chars=1),
        ),
        ("search_trace", {"pattern": "x"}, SearchArgs(pattern="x")),
        (
            "search_trace",
            {
                "pattern": "x",
                "regex": True,
                "case_sensitive": True,
                "roles": ["assistant"],
                "parts": ["reasoning", "content"],
                "context_chars": 2000,
                "start": 1,
                "end": 2,
                "count": 1000,
                "offset": 5,
            },
            SearchArgs(
                pattern="x",
                regex=True,
                case_sensitive=True,
                roles=("assistant",),
                parts=("reasoning", "content"),
                context_chars=2_000,
                start=1,
                end=2,
                count=1_000,
                offset=5,
            ),
        ),
    ],
)
def test_parse_args_defaults_and_coercion(tool_name, kwargs, expected):
    args = parse_args(tool_name, kwargs)
    assert args == expected
    for value in vars(args).values() if args is not None else ():
        assert not isinstance(value, float)


@pytest.mark.parametrize(
    "tool_name, kwargs",
    [
        ("trace_overview", {"x": 1}),
        ("preview_messages", {"preview_chars": 1001}),
        ("preview_messages", {"start": 0}),
        ("preview_messages", {"start": 1.5}),
        ("preview_messages", {"start": True}),
        ("preview_messages", {"roles": []}),
        ("read_messages", {"numbers": list(range(1, 1002))}),
        ("read_messages", {"max_chars": 0}),
        ("read_messages", {"parts": ["thoughts"]}),
        ("read_message_text", {}),
        ("read_message_text", {"number": 1, "offset": -1}),
        ("search_trace", {"pattern": ""}),
        ("search_trace", {"pattern": "x", "count": 1001}),
        ("search_trace", {"pattern": "x", "context_chars": 2001}),
        ("search_trace", {"pattern": "x", "regex": "yes"}),
    ],
)
def test_parse_args_invalid(tool_name, kwargs):
    # The rest of the message is jsonschema's wording, which v1 doesn't control.
    with pytest.raises(TraceToolUsageError, match=r"^Invalid arguments: "):
        parse_args(tool_name, kwargs)


def test_parse_args_ignores_duplicate_roles_and_parts():
    assert parse_args(
        "read_messages",
        {"roles": ["tool", "user", "tool"], "parts": ["content", "content"]},
    ) == ReadArgs(roles=("tool", "user"), parts=("content",))


def test_parse_args_numbers_and_range_conflict():
    with pytest.raises(
        TraceToolUsageError, match=r"^Use either numbers or start/end, not both\.$"
    ):
        parse_args("read_messages", {"numbers": [1], "end": 2})


def test_parse_args_unknown_tool():
    with pytest.raises(ValueError, match="No v1 trace tool named 'nope'"):
        parse_args("nope", {})


@pytest.mark.parametrize(
    "tool_name, kwargs",
    [
        ("trace_overview", {"unexpected": 1}),
        ("preview_messages", {"start": 99}),
        ("read_messages", {"numbers": [1], "start": 1}),
        ("read_message_text", {"number": 4, "part": "reasoning"}),
        ("search_trace", {"pattern": "(", "regex": True}),
        ("search_trace", {"pattern": "billing", "offset": 900}),
    ],
)
async def test_tool_usage_errors_are_tool_call_errors(coding_tools, tool_name, kwargs):
    with pytest.raises(TraceToolUsageError) as e:
        await coding_tools[tool_name].run(**kwargs)
    assert isinstance(e.value, ToolCallError)


@pytest.mark.parametrize(
    "tool_name, kwargs, expected_start",
    [
        ("trace_overview", {}, "Trace: 16 messages"),
        ("preview_messages", {"end": 1}, "#1 system 105"),
        ("read_messages", {"numbers": [5]}, "=== #5 tool result from grep"),
        ("read_message_text", {"number": 5}, "=== #5 tool result from grep"),
        ("search_trace", {"pattern": "legacy"}, "6 matches in 5 messages."),
    ],
)
async def test_tools_run_returns_output(
    coding_tools, tool_name, kwargs, expected_start
):
    result = await coding_tools[tool_name].run(None, **kwargs)
    assert isinstance(result, ToolCallResult)
    assert not result.is_error
    assert result.output.startswith(expected_start)


async def test_slow_tools_run_in_a_thread(coding_tools):
    calls = {
        "read_messages": {},
        "search_trace": {"pattern": "x"},
        "preview_messages": {},
    }
    with patch(
        "kiln_ai.adapters.eval.trace_tools.v1.tools.asyncio.to_thread",
        wraps=asyncio.to_thread,
    ) as to_thread:
        for name, kwargs in calls.items():
            await coding_tools[name].run(**kwargs)
    assert to_thread.call_count == 2


def test_toolset_v1_builds_tools_and_overview(coding_trace):
    view = TOOLSET_V1.build_view(coding_trace)
    assert TOOLSET_V1.version == 1
    assert TOOLSET_V1.render_overview(view) == render_overview(build_view(coding_trace))
    assert len(TOOLSET_V1.build_tools(view)) == 5


@pytest.mark.parametrize("method", ["render_overview", "build_tools"])
def test_toolset_v1_rejects_foreign_view(method):
    with pytest.raises(
        TypeError, match="needs a view built by its own build_view, got list"
    ):
        getattr(TOOLSET_V1, method)([])


def _model_turn(*calls: tuple[str, str, dict]) -> ModelResponse:
    return ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                        for call_id, name, arguments in calls
                    ],
                }
            }
        ],
    )


async def test_judge_loop_continues_after_tool_error(tmp_path, coding_view):
    project = datamodel.Project(name="judge_project", path=tmp_path / "project.kiln")
    project.save_to_file()
    task = datamodel.Task(parent=project, name="judge", instruction="Judge the trace.")
    task.save_to_file()
    adapter = LiteLlmAdapter(
        config=LiteLlmConfig(
            run_config_properties=KilnAgentRunConfigProperties(
                structured_output_mode=StructuredOutputMode.json_schema,
                model_name="gpt_4_1_mini",
                model_provider_name=ModelProviderName.openai,
                prompt_id="simple_prompt_builder",
            )
        ),
        kiln_task=task,
        base_adapter_config=AdapterConfig(
            allow_saving=False, unmanaged_tools=build_tools(coding_view)
        ),
    )
    turns = [
        _model_turn(
            ("bad_number", "read_messages", {"numbers": [99]}),
            ("bad_schema", "preview_messages", {"roles": ["robot"]}),
        ),
        _model_turn(("good", "read_messages", {"numbers": [5]})),
        ModelResponse(
            model="gpt-4o-mini",
            choices=[{"message": {"content": "Score: pass", "tool_calls": None}}],
        ),
    ]
    provider = KilnModelProvider(name=ModelProviderName.openai, model_id="gpt_4_1_mini")
    with (
        patch.object(adapter, "model_provider", return_value=provider),
        patch.object(adapter, "build_completion_kwargs", return_value={}),
        patch.object(
            adapter,
            "acompletion_checking_response",
            side_effect=[(turn, turn.choices[0]) for turn in turns],
        ),
    ):
        run = await adapter.invoke("Judge this trace.")

    assert run.output.output == "Score: pass"
    assert run.trace is not None
    tool_messages = {m["tool_call_id"]: m for m in run.trace if m["role"] == "tool"}
    assert tool_messages["bad_number"]["is_error"] is True
    assert tool_messages["bad_number"]["content"] == (
        "Message #99 doesn't exist. The trace has 16 messages (#1\u2013#16)."
    )
    assert tool_messages["bad_schema"]["is_error"] is True
    assert "don't match its schema" in tool_messages["bad_schema"]["content"]
    assert tool_messages["good"].get("is_error") is None
    assert tool_messages["good"]["content"].startswith(
        "=== #5 tool result from grep (content 33) ERROR ==="
    )
