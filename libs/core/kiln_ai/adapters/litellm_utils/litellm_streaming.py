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

    Reasoning-only deltas are yielded on choice 0, with a blank line added where
    the reasoning summary part index changes; a reasoning item that follows a
    one-part item is not separated on the live stream. For OpenAI Responses
    streams, the assembled message carries the reasoning items, and its reasoning
    is every summary part of every item, separated by blank lines.

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
            summary_part = _move_summary_parts_to_choice_zero(chunk, summary_part)
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


def _move_summary_parts_to_choice_zero(
    chunk: ModelResponseStream, previous_part: int | None
) -> int | None:
    """Move each reasoning-only delta in ``chunk`` to choice 0, prefixing a blank
    line when its summary part differs from ``previous_part``. Returns the summary
    part of the last reasoning delta seen, to pass in with the next chunk.

    This undoes how LiteLLM bridges OpenAI Responses reasoning summaries into
    Chat Completions chunks. OpenAI streams a summary as
    ``response.reasoning_summary_text.delta`` events, each carrying ``item_id``,
    ``output_index``, ``summary_index`` and ``delta``. LiteLLM puts each delta on
    ``StreamingChoices(index=summary_index)`` and drops ``item_id`` and
    ``output_index``. See the ``response.reasoning_summary_text.delta`` branch of
    ``translate_responses_chunk_to_openai_stream``, in class
    ``OpenAiResponsesToChatCompletionStreamIterator`` of
    ``litellm/completion_extras/litellm_responses_transformation/transformation.py``
    (about line 1627 in LiteLLM 1.105.7). So summary part N arrives on choice N,
    and nothing separates the parts. A consumer that builds one message per choice
    would see reasoning spread over choices that carry no text or tool calls.

    This applies only to OpenAI Responses reasoning summaries. With one choice per
    request, every other provider streams reasoning on choice 0, so this changes
    nothing for them.

    Known limit: a new reasoning item restarts at part 0, and without ``item_id``
    its first delta looks like more of the previous part. So a one-part item
    followed by another item gets no blank line on the live stream.
    The saved text still has that blank line, because ``_apply_reasoning_items``
    rebuilds it from the reasoning items.

    Tests: ``TestSummaryPartsOnChoiceZero`` in ``test_litellm_streaming.py``, and
    ``test_streamed_reasoning_deltas_on_one_choice_with_part_breaks`` and
    ``test_multi_part_summary_saved_in_full`` in ``test_openai_responses_wire.py``.
    The wire tests run real LiteLLM, so they fail if an upgrade changes this.
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
