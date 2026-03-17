from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

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
