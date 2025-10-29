import pytest

from kiln_ai.adapters.eval.eval_utils import EvalUtils
from kiln_ai.datamodel import Project, Task, TaskOutputRatingType, TaskRequirement
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalOutputScore,
)
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class TestEvalUtils:
    """Test cases for EvalUtils class"""

    def test_called_tool_names_from_trace_empty_trace(self):
        """Test with empty trace"""
        trace: list[ChatCompletionMessageParam] = []
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_no_tool_calls(self):
        """Test with trace containing no tool calls"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_single_tool_call(self):
        """Test with single tool call"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "content": "I'll check the weather for you.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "NYC"}',
                        },
                    }
                ],
            },
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == ["get_weather"]

    def test_called_tool_names_from_trace_multiple_tool_calls_same_tool(self):
        """Test with multiple calls to the same tool"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Check weather and time"},
            {
                "role": "assistant",
                "content": "I'll check both for you.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "NYC"}',
                        },
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "LA"}',
                        },
                    },
                ],
            },
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == ["get_weather"]

    def test_called_tool_names_from_trace_multiple_different_tools(self):
        """Test with multiple different tools"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Check weather and time"},
            {
                "role": "assistant",
                "content": "I'll check both for you.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "NYC"}',
                        },
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "get_time",
                            "arguments": '{"timezone": "EST"}',
                        },
                    },
                ],
            },
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == ["get_weather", "get_time"]

    def test_called_tool_names_from_trace_multiple_messages_with_tools(self):
        """Test with multiple assistant messages containing tool calls"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "First request"},
            {
                "role": "assistant",
                "content": "First response",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": '{"query": "first"}',
                        },
                    }
                ],
            },
            {"role": "user", "content": "Second request"},
            {
                "role": "assistant",
                "content": "Second response",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "calculate",
                            "arguments": '{"operation": "add"}',
                        },
                    }
                ],
            },
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == ["search", "calculate"]

    def test_called_tool_names_from_trace_mixed_messages(self):
        """Test with mixed message types (some with tools, some without)"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "Can you help me?"},
            {
                "role": "assistant",
                "content": "Sure!",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "help_tool",
                            "arguments": '{"task": "assist"}',
                        },
                    }
                ],
            },
            {"role": "user", "content": "Thanks"},
            {"role": "assistant", "content": "You're welcome!"},
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == ["help_tool"]

    def test_called_tool_names_from_trace_preserves_order(self):
        """Test that tool names are returned in the order they first appear"""
        trace: list[ChatCompletionMessageParam] = [
            {
                "role": "assistant",
                "content": "First tools",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "tool_c", "arguments": "{}"},
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "tool_a", "arguments": "{}"},
                    },
                ],
            },
            {
                "role": "assistant",
                "content": "Second tools",
                "tool_calls": [
                    {
                        "id": "call_3",
                        "type": "function",
                        "function": {"name": "tool_b", "arguments": "{}"},
                    },
                    {
                        "id": "call_4",
                        "type": "function",
                        "function": {"name": "tool_a", "arguments": "{}"},
                    },
                ],
            },
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == ["tool_c", "tool_a", "tool_b"]

    def test_called_tool_names_from_trace_no_assistant_messages(self):
        """Test with trace containing no assistant messages"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "System message"},
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_assistant_without_tool_calls(self):
        """Test with assistant messages that don't have tool_calls field"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "assistant", "content": "How can I help?"},
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_empty_tool_calls(self):
        """Test with assistant messages that have empty tool_calls"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!", "tool_calls": []},
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_complex_tool_call_structure(self):
        """Test with complex tool call structure"""
        trace: list[ChatCompletionMessageParam] = [
            {
                "role": "assistant",
                "content": "I'll help you with multiple tasks",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "complex_tool",
                            "arguments": '{"param1": "value1", "param2": {"nested": "value"}}',
                        },
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "simple_tool", "arguments": "{}"},
                    },
                ],
            },
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == ["complex_tool", "simple_tool"]


@pytest.fixture
def test_project(tmp_path):
    """Create a test project"""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()
    return project


@pytest.fixture
def test_task(test_project):
    """Create a test task"""
    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=test_project,
        requirements=[
            TaskRequirement(
                name="Quality",
                instruction="Rate the quality",
                type=TaskOutputRatingType.five_star,
            )
        ],
    )
    task.save_to_file()
    return task


@pytest.fixture
def test_eval_final_answer(test_task):
    """Create an eval with final_answer evaluation data type"""
    return Eval(
        name="Final Answer Eval",
        parent=test_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="quality",
                type=TaskOutputRatingType.five_star,
            )
        ],
        evaluation_data_type=EvalDataType.final_answer,
    )


@pytest.fixture
def test_eval_full_trace(test_task):
    """Create an eval with full_trace evaluation data type"""
    return Eval(
        name="Full Trace Eval",
        parent=test_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="quality",
                type=TaskOutputRatingType.five_star,
            )
        ],
        evaluation_data_type=EvalDataType.full_trace,
    )


@pytest.fixture
def test_eval_tool_call_list(test_task):
    """Create an eval with tool_call_list evaluation data type"""
    return Eval(
        name="Tool Call List Eval",
        parent=test_task,
        eval_set_filter_id="tag::tag1",
        eval_configs_filter_id="tag::tag2",
        output_scores=[
            EvalOutputScore(
                name="quality",
                type=TaskOutputRatingType.five_star,
            )
        ],
        evaluation_data_type=EvalDataType.tool_call_list,
    )


@pytest.fixture
def test_eval_config_final_answer(test_eval_final_answer):
    """Create an eval config for final_answer eval"""
    return EvalConfig(
        name="Final Answer Config",
        parent=test_eval_final_answer,
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1", "step2"]},
    )


@pytest.fixture
def test_eval_config_full_trace(test_eval_full_trace):
    """Create an eval config for full_trace eval"""
    return EvalConfig(
        name="Full Trace Config",
        parent=test_eval_full_trace,
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1", "step2"]},
    )


@pytest.fixture
def test_eval_config_tool_call_list(test_eval_tool_call_list):
    """Create an eval config for tool_call_list eval"""
    return EvalConfig(
        name="Tool Call List Config",
        parent=test_eval_tool_call_list,
        model_name="gpt-4",
        model_provider="openai",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1", "step2"]},
    )


class TestAdditionalEvalData:
    """Test cases for additional_eval_data function"""

    def test_additional_eval_data_none_trace(self, test_eval_config_final_answer):
        """Test with None trace"""
        full_trace, tool_call_list = EvalUtils.additional_eval_data(
            test_eval_config_final_answer, None
        )
        assert full_trace is None
        assert tool_call_list is None

    def test_additional_eval_data_empty_trace(self, test_eval_config_final_answer):
        """Test with empty trace"""
        full_trace, tool_call_list = EvalUtils.additional_eval_data(
            test_eval_config_final_answer, []
        )
        assert full_trace is None
        assert tool_call_list is None

    def test_additional_eval_data_final_answer_eval(
        self, test_eval_config_final_answer
    ):
        """Test with final_answer evaluation data type"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        full_trace, tool_call_list = EvalUtils.additional_eval_data(
            test_eval_config_final_answer, trace
        )
        assert full_trace is None
        assert tool_call_list is None

    def test_additional_eval_data_full_trace_eval(self, test_eval_config_full_trace):
        """Test with full_trace evaluation data type"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        full_trace, tool_call_list = EvalUtils.additional_eval_data(
            test_eval_config_full_trace, trace
        )
        assert full_trace is not None
        assert tool_call_list is None
        # Verify the trace is properly JSON serialized
        import json

        parsed_trace = json.loads(full_trace)
        assert parsed_trace == trace

    def test_additional_eval_data_tool_call_list_eval(
        self, test_eval_config_tool_call_list
    ):
        """Test with tool_call_list evaluation data type"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "content": "I'll check the weather for you.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "NYC"}',
                        },
                    }
                ],
            },
        ]
        full_trace, tool_call_list = EvalUtils.additional_eval_data(
            test_eval_config_tool_call_list, trace
        )
        assert full_trace is None
        assert tool_call_list is not None
        assert tool_call_list == ["get_weather"]

    def test_additional_eval_data_tool_call_list_multiple_tools(
        self, test_eval_config_tool_call_list
    ):
        """Test with tool_call_list evaluation data type and multiple tools"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Check weather and time"},
            {
                "role": "assistant",
                "content": "I'll check both for you.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "NYC"}',
                        },
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "get_time",
                            "arguments": '{"timezone": "EST"}',
                        },
                    },
                ],
            },
        ]
        full_trace, tool_call_list = EvalUtils.additional_eval_data(
            test_eval_config_tool_call_list, trace
        )
        assert full_trace is None
        assert tool_call_list is not None
        assert tool_call_list == ["get_weather", "get_time"]

    def test_additional_eval_data_tool_call_list_no_tools(
        self, test_eval_config_tool_call_list
    ):
        """Test with tool_call_list evaluation data type but no tool calls"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        full_trace, tool_call_list = EvalUtils.additional_eval_data(
            test_eval_config_tool_call_list, trace
        )
        assert full_trace is None
        assert tool_call_list is not None
        assert tool_call_list == []

    def test_additional_eval_data_full_trace_complex_trace(
        self, test_eval_config_full_trace
    ):
        """Test with full_trace evaluation data type and complex trace"""
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "content": "I'll check the weather for you.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "NYC"}',
                        },
                    }
                ],
            },
            {"role": "user", "content": "Thanks"},
            {"role": "assistant", "content": "You're welcome!"},
        ]
        full_trace, tool_call_list = EvalUtils.additional_eval_data(
            test_eval_config_full_trace, trace
        )
        assert full_trace is not None
        assert tool_call_list is None
        # Verify the trace is properly JSON serialized
        import json

        parsed_trace = json.loads(full_trace)
        assert parsed_trace == trace

    def test_additional_eval_data_eval_config_without_parent(self, test_task):
        """Test with eval config that has no parent eval"""
        # Create an eval config without a parent eval
        eval_config = EvalConfig(
            name="Orphaned Config",
            model_name="gpt-4",
            model_provider="openai",
            config_type=EvalConfigType.g_eval,
            properties={"eval_steps": ["step1", "step2"]},
        )

        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        full_trace, tool_call_list = EvalUtils.additional_eval_data(eval_config, trace)
        assert full_trace is None
        assert tool_call_list is None
