from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import MagicMock, patch

import litellm
import pytest
from litellm.types.utils import (
    Choices,
    Delta,
    Message,
    ModelResponse,
    ModelResponseStream,
    StreamingChoices,
)

from kiln_ai.adapters.litellm_utils.litellm_streaming import StreamingCompletion


def _make_chunk(content: str | None = None, finish_reason: str | None = None) -> Any:
    """Build a minimal chunk object matching litellm's streaming shape."""
    delta = SimpleNamespace(content=content, role="assistant")
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason, index=0)
    return SimpleNamespace(choices=[choice], id="chatcmpl-test", model="test-model")


async def _async_iter(items: List[Any]):
    """Turn a plain list into an async iterator."""
    for item in items:
        yield item


@pytest.fixture
def mock_acompletion():
    with patch("litellm.acompletion") as mock:
        yield mock


@pytest.fixture
def mock_chunk_builder():
    with patch("litellm.stream_chunk_builder") as mock:
        yield mock


class TestStreamingCompletion:
    async def test_yields_all_chunks(self, mock_acompletion, mock_chunk_builder):
        chunks = [_make_chunk("Hello"), _make_chunk(" world"), _make_chunk("!")]
        mock_acompletion.return_value = _async_iter(chunks)
        mock_chunk_builder.return_value = MagicMock(name="final_response")

        stream = StreamingCompletion(model="test", messages=[])
        received = [chunk async for chunk in stream]

        assert received == chunks

    async def test_response_available_after_iteration(
        self, mock_acompletion, mock_chunk_builder
    ):
        chunks = [_make_chunk("hi")]
        mock_acompletion.return_value = _async_iter(chunks)
        sentinel = MagicMock(name="final_response")
        mock_chunk_builder.return_value = sentinel

        stream = StreamingCompletion(model="test", messages=[])
        async for _ in stream:
            pass

        assert stream.response is sentinel

    async def test_response_raises_before_iteration(self):
        stream = StreamingCompletion(model="test", messages=[])
        with pytest.raises(RuntimeError, match="not been iterated"):
            _ = stream.response

    async def test_stream_kwarg_is_stripped(self, mock_acompletion, mock_chunk_builder):
        mock_acompletion.return_value = _async_iter([])
        mock_chunk_builder.return_value = None

        stream = StreamingCompletion(model="test", messages=[], stream=False)
        async for _ in stream:
            pass

        _, call_kwargs = mock_acompletion.call_args
        assert call_kwargs["stream"] is True

    async def test_passes_args_and_kwargs_through(
        self, mock_acompletion, mock_chunk_builder
    ):
        mock_acompletion.return_value = _async_iter([])
        mock_chunk_builder.return_value = None

        stream = StreamingCompletion(
            model="gpt-4", messages=[{"role": "user", "content": "hi"}], temperature=0.5
        )
        async for _ in stream:
            pass

        _, call_kwargs = mock_acompletion.call_args
        assert call_kwargs["model"] == "gpt-4"
        assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["stream"] is True

    async def test_chunks_passed_to_builder(self, mock_acompletion, mock_chunk_builder):
        chunks = [_make_chunk("a"), _make_chunk("b")]
        mock_acompletion.return_value = _async_iter(chunks)
        mock_chunk_builder.return_value = MagicMock()

        stream = StreamingCompletion(model="test", messages=[])
        async for _ in stream:
            pass

        mock_chunk_builder.assert_called_once_with(chunks)

    async def test_re_iteration_resets_state(
        self, mock_acompletion, mock_chunk_builder
    ):
        first_chunks = [_make_chunk("first")]
        second_chunks = [_make_chunk("second")]
        first_response = MagicMock(name="first_response")
        second_response = MagicMock(name="second_response")

        mock_acompletion.side_effect = [
            _async_iter(first_chunks),
            _async_iter(second_chunks),
        ]
        mock_chunk_builder.side_effect = [first_response, second_response]

        stream = StreamingCompletion(model="test", messages=[])

        async for _ in stream:
            pass
        assert stream.response is first_response

        async for _ in stream:
            pass
        assert stream.response is second_response

    async def test_empty_stream(self, mock_acompletion, mock_chunk_builder):
        mock_acompletion.return_value = _async_iter([])
        mock_chunk_builder.return_value = None

        stream = StreamingCompletion(model="test", messages=[])
        received = [chunk async for chunk in stream]

        assert received == []
        assert stream.response is None

    async def test_complete_response_instead_of_stream_raises(
        self, mock_acompletion, mock_chunk_builder
    ):
        mock_acompletion.return_value = ModelResponse()

        stream = StreamingCompletion(model="test", messages=[])
        with pytest.raises(RuntimeError, match="Expected a streamed response"):
            async for _ in stream:
                pass

        mock_chunk_builder.assert_not_called()

    async def test_stream_options_include_usage_added_by_default(
        self, mock_acompletion, mock_chunk_builder
    ):
        """Default ``stream_options`` must request usage so the assembled response carries it."""
        mock_acompletion.return_value = _async_iter([])
        mock_chunk_builder.return_value = None

        stream = StreamingCompletion(model="test", messages=[])
        async for _ in stream:
            pass

        _, call_kwargs = mock_acompletion.call_args
        assert call_kwargs["stream_options"] == {"include_usage": True}

    async def test_stream_options_include_usage_merged_with_caller_options(
        self, mock_acompletion, mock_chunk_builder
    ):
        """Caller-provided ``stream_options`` keys must survive; ``include_usage`` is forced on."""
        mock_acompletion.return_value = _async_iter([])
        mock_chunk_builder.return_value = None

        stream = StreamingCompletion(
            model="test",
            messages=[],
            stream_options={"some_other_flag": True},
        )
        async for _ in stream:
            pass

        _, call_kwargs = mock_acompletion.call_args
        assert call_kwargs["stream_options"] == {
            "some_other_flag": True,
            "include_usage": True,
        }

    async def test_caller_provided_include_usage_false_is_overridden(
        self, mock_acompletion, mock_chunk_builder
    ):
        """Streaming usage tracking is mandatory; an explicit ``False`` is overridden."""
        mock_acompletion.return_value = _async_iter([])
        mock_chunk_builder.return_value = None

        stream = StreamingCompletion(
            model="test",
            messages=[],
            stream_options={"include_usage": False},
        )
        async for _ in stream:
            pass

        _, call_kwargs = mock_acompletion.call_args
        assert call_kwargs["stream_options"]["include_usage"] is True

    async def test_stream_options_none_treated_as_empty(
        self, mock_acompletion, mock_chunk_builder
    ):
        """Passing ``stream_options=None`` must not crash — treated as empty."""
        mock_acompletion.return_value = _async_iter([])
        mock_chunk_builder.return_value = None

        stream = StreamingCompletion(model="test", messages=[], stream_options=None)
        async for _ in stream:
            pass

        _, call_kwargs = mock_acompletion.call_args
        assert call_kwargs["stream_options"] == {"include_usage": True}


def _stream_chunk(
    index: int = 0, finish_reason: str | None = None, **delta: Any
) -> ModelResponseStream:
    return ModelResponseStream(
        id="chatcmpl-test",
        model="gpt-5.4",
        choices=[
            StreamingChoices(
                index=index, finish_reason=finish_reason, delta=Delta(**delta)
            )
        ],
    )


def _reasoning_item(item_id: str, *texts: str) -> dict[str, Any]:
    return {
        "type": "reasoning",
        "id": item_id,
        "encrypted_content": f"ENC_{item_id}",
        "summary": [{"type": "summary_text", "text": text} for text in texts],
    }


async def _stream_with_real_builder(
    chunks: list[ModelResponseStream],
) -> tuple[list[ModelResponseStream], ModelResponse]:
    with patch("litellm.acompletion", return_value=_async_iter(chunks)):
        stream = StreamingCompletion(model="gpt-5.4", messages=[])
        received = [chunk async for chunk in stream]
    assert isinstance(stream.response, ModelResponse)
    return received, stream.response


def _built_message(response: ModelResponse) -> Message:
    choice = response.choices[0]
    assert isinstance(choice, Choices)
    return choice.message


class TestReasoningNormalization:
    async def test_reasoning_delta_moves_to_choice_zero(self):
        received, _ = await _stream_with_real_builder(
            [
                _stream_chunk(index=0, reasoning_content="Part zero."),
                _stream_chunk(index=1, reasoning_content="Part one."),
            ]
        )

        assert [chunk.choices[0].index for chunk in received] == [0, 0]

    async def test_blank_line_inserted_when_summary_part_changes(self):
        received, _ = await _stream_with_real_builder(
            [
                _stream_chunk(index=0, reasoning_content="Part "),
                _stream_chunk(index=0, reasoning_content="zero."),
                _stream_chunk(index=1, reasoning_content="Part "),
                _stream_chunk(index=1, reasoning_content="one."),
                _stream_chunk(index=0, reasoning_content="Next item."),
            ]
        )

        assert [chunk.choices[0].delta.reasoning_content for chunk in received] == [
            "Part ",
            "zero.",
            "\n\nPart ",
            "one.",
            "\n\nNext item.",
        ]

    async def test_content_and_tool_call_deltas_keep_their_index(self):
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "add", "arguments": "{}"},
            "index": 0,
        }
        received, _ = await _stream_with_real_builder(
            [
                _stream_chunk(index=1, reasoning_content="Thinking."),
                _stream_chunk(index=2, content="Text", reasoning_content="r"),
                _stream_chunk(index=3, tool_calls=[tool_call], reasoning_content="r"),
            ]
        )

        assert [chunk.choices[0].index for chunk in received] == [0, 2, 3]
        assert [chunk.choices[0].delta.reasoning_content for chunk in received] == [
            "Thinking.",
            "r",
            "r",
        ]

    async def test_part_tracking_resets_on_re_iteration(self):
        first = [_stream_chunk(index=1, reasoning_content="First run.")]
        second = [_stream_chunk(index=0, reasoning_content="Second run.")]

        with patch(
            "litellm.acompletion", side_effect=[_async_iter(first), _async_iter(second)]
        ):
            stream = StreamingCompletion(model="gpt-5.4", messages=[])
            [chunk async for chunk in stream]
            received = [chunk async for chunk in stream]

        assert received[0].choices[0].delta.reasoning_content == "Second run."


class TestReasoningItems:
    async def test_terminal_reasoning_items_attached_to_built_message(self):
        items = [_reasoning_item("rs_1", "Part zero.")]
        _, response = await _stream_with_real_builder(
            [
                _stream_chunk(reasoning_content="Part zero."),
                _stream_chunk(content="Answer"),
                _stream_chunk(reasoning_items=items),
                _stream_chunk(finish_reason="stop"),
            ]
        )

        message = _built_message(response)
        assert message.reasoning_items == items
        assert message.content == "Answer"

    async def test_reasoning_content_joined_across_items_and_parts(self):
        items = [
            _reasoning_item("rs_1", "**Plan**\n\nFirst part. ", " Second part."),
            _reasoning_item("rs_2", "Third part, second item."),
        ]
        _, response = await _stream_with_real_builder(
            [
                _stream_chunk(index=0, reasoning_content="**Plan**\n\nFirst part. "),
                _stream_chunk(index=1, reasoning_content=" Second part."),
                _stream_chunk(index=0, reasoning_content="Third part, second item."),
                _stream_chunk(content="Answer"),
                _stream_chunk(reasoning_items=items, finish_reason="stop"),
            ]
        )

        assert _built_message(response).reasoning_content == (
            "**Plan**\n\nFirst part.\n\nSecond part.\n\nThird part, second item."
        )

    async def test_reasoning_items_without_summary_text_keep_streamed_reasoning(self):
        items = [_reasoning_item("rs_1"), _reasoning_item("rs_2", "")]
        _, response = await _stream_with_real_builder(
            [
                _stream_chunk(reasoning_content="Streamed."),
                _stream_chunk(content="Answer"),
                _stream_chunk(reasoning_items=items, finish_reason="stop"),
            ]
        )

        message = _built_message(response)
        assert message.reasoning_items == items
        assert message.reasoning_content == "Streamed."

    async def test_no_reasoning_items_leaves_built_response_unchanged(self):
        chunks = [
            _stream_chunk(reasoning_content="Thinking."),
            _stream_chunk(content="Answer", finish_reason="stop"),
        ]
        expected = litellm.stream_chunk_builder(copy.deepcopy(chunks))
        assert isinstance(expected, ModelResponse)

        _, response = await _stream_with_real_builder(chunks)

        message = _built_message(response)
        assert getattr(message, "reasoning_items", None) is None
        assert message.reasoning_content == _built_message(expected).reasoning_content
        assert message.content == "Answer"
