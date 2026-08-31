"""Shared entry-point caller for sandbox children.

Stdlib only — no Pydantic / Kiln-model / DB / UI imports.

Handles both ``def`` and ``async def`` entry points transparently:
if the call returns a coroutine, it is driven to completion with
``asyncio.run()``.
"""

import asyncio
import inspect
from typing import Any, Callable


def call_entrypoint(fn: Callable, kwargs: dict) -> Any:
    """Invoke *fn* with *kwargs*, transparently awaiting if async.

    If *fn* is a regular function its return value is returned as-is.
    If *fn* is an ``async def`` (or returns a coroutine for any other
    reason, e.g. a decorated/partial wrapper), ``asyncio.run()`` is
    used to drive the coroutine in the child's main thread.

    This helper is shared between code-eval scorers and code-tool
    ``run()`` entry points.
    """
    result = fn(**kwargs)
    if inspect.iscoroutine(result):
        result = asyncio.run(result)
    return result
