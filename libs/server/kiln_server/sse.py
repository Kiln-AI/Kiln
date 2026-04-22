import asyncio
import contextlib
import logging
from typing import (
    Any,
    AsyncGenerator,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    TypeVar,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# SSE comment lines start with ":" and are ignored by EventSource clients.
# Emitting one forces Starlette to call send() on the ASGI channel, which
# raises OSError (and in turn ClientDisconnect) when the client has gone away.
HEARTBEAT_COMMENT = ": keepalive\n\n"

DEFAULT_HEARTBEAT_SECONDS = 3.0


async def stream_with_heartbeat(
    source: AsyncIterable[T],
    format_chunk: Callable[[T], str],
    *,
    heartbeat_seconds: float | None = None,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncGenerator[str, None]:
    """Iterate `source`, yielding `format_chunk(item)` for each item.

    Two disconnect-detection mechanisms run in parallel:

    1. Heartbeat comments (`: keepalive\\n\\n`) are emitted every
       `heartbeat_seconds` of idleness. Emitting forces Starlette to call
       `send()`, which raises OSError/ClientDisconnect if the client is gone.
    2. If `is_disconnected` is provided, it is polled at each iteration; when
       it returns True, the generator returns immediately, triggering the
       source's aclose via the `finally` block.

    When the generator exits (for any reason), the underlying `source` has
    `aclose()` called on it. That's the lever that propagates cancellation
    to AsyncJobRunner's `finally` block and cancels its workers.
    """
    timeout = (
        heartbeat_seconds
        if heartbeat_seconds is not None
        else DEFAULT_HEARTBEAT_SECONDS
    )
    it: AsyncIterator[T] = source.__aiter__()

    async def next_item() -> T:
        return await it.__anext__()

    pending: asyncio.Task[T] | None = None
    try:
        while True:
            if is_disconnected is not None and await is_disconnected():
                logger.info("SSE stream: client disconnected, cancelling workers")
                return

            if pending is None:
                pending = asyncio.create_task(next_item())
            done, _ = await asyncio.wait({pending}, timeout=timeout)
            if pending in done:
                try:
                    item = pending.result()
                except StopAsyncIteration:
                    return
                pending = None
                yield format_chunk(item)
            else:
                logger.debug("SSE stream: idle for %.1fs, emitting heartbeat", timeout)
                yield HEARTBEAT_COMMENT
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with contextlib.suppress(BaseException):
                await pending
        if hasattr(source, "aclose"):
            with contextlib.suppress(BaseException):
                await _call_aclose(source)


async def _call_aclose(source: Any) -> None:
    """Call source.aclose() — extracted so the call site is a single await."""
    await source.aclose()
