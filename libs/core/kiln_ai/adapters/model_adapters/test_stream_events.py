from litellm.types.utils import (
    ChatCompletionDeltaToolCall,
    Delta,
    Function,
    ModelResponseStream,
    StreamingChoices,
)

from kiln_ai.adapters.model_adapters.stream_events import (
    AiSdkEventType,
    AiSdkStreamConverter,
    AiSdkStreamEvent,
    ToolCallEvent,
    ToolCallEventType,
)


def _make_tool_call_delta(
    index: int = 0,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> ChatCompletionDeltaToolCall:
    func = Function(name=name, arguments=arguments or "")
    tc = ChatCompletionDeltaToolCall(index=index, function=func)
    if call_id is not None:
        tc.id = call_id
    return tc


def _make_chunk(
    content: str | None = None,
    reasoning_content: str | None = None,
    tool_calls: list[ChatCompletionDeltaToolCall] | None = None,
    finish_reason: str | None = None,
) -> ModelResponseStream:
    delta = Delta(content=content, tool_calls=tool_calls)
    if reasoning_content is not None:
        delta.reasoning_content = reasoning_content
    choice = StreamingChoices(
        index=0,
        delta=delta,
        finish_reason=finish_reason,
    )
    return ModelResponseStream(id="test", choices=[choice])


class TestAiSdkStreamEvent:
    def test_model_dump(self):
        event = AiSdkStreamEvent(AiSdkEventType.START, {"messageId": "msg-123"})
        dump = event.model_dump()
        assert dump["type"] == "start"
        assert dump["messageId"] == "msg-123"


class TestAiSdkStreamConverter:
    def test_text_start_and_delta(self):
        converter = AiSdkStreamConverter()
        events = converter.convert_chunk(_make_chunk(content="Hello"))
        types = [e.type for e in events]
        assert AiSdkEventType.TEXT_START in types
        assert AiSdkEventType.TEXT_DELTA in types
        assert events[-1].payload["delta"] == "Hello"

    def test_text_delta_no_duplicate_start(self):
        converter = AiSdkStreamConverter()
        converter.convert_chunk(_make_chunk(content="Hello"))
        events = converter.convert_chunk(_make_chunk(content=" world"))
        types = [e.type for e in events]
        assert AiSdkEventType.TEXT_START not in types
        assert AiSdkEventType.TEXT_DELTA in types

    def test_reasoning_start_and_delta(self):
        converter = AiSdkStreamConverter()
        events = converter.convert_chunk(_make_chunk(reasoning_content="Thinking..."))
        types = [e.type for e in events]
        assert AiSdkEventType.REASONING_START in types
        assert AiSdkEventType.REASONING_DELTA in types

    def test_reasoning_ends_when_content_starts(self):
        converter = AiSdkStreamConverter()
        converter.convert_chunk(_make_chunk(reasoning_content="Thinking..."))
        events = converter.convert_chunk(_make_chunk(content="Answer"))
        types = [e.type for e in events]
        assert AiSdkEventType.REASONING_END in types
        assert AiSdkEventType.TEXT_START in types

    def test_reasoning_ends_when_tool_calls_start(self):
        converter = AiSdkStreamConverter()
        converter.convert_chunk(_make_chunk(reasoning_content="Thinking..."))

        tc_delta = _make_tool_call_delta(
            index=0, call_id="call_1", name="add", arguments='{"a":1}'
        )
        events = converter.convert_chunk(_make_chunk(tool_calls=[tc_delta]))
        types = [e.type for e in events]
        assert AiSdkEventType.REASONING_END in types

    def test_tool_call_input_start_and_delta(self):
        converter = AiSdkStreamConverter()

        tc_delta = _make_tool_call_delta(
            index=0, call_id="call_1", name="add", arguments='{"a":'
        )
        events = converter.convert_chunk(_make_chunk(tool_calls=[tc_delta]))
        types = [e.type for e in events]
        assert AiSdkEventType.TOOL_INPUT_START in types
        assert AiSdkEventType.TOOL_INPUT_DELTA in types

        start_event = next(
            e for e in events if e.type == AiSdkEventType.TOOL_INPUT_START
        )
        assert start_event.payload["toolCallId"] == "call_1"
        assert start_event.payload["toolName"] == "add"

    def test_finalize_closes_open_blocks(self):
        converter = AiSdkStreamConverter()
        converter.convert_chunk(_make_chunk(content="text"))
        events = converter.finalize()
        types = [e.type for e in events]
        assert AiSdkEventType.TEXT_END in types
        assert AiSdkEventType.FINISH in types

    def test_finalize_closes_reasoning(self):
        converter = AiSdkStreamConverter()
        converter.convert_chunk(_make_chunk(reasoning_content="thinking"))
        events = converter.finalize()
        types = [e.type for e in events]
        assert AiSdkEventType.REASONING_END in types

    def test_convert_tool_event_input_available(self):
        converter = AiSdkStreamConverter()
        event = ToolCallEvent(
            event_type=ToolCallEventType.INPUT_AVAILABLE,
            tool_call_id="call_1",
            tool_name="add",
            arguments={"a": 1, "b": 2},
        )
        events = converter.convert_tool_event(event)
        assert len(events) == 1
        assert events[0].type == AiSdkEventType.TOOL_INPUT_AVAILABLE
        assert events[0].payload["toolCallId"] == "call_1"
        assert events[0].payload["input"] == {"a": 1, "b": 2}

    def test_convert_tool_event_output_available(self):
        converter = AiSdkStreamConverter()
        event = ToolCallEvent(
            event_type=ToolCallEventType.OUTPUT_AVAILABLE,
            tool_call_id="call_1",
            tool_name="add",
            result="3",
        )
        events = converter.convert_tool_event(event)
        assert len(events) == 1
        assert events[0].type == AiSdkEventType.TOOL_OUTPUT_AVAILABLE
        assert events[0].payload["output"] == "3"

    def test_convert_tool_event_output_error(self):
        converter = AiSdkStreamConverter()
        event = ToolCallEvent(
            event_type=ToolCallEventType.OUTPUT_ERROR,
            tool_call_id="call_1",
            tool_name="add",
            error="Something went wrong",
        )
        events = converter.convert_tool_event(event)
        assert len(events) == 1
        assert events[0].type == AiSdkEventType.TOOL_OUTPUT_ERROR
        assert events[0].payload["errorText"] == "Something went wrong"

    def test_reasoning_not_interrupted_by_empty_content(self):
        # Minimax and similar models send chunks with both reasoning_content and
        # delta.content="" simultaneously. Empty content must not close reasoning
        # blocks or emit useless text-delta events.
        converter = AiSdkStreamConverter()

        chunk1 = _make_chunk(reasoning_content="The", content="")
        chunk2 = _make_chunk(reasoning_content=" user", content="")
        chunk3 = _make_chunk(reasoning_content=" is", content="")

        events1 = converter.convert_chunk(chunk1)
        events2 = converter.convert_chunk(chunk2)
        events3 = converter.convert_chunk(chunk3)

        all_types1 = [e.type for e in events1]
        all_types2 = [e.type for e in events2]
        all_types3 = [e.type for e in events3]

        # First chunk opens the reasoning block
        assert AiSdkEventType.REASONING_START in all_types1
        assert AiSdkEventType.REASONING_DELTA in all_types1
        # No text events from empty content
        assert AiSdkEventType.TEXT_START not in all_types1
        assert AiSdkEventType.TEXT_DELTA not in all_types1

        # Subsequent chunks must NOT re-open reasoning (no start) and must NOT
        # close reasoning with reasoning-end
        assert AiSdkEventType.REASONING_START not in all_types2
        assert AiSdkEventType.REASONING_END not in all_types2
        assert AiSdkEventType.REASONING_DELTA in all_types2
        assert AiSdkEventType.TEXT_DELTA not in all_types2

        assert AiSdkEventType.REASONING_START not in all_types3
        assert AiSdkEventType.REASONING_END not in all_types3
        assert AiSdkEventType.REASONING_DELTA in all_types3
        assert AiSdkEventType.TEXT_DELTA not in all_types3

    def test_reset_for_next_step(self):
        converter = AiSdkStreamConverter()
        converter._finish_reason = "tool_calls"
        converter._tool_calls_state = {
            0: {"id": "x", "name": "y", "arguments": "", "started": True}
        }
        converter.reset_for_next_step()
        assert converter._tool_calls_state == {}
        assert converter._finish_reason is None

    def test_finish_reason_in_finalize(self):
        converter = AiSdkStreamConverter()
        converter.convert_chunk(_make_chunk(content="done", finish_reason="stop"))
        events = converter.finalize()
        finish_events = [e for e in events if e.type == AiSdkEventType.FINISH]
        assert len(finish_events) == 1
        meta = finish_events[0].payload.get("messageMetadata", {})
        assert meta.get("finishReason") == "stop"

    def test_tool_input_start_reemitted_after_reset(self):
        """After reset_for_next_step, tool-input-start must fire again for index 0."""
        converter = AiSdkStreamConverter()

        tc_round1 = _make_tool_call_delta(
            index=0, call_id="call_r1", name="search", arguments='{"q":"hi"}'
        )
        events_r1 = converter.convert_chunk(_make_chunk(tool_calls=[tc_round1]))
        starts_r1 = [e for e in events_r1 if e.type == AiSdkEventType.TOOL_INPUT_START]
        assert len(starts_r1) == 1
        assert starts_r1[0].payload["toolCallId"] == "call_r1"

        converter.reset_for_next_step()

        tc_round2 = _make_tool_call_delta(
            index=0, call_id="call_r2", name="search", arguments='{"q":"world"}'
        )
        events_r2 = converter.convert_chunk(_make_chunk(tool_calls=[tc_round2]))
        starts_r2 = [e for e in events_r2 if e.type == AiSdkEventType.TOOL_INPUT_START]
        assert len(starts_r2) == 1, (
            "tool-input-start must be re-emitted for index 0 after reset"
        )
        assert starts_r2[0].payload["toolCallId"] == "call_r2"

    def test_tool_input_start_not_reemitted_without_reset(self):
        """Without reset, a second tool call at index 0 must NOT re-emit tool-input-start."""
        converter = AiSdkStreamConverter()

        tc_round1 = _make_tool_call_delta(
            index=0, call_id="call_r1", name="search", arguments='{"q":"hi"}'
        )
        converter.convert_chunk(_make_chunk(tool_calls=[tc_round1]))

        tc_round2 = _make_tool_call_delta(
            index=0, call_id="call_r2", name="search", arguments='{"q":"world"}'
        )
        events_r2 = converter.convert_chunk(_make_chunk(tool_calls=[tc_round2]))
        starts_r2 = [e for e in events_r2 if e.type == AiSdkEventType.TOOL_INPUT_START]
        assert len(starts_r2) == 0, (
            "Without reset, started=True blocks duplicate tool-input-start"
        )
