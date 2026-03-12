from __future__ import annotations

from typing import Any, AsyncIterator, Optional, Union

import litellm
from litellm.types.utils import (
    ModelResponse,
    ModelResponseStream,
    TextCompletionResponse,
)


class StreamingCompletion:
    """
    Async iterable wrapper around ``litellm.acompletion`` with streaming.

    Yields ``ModelResponseStream`` chunks as they arrive.  After iteration
    completes, the assembled ``ModelResponse`` is available via the
    ``.response`` property.

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
        stream = await litellm.acompletion(*self._args, stream=True, **self._kwargs)

        async for chunk in stream:
            chunks.append(chunk)
            yield chunk

        self._response = litellm.stream_chunk_builder(chunks)
        self._iterated = True
