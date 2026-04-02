from app.desktop.studio_server.chat import EventParser, tool_input_executor_is_server
from app.desktop.studio_server.test_chat.helpers import sse_text_delta


class TestEventParser:
    def test_passthrough_normal_events(self):
        raw = sse_text_delta("hi")
        result = EventParser().parse(raw)
        assert result.finish_tool_calls is False
        assert result.tool_input_events == []
        assert result.text_delta == "hi"
        assert result.chat_trace_id is None
        assert any(b"text-delta" in line for line in result.lines_to_forward)

    def test_invalid_ai_sdk_shape_skipped_for_extraction(self):
        raw = b'data: {"type":"text-delta","delta":"noid"}\n\n'
        result = EventParser().parse(raw)
        assert result.text_delta == ""
        assert any(b"text-delta" in line for line in result.lines_to_forward)

    def test_detects_ai_sdk_tool_calls_finish(self):
        raw = b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n'
        result = EventParser().parse(raw)
        assert result.finish_tool_calls is True
        assert result.tool_input_events == []
        assert result.chat_trace_id is None
        assert any(b"finish" in line for line in result.lines_to_forward)

    def test_handles_empty_input(self):
        result = EventParser().parse(b"")
        assert result.finish_tool_calls is False
        assert result.tool_input_events == []
        assert result.text_delta == ""
        assert result.chat_trace_id is None

    def test_detects_tool_input_available(self):
        raw = b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::multiply_numbers","input":{"a":2,"b":8}}\n\n'
        result = EventParser().parse(raw)
        assert result.chat_trace_id is None
        assert len(result.tool_input_events) == 1
        assert result.tool_input_events[0].toolCallId == "tc1"
        assert result.tool_input_events[0].toolName == "kiln_tool::multiply_numbers"
        assert result.tool_input_events[0].input == {"a": 2, "b": 8}
        assert any(b"tool-input-available" in line for line in result.lines_to_forward)

    def test_detects_tool_input_available_with_kiln_metadata_executor_server(self):
        raw = b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::multiply_numbers","input":{"a":2,"b":8},"kiln_metadata":{"executor":"server"}}\n\n'
        result = EventParser().parse(raw)
        assert len(result.tool_input_events) == 1
        ev = result.tool_input_events[0]
        assert ev.kiln_metadata.get("executor") == "server"
        assert tool_input_executor_is_server(ev) is True

    def test_accumulates_text_delta(self):
        raw = sse_text_delta("hello ") + sse_text_delta("world", text_id="text-test-2")
        result = EventParser().parse(raw)
        assert result.text_delta == "hello world"
        assert result.chat_trace_id is None

    def test_buffers_split_line(self):
        parser = EventParser()
        parser.parse(b'data: {"type":"text-delta","id":"t1","del')
        result = parser.parse(b'ta":"hi"}\n\n')
        assert result.text_delta == "hi"
        assert result.chat_trace_id is None
        assert any(b"text-delta" in line for line in result.lines_to_forward)

    def test_detects_kiln_chat_trace(self):
        tid = "d5804b96-851f-4ed6-acb6-b4107968a85a"
        raw = f'data: {{"type":"kiln_chat_trace","trace_id":"{tid}"}}\n\n'.encode()
        result = EventParser().parse(raw)
        assert result.chat_trace_id == tid
        assert any(b"kiln_chat_trace" in line for line in result.lines_to_forward)

    def test_kiln_chat_trace_last_wins_in_chunk(self):
        raw = (
            b'data: {"type":"kiln_chat_trace","trace_id":"first-id"}\n'
            b'data: {"type":"kiln_chat_trace","trace_id":"second-id"}\n\n'
        )
        result = EventParser().parse(raw)
        assert result.chat_trace_id == "second-id"
