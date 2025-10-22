from kiln_ai.adapters.eval.eval_utils import EvalUtils


class TestEvalUtils:
    """Test cases for EvalUtils class"""

    def test_called_tool_names_from_trace_empty_trace(self):
        """Test with empty trace"""
        trace = []
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_no_tool_calls(self):
        """Test with trace containing no tool calls"""
        trace = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_single_tool_call(self):
        """Test with single tool call"""
        trace = [
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
        trace = [
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
        trace = [
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
        trace = [
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
        trace = [
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
        trace = [
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
        trace = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "System message"},
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_assistant_without_tool_calls(self):
        """Test with assistant messages that don't have tool_calls field"""
        trace = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "assistant", "content": "How can I help?"},
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_empty_tool_calls(self):
        """Test with assistant messages that have empty tool_calls"""
        trace = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!", "tool_calls": []},
        ]
        result = EvalUtils.called_tool_names_from_trace(trace)
        assert result == []

    def test_called_tool_names_from_trace_complex_tool_call_structure(self):
        """Test with complex tool call structure"""
        trace = [
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
