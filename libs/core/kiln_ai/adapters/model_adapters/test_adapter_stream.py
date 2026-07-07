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
from kiln_ai.datamodel import MessageUsage, Usage


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
    adapter.usage_from_response = MagicMock(return_value=MessageUsage())
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


class TestAdapterStreamPerMessageUsage:
    """Per-message usage capture mirroring the non-streaming adapter."""

    @pytest.mark.asyncio
    async def test_per_message_usage_captured_for_simple_response(
        self, mock_adapter, mock_provider
    ):
        """A single LLM call should record one per-message MessageUsage entry."""
        response = _make_model_response(content="Hello world")
        fake_stream = FakeStreamingCompletion(response)
        call_usage = MessageUsage(input_tokens=10, output_tokens=20, cost=0.1)
        mock_adapter.usage_from_response = MagicMock(return_value=call_usage)

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
            async for _ in stream:
                pass

        # all_messages_to_trace receives the per-message usage dict.
        call_args = mock_adapter.all_messages_to_trace.call_args
        message_usage_arg = call_args.args[2] if len(call_args.args) >= 3 else None
        assert message_usage_arg is not None
        assert len(message_usage_arg) == 1
        # The single entry maps the assistant message index to the call's MessageUsage.
        only_entry = next(iter(message_usage_arg.values()))
        assert only_entry == call_usage
        # Per-message records are MessageUsage — no latency field at all.
        assert isinstance(only_entry, MessageUsage)
        assert not isinstance(only_entry, Usage)

        # The running aggregate (Usage) sums the per-call usage and accumulates latency.
        assert stream.result.usage.input_tokens == 10
        assert stream.result.usage.output_tokens == 20
        assert stream.result.usage.cost == 0.1
        assert stream.result.usage.total_llm_latency_ms is not None

    @pytest.mark.asyncio
    async def test_per_message_usage_distinct_per_tool_call_loop(
        self, mock_adapter, mock_provider
    ):
        """Each LLM call inside a tool-call loop should record its own per-message Usage."""
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

        first_call_usage = MessageUsage(input_tokens=10, output_tokens=20, cost=0.1)
        second_call_usage = MessageUsage(input_tokens=11, output_tokens=22, cost=0.2)
        mock_adapter.usage_from_response = MagicMock(
            side_effect=[first_call_usage, second_call_usage]
        )
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
            async for _ in stream:
                pass

        message_usage_arg = mock_adapter.all_messages_to_trace.call_args.args[2]
        # Two assistant messages → two distinct per-message Usage entries.
        # (One tool-result message is also appended, but it's not an assistant.)
        assert len(message_usage_arg) == 2
        usages = list(message_usage_arg.values())
        assert first_call_usage in usages
        assert second_call_usage in usages
        # Running aggregate sums both calls.
        assert stream.result.usage.input_tokens == 21
        assert stream.result.usage.output_tokens == 42
        assert stream.result.usage.cost == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_per_message_usage_on_tool_call_interruption(
        self, mock_adapter, mock_provider
    ):
        """return_on_tool_call=True should still record per-message usage for the interrupting call."""
        tool_call = _make_tool_call(
            call_id="call_1", name="add", arguments={"a": 1, "b": 2}
        )
        tool_response = _make_model_response(content=None, tool_calls=[tool_call])
        fake_stream = FakeStreamingCompletion(
            tool_response,
            [_make_streaming_chunk(finish_reason="tool_calls")],
        )

        mock_adapter.base_adapter_config.return_on_tool_call = True
        interrupted_call_usage = MessageUsage(
            input_tokens=7, output_tokens=8, cost=0.05
        )
        mock_adapter.usage_from_response = MagicMock(
            return_value=interrupted_call_usage
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
            async for _ in stream:
                pass

        # Even on interruption, the assistant message produced before the
        # tool-call hand-off must have its per-message usage recorded.
        message_usage_arg = mock_adapter.all_messages_to_trace.call_args.args[2]
        assert len(message_usage_arg) == 1
        only_entry = next(iter(message_usage_arg.values()))
        assert only_entry == interrupted_call_usage

    @pytest.mark.asyncio
    async def test_per_message_usage_handles_empty_usage(
        self, mock_adapter, mock_provider
    ):
        """When the provider returns no usage, an empty Usage() is still attached."""
        response = _make_model_response(content="Hi")
        fake_stream = FakeStreamingCompletion(response)
        # Default fixture already returns MessageUsage() (all None) — be explicit.
        mock_adapter.usage_from_response = MagicMock(return_value=MessageUsage())

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
            async for _ in stream:
                pass

        # An entry exists (an empty Usage), it doesn't break finalization.
        message_usage_arg = mock_adapter.all_messages_to_trace.call_args.args[2]
        assert len(message_usage_arg) == 1
        only_entry = next(iter(message_usage_arg.values()))
        assert only_entry.input_tokens is None
        assert only_entry.cost is None


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


class TestStreamingSpendCredit:
    """The streaming turn credits the per-conversation spend ledger once per LLM
    call — the mirror of test_run_model_turn_credits_spend_ledger for the
    streaming path (adapter_stream.py). Assistant chat streams, so this is the
    path that actually runs in production."""

    CONVERSATION_ID = "1f2e3d4c-5b6a-4789-8abc-def012345678"

    @pytest.mark.asyncio
    async def test_credits_once_when_contextvar_set(self, mock_adapter, mock_provider):
        from kiln_ai.utils import spend_ledger

        response = _make_model_response(content="Hello world")
        fake_stream = FakeStreamingCompletion(response)
        formatter = FakeChatFormatter()
        call_usage = MessageUsage(
            input_tokens=10, output_tokens=5, total_tokens=15, cost=0.5
        )
        mock_adapter.usage_from_response = MagicMock(return_value=call_usage)

        token = spend_ledger.current_conversation_id.set(self.CONVERSATION_ID)
        try:
            with (
                patch(
                    "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
                    return_value=fake_stream,
                ),
                patch.object(
                    spend_ledger, "record_spend_for_current_conversation"
                ) as mock_record,
            ):
                stream = AdapterStream(
                    adapter=mock_adapter,
                    provider=mock_provider,
                    chat_formatter=formatter,
                    initial_messages=[],
                    top_logprobs=None,
                )
                async for _ in stream:
                    pass
        finally:
            spend_ledger.current_conversation_id.reset(token)

        mock_record.assert_called_once_with(0.5, 15)

    @pytest.mark.asyncio
    async def test_noop_when_contextvar_unset(self, mock_adapter, mock_provider):
        # The contextvar is unset (normal, non-assistant run). The credit call
        # still fires but is a no-op internally; verify it never records against
        # a conversation. (Uses the real ledger indirection with the contextvar
        # cleared, so a stray recording would create ledger state.)
        from kiln_ai.utils import spend_ledger

        response = _make_model_response(content="Hi")
        fake_stream = FakeStreamingCompletion(response)
        formatter = FakeChatFormatter()
        mock_adapter.usage_from_response = MagicMock(
            return_value=MessageUsage(total_tokens=3, cost=0.1)
        )

        # Ensure unset.
        token = spend_ledger.current_conversation_id.set(None)
        try:
            with (
                patch(
                    "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
                    return_value=fake_stream,
                ),
                patch.object(spend_ledger, "record_spend") as mock_record_spend,
            ):
                stream = AdapterStream(
                    adapter=mock_adapter,
                    provider=mock_provider,
                    chat_formatter=formatter,
                    initial_messages=[],
                    top_logprobs=None,
                )
                async for _ in stream:
                    pass
        finally:
            spend_ledger.current_conversation_id.reset(token)

        # record_spend is the ledger-mutating call; it must never fire with no
        # conversation in scope.
        mock_record_spend.assert_not_called()
