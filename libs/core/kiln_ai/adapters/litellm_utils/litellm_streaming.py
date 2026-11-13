from __future__ import annotations

from typing import Any, AsyncIterator, Optional, Union

import litellm
from litellm.types.llms.openai import ChatCompletionReasoningItem
from litellm.types.utils import (
    Choices,
    ModelResponse,
    ModelResponseStream,
    TextCompletionResponse,
)

_SUMMARY_PART_SEPARATOR = "\n\n"


class StreamingCompletion:
    """
    Async iterable wrapper around ``litellm.acompletion`` with streaming.

    Yields ``ModelResponseStream`` chunks as they arrive.  After iteration
    completes, the assembled ``ModelResponse`` is available via the
    ``.response`` property.

    Reasoning-only deltas are yielded on choice 0, and each new reasoning summary
    part starts with a blank line. For OpenAI Responses streams, the assembled
    message carries the reasoning items and every summary part as its reasoning.

    Usage::

        stream = StreamingCompletion(model=..., messages=...)
        async for chunk in stream:
            # handle chunk however you like (print, log, send over WS, …)
            pass
        final = stream.response   # fully assembled ModelResponse
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs = dict(kwargs)
        kwargs.pop("stream", None)
        # LiteLLM's streaming responses don't include a usage block by
        # default — ``stream_options={"include_usage": True}`` is required
        # for the final assembled ModelResponse to carry token counts (and
        # downstream cost). Force it on; merge with caller-provided
        # ``stream_options`` without clobbering unrelated keys, but always
        # override ``include_usage`` since usage tracking is mandatory.
        caller_stream_options = kwargs.get("stream_options") or {}
        kwargs["stream_options"] = {
            **caller_stream_options,
            "include_usage": True,
        }
        self._args = args
        self._kwargs = kwargs
        self._response: Optional[Union[ModelResponse, TextCompletionResponse]] = None
        self._iterated: bool = False

    @property
    def response(self) -> Optional[Union[ModelResponse, TextCompletionResponse]]:
        """The final assembled response. Only available after iteration."""
        if not self._iterated:
            raise RuntimeError(
                "StreamingCompletion has not been iterated yet. "
                "Use 'async for chunk in stream:' before accessing .response"
            )
        return self._response

    async def __aiter__(self) -> AsyncIterator[ModelResponseStream]:
        self._response = None
        self._iterated = False

        chunks: list[ModelResponseStream] = []
        reasoning_items: list[ChatCompletionReasoningItem] | None = None
        summary_part: int | None = None
        stream = await litellm.acompletion(*self._args, stream=True, **self._kwargs)
        if isinstance(stream, ModelResponse):
            raise RuntimeError(
                "Expected a streamed response from LiteLLM, got a complete ModelResponse."
            )

        async for chunk in stream:
            reasoning_items = _reasoning_items_from_chunk(chunk) or reasoning_items
            summary_part = _normalize_reasoning_delta(chunk, summary_part)
            chunks.append(chunk)
            yield chunk

        response = litellm.stream_chunk_builder(chunks)
        if reasoning_items and isinstance(response, ModelResponse):
            _apply_reasoning_items(response, reasoning_items)
        self._response = response
        self._iterated = True


def _reasoning_items_from_chunk(
    chunk: ModelResponseStream,
) -> list[ChatCompletionReasoningItem] | None:
    """The OpenAI reasoning items on this chunk, if any. LiteLLM sends them only on
    the terminal chunk of a /v1/responses stream, and stream_chunk_builder drops them."""
    for choice in chunk.choices:
        items = getattr(choice.delta, "reasoning_items", None)
        if items:
            return items
    return None


def _normalize_reasoning_delta(
    chunk: ModelResponseStream, previous_part: int | None
) -> int | None:
    """Move reasoning-only deltas to choice 0, starting each new summary part with
    a blank line. Returns the summary part of the last reasoning delta seen.

    LiteLLM streams OpenAI summary part N on choice index N, with no separator
    between parts. A new reasoning item restarts at part 0, so a one-part item
    followed by another isn't separated here; the saved text is rebuilt from the
    reasoning items instead.
    """
    for choice in chunk.choices:
        delta = choice.delta
        reasoning = getattr(delta, "reasoning_content", None)
        if not reasoning or delta.content or delta.tool_calls:
            continue
        part = choice.index
        choice.index = 0
        if previous_part is not None and part != previous_part:
            delta.reasoning_content = _SUMMARY_PART_SEPARATOR + reasoning
        previous_part = part
    return previous_part


def _apply_reasoning_items(
    response: ModelResponse, reasoning_items: list[ChatCompletionReasoningItem]
) -> None:
    """Put the streamed reasoning items back on the built message, so LiteLLM can
    replay them on the next tool round, and set its reasoning text to every summary
    part of every item."""
    if not response.choices or not isinstance(response.choices[0], Choices):
        return
    message = response.choices[0].message
    message.reasoning_items = reasoning_items
    summary_texts = [
        part.get("text", "").strip()
        for item in reasoning_items
        for part in item.get("summary", [])
    ]
    joined = _SUMMARY_PART_SEPARATOR.join(text for text in summary_texts if text)
    if joined:
        message.reasoning_content = joined
