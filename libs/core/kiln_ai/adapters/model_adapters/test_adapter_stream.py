import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm.types.utils import (
    ChatCompletionMessageToolCall,
    Choices,
    Delta,
    Function,
    ModelResponse,
    ModelResponseStream,
    StreamingChoices,
)
from litellm.types.utils import Message as LiteLLMMessage

from kiln_ai.adapters.chat import ChatFormatter
from kiln_ai.adapters.model_adapters.adapter_stream import AdapterStream
from kiln_ai.adapters.model_adapters.stream_events import (
    ToolCallEvent,
    ToolCallEventType,
)
from kiln_ai.datamodel import Usage


def _make_streaming_chunk(
    content: str | None = None,
    finish_reason: str | None = None,
) -> ModelResponseStream:
    delta = Delta(content=content)
    choice = StreamingChoices(
        index=0,
        delta=delta,
        finish_reason=finish_reason,
    )
    return ModelResponseStream(id="test-stream", choices=[choice])


def _make_model_response(
    content: str = "Hello",
    tool_calls: list[ChatCompletionMessageToolCall] | None = None,
) -> ModelResponse:
    message = LiteLLMMessage(content=content, role="assistant")
    if tool_calls is not None:
        message.tool_calls = tool_calls
    choice = Choices(
        index=0,
        message=message,
        finish_reason="stop" if tool_calls is None else "tool_calls",
    )
    return ModelResponse(id="test-response", choices=[choice])


def _make_tool_call(
    call_id: str = "call_1",
    name: str = "add",
    arguments: dict[str, Any] | None = None,
) -> ChatCompletionMessageToolCall:
    args = json.dumps(arguments or {"a": 1, "b": 2})
    return ChatCompletionMessageToolCall(
        id=call_id,
        type="function",
        function=Function(name=name, arguments=args),
    )


class FakeChatFormatter(ChatFormatter):
    """A simple chat formatter that returns a single turn then None."""

    def __init__(self, num_turns: int = 1):
        self._turn_count = 0
        self._num_turns = num_turns

    def next_turn(self, prior_output: str | None):
        if self._turn_count >= self._num_turns:
            return None
        self._turn_count += 1
        turn = MagicMock()
        turn.messages = [MagicMock(role="user", content="test input")]
        turn.final_call = self._turn_count == self._num_turns
        return turn

    def intermediate_outputs(self):
        return {}


class FakeStreamingCompletion:
    """Mocks StreamingCompletion: yields chunks, then exposes .response"""

    def __init__(
        self,
        model_response: ModelResponse,
        chunks: list[ModelResponseStream] | None = None,
    ):
        self._chunks = chunks or [
            _make_streaming_chunk(content="Hel"),
            _make_streaming_chunk(content="lo"),
            _make_streaming_chunk(finish_reason="stop"),
        ]
        self._response = model_response

    @property
    def response(self):
        return self._response

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.build_completion_kwargs = AsyncMock(return_value={"model": "test"})
    adapter.usage_from_response = MagicMock(return_value=Usage())
    adapter.process_tool_calls = AsyncMock(return_value=(None, []))
    adapter._extract_and_validate_logprobs = MagicMock(return_value=None)
    adapter._extract_reasoning_to_intermediate_outputs = MagicMock()
    adapter.all_messages_to_trace = MagicMock(return_value=[])
    adapter.base_adapter_config = MagicMock()
    adapter.base_adapter_config.top_logprobs = None
    adapter.base_adapter_config.return_on_tool_call = False
    return adapter


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.model_id = "test-model"
    return provider


class TestAdapterStreamSimple:
    @pytest.mark.asyncio
    async def test_simple_content_response(self, mock_adapter, mock_provider):
        response = _make_model_response(content="Hello world")
        fake_stream = FakeStreamingCompletion(response)
        formatter = FakeChatFormatter()

        with patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            return_value=fake_stream,
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=formatter,
                initial_messages=[],
                top_logprobs=None,
            )

            events = []
            async for event in stream:
                events.append(event)

        chunks = [e for e in events if isinstance(e, ModelResponseStream)]
        assert len(chunks) == 3

        result = stream.result
        assert result.run_output.output == "Hello world"

    @pytest.mark.asyncio
    async def test_result_not_available_before_iteration(
        self, mock_adapter, mock_provider
    ):
        stream = AdapterStream(
            adapter=mock_adapter,
            provider=mock_provider,
            chat_formatter=FakeChatFormatter(),
            initial_messages=[],
            top_logprobs=None,
        )
        with pytest.raises(RuntimeError, match="not been iterated"):
            _ = stream.result


class TestAdapterStreamToolCalls:
    @pytest.mark.asyncio
    async def test_tool_call_yields_events(self, mock_adapter, mock_provider):
        tool_call = _make_tool_call(
            call_id="call_1", name="add", arguments={"a": 1, "b": 2}
        )
        tool_response = _make_model_response(content=None, tool_calls=[tool_call])
        final_response = _make_model_response(content="The answer is 3")

        tool_stream = FakeStreamingCompletion(
            tool_response,
            [_make_streaming_chunk(finish_reason="tool_calls")],
        )
        final_stream = FakeStreamingCompletion(
            final_response,
            [
                _make_streaming_chunk(content="The answer is 3"),
                _make_streaming_chunk(finish_reason="stop"),
            ],
        )

        streams_iter = iter([tool_stream, final_stream])

        mock_adapter.process_tool_calls = AsyncMock(
            return_value=(
                None,
                [{"role": "tool", "tool_call_id": "call_1", "content": "3"}],
            )
        )

        with patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            side_effect=lambda **kw: next(streams_iter),
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=FakeChatFormatter(),
                initial_messages=[],
                top_logprobs=None,
            )

            events = []
            async for event in stream:
                events.append(event)

        tool_events = [e for e in events if isinstance(e, ToolCallEvent)]
        assert len(tool_events) == 2

        input_event = next(
            e for e in tool_events if e.event_type == ToolCallEventType.INPUT_AVAILABLE
        )
        assert input_event.tool_call_id == "call_1"
        assert input_event.tool_name == "add"
        assert input_event.arguments == {"a": 1, "b": 2}

        output_event = next(
            e for e in tool_events if e.event_type == ToolCallEventType.OUTPUT_AVAILABLE
        )
        assert output_event.tool_call_id == "call_1"
        assert output_event.result == "3"

        assert stream.result.run_output.output == "The answer is 3"

    @pytest.mark.asyncio
    async def test_task_response_tool_call(self, mock_adapter, mock_provider):
        task_response_call = _make_tool_call(
            call_id="call_tr", name="task_response", arguments={"result": "42"}
        )
        response = _make_model_response(content=None, tool_calls=[task_response_call])

        fake_stream = FakeStreamingCompletion(
            response,
            [_make_streaming_chunk(finish_reason="tool_calls")],
        )

        mock_adapter.process_tool_calls = AsyncMock(
            return_value=('{"result": "42"}', [])
        )

        with patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            return_value=fake_stream,
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=FakeChatFormatter(),
                initial_messages=[],
                top_logprobs=None,
            )

            events = []
            async for event in stream:
                events.append(event)

        tool_events = [e for e in events if isinstance(e, ToolCallEvent)]
        assert len(tool_events) == 0

        assert stream.result.run_output.output == '{"result": "42"}'

    @pytest.mark.asyncio
    async def test_too_many_tool_calls_raises(self, mock_adapter, mock_provider):
        tool_call = _make_tool_call()
        response = _make_model_response(content=None, tool_calls=[tool_call])

        mock_adapter.process_tool_calls = AsyncMock(
            return_value=(
                None,
                [{"role": "tool", "tool_call_id": "call_1", "content": "ok"}],
            )
        )

        def make_stream(**kw):
            return FakeStreamingCompletion(
                response,
                [_make_streaming_chunk(finish_reason="tool_calls")],
            )

        with (
            patch(
                "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
                side_effect=make_stream,
            ),
            patch(
                "kiln_ai.adapters.model_adapters.adapter_stream.MAX_TOOL_CALLS_PER_TURN",
                2,
            ),
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=FakeChatFormatter(),
                initial_messages=[],
                top_logprobs=None,
            )

            with pytest.raises(RuntimeError, match="Too many tool calls"):
                async for _ in stream:
                    pass

    @pytest.mark.asyncio
    async def test_unparseable_tool_call_arguments(self, mock_adapter, mock_provider):
        bad_tool_call = ChatCompletionMessageToolCall(
            id="call_bad",
            type="function",
            function=Function(name="add", arguments="not json"),
        )
        response = _make_model_response(content=None, tool_calls=[bad_tool_call])
        final_response = _make_model_response(content="fallback")

        tool_stream = FakeStreamingCompletion(
            response,
            [_make_streaming_chunk(finish_reason="tool_calls")],
        )
        final_stream = FakeStreamingCompletion(
            final_response,
            [
                _make_streaming_chunk(content="fallback"),
                _make_streaming_chunk(finish_reason="stop"),
            ],
        )

        streams_iter = iter([tool_stream, final_stream])

        mock_adapter.process_tool_calls = AsyncMock(
            return_value=(
                None,
                [{"role": "tool", "tool_call_id": "call_bad", "content": "error"}],
            )
        )

        with patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            side_effect=lambda **kw: next(streams_iter),
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=FakeChatFormatter(),
                initial_messages=[],
                top_logprobs=None,
            )

            events = []
            async for event in stream:
                events.append(event)

        input_events = [
            e
            for e in events
            if isinstance(e, ToolCallEvent)
            and e.event_type == ToolCallEventType.INPUT_AVAILABLE
        ]
        assert len(input_events) == 1
        assert input_events[0].arguments is None
        assert "Failed to parse" in (input_events[0].error or "")


class TestAdapterStreamReturnOnToolCall:
    """Tests for return_on_tool_call=True behaviour in AdapterStream."""

    @pytest.mark.asyncio
    async def test_stops_at_tool_call_and_sets_trace(self, mock_adapter, mock_provider):
        tool_call = _make_tool_call(
            call_id="call_1", name="add", arguments={"a": 1, "b": 2}
        )
        tool_response = _make_model_response(content=None, tool_calls=[tool_call])
        fake_stream = FakeStreamingCompletion(
            tool_response,
            [_make_streaming_chunk(finish_reason="tool_calls")],
        )

        mock_adapter.base_adapter_config.return_on_tool_call = True
        trace_with_tool_calls = [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_1"}],
            },
        ]
        mock_adapter.all_messages_to_trace = MagicMock(
            return_value=trace_with_tool_calls
        )

        with patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            return_value=fake_stream,
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=FakeChatFormatter(),
                initial_messages=[],
                top_logprobs=None,
            )

            events = []
            async for event in stream:
                events.append(event)

        tool_events = [e for e in events if isinstance(e, ToolCallEvent)]
        assert len(tool_events) == 1
        assert tool_events[0].event_type == ToolCallEventType.INPUT_AVAILABLE
        assert tool_events[0].tool_call_id == "call_1"

        mock_adapter.process_tool_calls.assert_not_called()

        result = stream.result
        assert result.run_output.output == ""
        assert result.run_output.trace == trace_with_tool_calls

    @pytest.mark.asyncio
    async def test_task_response_tool_not_interrupted(
        self, mock_adapter, mock_provider
    ):
        """task_response tool calls should NOT trigger an interrupt."""
        task_response_call = _make_tool_call(
            call_id="call_tr", name="task_response", arguments={"result": "42"}
        )
        response = _make_model_response(content=None, tool_calls=[task_response_call])
        fake_stream = FakeStreamingCompletion(
            response,
            [_make_streaming_chunk(finish_reason="tool_calls")],
        )

        mock_adapter.base_adapter_config.return_on_tool_call = True
        mock_adapter.process_tool_calls = AsyncMock(
            return_value=('{"result": "42"}', [])
        )

        with patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            return_value=fake_stream,
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=FakeChatFormatter(),
                initial_messages=[],
                top_logprobs=None,
            )

            events = []
            async for event in stream:
                events.append(event)

        tool_events = [e for e in events if isinstance(e, ToolCallEvent)]
        assert len(tool_events) == 0

        result = stream.result
        assert result.run_output.output == '{"result": "42"}'

    @pytest.mark.asyncio
    async def test_normal_content_not_interrupted(self, mock_adapter, mock_provider):
        """When model returns content (no tool calls), no interrupt occurs."""
        mock_adapter.base_adapter_config.return_on_tool_call = True
        response = _make_model_response(content="Hello world")
        fake_stream = FakeStreamingCompletion(response)

        with patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            return_value=fake_stream,
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=FakeChatFormatter(),
                initial_messages=[],
                top_logprobs=None,
            )

            events = []
            async for event in stream:
                events.append(event)

        result = stream.result
        assert result.run_output.output == "Hello world"


class TestAdapterStreamEdgeCases:
    @pytest.mark.asyncio
    async def test_too_many_turns_raises(self, mock_adapter, mock_provider):
        formatter = FakeChatFormatter(num_turns=15)
        response = _make_model_response(content="ok")
        fake_stream = FakeStreamingCompletion(response)

        with (
            patch(
                "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
                return_value=fake_stream,
            ),
            patch(
                "kiln_ai.adapters.model_adapters.adapter_stream.MAX_CALLS_PER_TURN",
                2,
            ),
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=formatter,
                initial_messages=[],
                top_logprobs=None,
            )
            with pytest.raises(RuntimeError, match="Too many turns"):
                async for _ in stream:
                    pass

    @pytest.mark.asyncio
    async def test_empty_message_content_raises(self, mock_adapter, mock_provider):
        formatter = MagicMock()
        turn = MagicMock()
        turn.messages = [MagicMock(role="user", content=None)]
        turn.final_call = True
        formatter.next_turn = MagicMock(side_effect=[turn, None])

        stream = AdapterStream(
            adapter=mock_adapter,
            provider=mock_provider,
            chat_formatter=formatter,
            initial_messages=[],
            top_logprobs=None,
        )
        with pytest.raises(ValueError, match="Empty message content"):
            async for _ in stream:
                pass

    @pytest.mark.asyncio
    async def test_no_content_or_tool_calls_raises(self, mock_adapter, mock_provider):
        response = _make_model_response(content=None, tool_calls=None)
        response.choices[0].message.content = None
        fake_stream = FakeStreamingCompletion(
            response, [_make_streaming_chunk(finish_reason="stop")]
        )

        with patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            return_value=fake_stream,
        ):
            stream = AdapterStream(
                adapter=mock_adapter,
                provider=mock_provider,
                chat_formatter=FakeChatFormatter(),
                initial_messages=[],
                top_logprobs=None,
            )
            with pytest.raises(ValueError, match="no content or tool calls"):
                async for _ in stream:
                    pass


class TestValidateResponse:
    def test_valid_response(self):
        from kiln_ai.adapters.model_adapters.adapter_stream import _validate_response

        response = _make_model_response(content="hello")
        result, choice = _validate_response(response)
        assert result is response
        assert choice.message.content == "hello"

    def test_none_response_raises(self):
        from kiln_ai.adapters.model_adapters.adapter_stream import _validate_response

        with pytest.raises(RuntimeError, match="Expected ModelResponse"):
            _validate_response(None)

    def test_empty_choices_raises(self):
        from kiln_ai.adapters.model_adapters.adapter_stream import _validate_response

        response = ModelResponse(id="test", choices=[])
        with pytest.raises(RuntimeError, match="Expected ModelResponse"):
            _validate_response(response)


class TestFindToolName:
    def test_found(self):
        from kiln_ai.adapters.model_adapters.adapter_stream import _find_tool_name

        tc = ChatCompletionMessageToolCall(
            id="call_1",
            type="function",
            function=Function(name="add", arguments="{}"),
        )
        assert _find_tool_name([tc], "call_1") == "add"

    def test_not_found_returns_unknown(self):
        from kiln_ai.adapters.model_adapters.adapter_stream import _find_tool_name

        tc = ChatCompletionMessageToolCall(
            id="call_1",
            type="function",
            function=Function(name="add", arguments="{}"),
        )
        assert _find_tool_name([tc], "call_999") == "unknown"

    def test_name_is_none_returns_unknown(self):
        from kiln_ai.adapters.model_adapters.adapter_stream import _find_tool_name

        tc = ChatCompletionMessageToolCall(
            id="call_1",
            type="function",
            function=Function(name=None, arguments="{}"),
        )
        assert _find_tool_name([tc], "call_1") == "unknown"
