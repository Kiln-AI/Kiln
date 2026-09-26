import sys
from contextlib import contextmanager
from functools import partial
from typing import Awaitable, Callable, Generator

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

_has_exceptiongroups = True
if sys.version_info < (3, 11):
    try:
        from exceptiongroup import BaseExceptionGroup  # type: ignore[import-not-found]
    except ImportError:
        _has_exceptiongroups = False


@contextmanager
def collapse_excgroups() -> Generator[None, None, None]:
    """Collapse single-exception ExceptionGroups to the underlying exception.

    Vendored from starlette's ``starlette._utils.collapse_excgroups``, which was
    a private helper removed in Starlette 1.0. anyio task groups raise an
    ``ExceptionGroup``; when the group wraps exactly one exception we re-raise
    that exception directly so callers see the original error rather than a
    group wrapper.
    """
    try:
        yield
    except BaseException as exc:
        if _has_exceptiongroups:
            while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
                exc = exc.exceptions[0]
        raise exc


class CancellableStreamingResponse(StreamingResponse):
    """A StreamingResponse that reliably cancels its body iterator on client disconnect.

    Starlette 0.49+ added a `spec_version >= 2.4` fast path in `StreamingResponse.__call__`
    that skips `listen_for_disconnect` and relies on `send()` raising `OSError` on
    disconnect. Under uvicorn, `send()` silently returns on disconnect rather than
    raising, so the fast path never detects disconnect. This subclass restores the
    pre-regression behavior: always run `stream_response` concurrently with
    `listen_for_disconnect` in an anyio task group, so a client disconnect cancels
    the body iterator's `async for` / `try/finally` cleanup promptly.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return

        with collapse_excgroups():
            async with anyio.create_task_group() as task_group:

                async def wrap(func: Callable[[], Awaitable[None]]) -> None:
                    await func()
                    task_group.cancel_scope.cancel()

                task_group.start_soon(wrap, partial(self.stream_response, send))
                await wrap(partial(self.listen_for_disconnect, receive))

        if self.background is not None:
            await self.background()
