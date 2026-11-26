"""MCP progress updates while a long API call runs, so that agents with short
tool timeouts keep waiting."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# progress, total, message: the arguments of the SDK's Context.report_progress.
ProgressSender = Callable[[float, float | None, str | None], Awaitable[None]]


async def run_with_progress(
    work: Coroutine[Any, Any, T],
    send: ProgressSender | None,
    *,
    label: str,
    interval: float = 2.0,
) -> T:
    """Await `work`, sending a progress update every `interval` seconds until
    it ends. A failing `send` stops the updates, never the work. Cancelling the
    caller cancels `work`."""
    task = asyncio.ensure_future(work)
    ticks = 0
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=interval)
            if done:
                return task.result()
            ticks += 1
            if send is not None:
                try:
                    await send(
                        float(ticks),
                        None,
                        f"{label}: still running, {int(ticks * interval)} s",
                    )
                except Exception:
                    logger.debug(
                        "Progress update failed; not sending more", exc_info=True
                    )
                    send = None
    finally:
        if not task.done():
            task.cancel()
