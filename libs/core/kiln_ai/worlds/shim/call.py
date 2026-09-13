"""One tool call, and the chain it runs through.

`invoke` is the innermost handler: validate the arguments, run the function inside the
instance's transaction, serialise the result. Serialisation happens *inside* the
transaction on purpose — a result the wire cannot carry is a bug in the tool, and the
write it made should not survive it.

Middleware wraps that. `build_chain` composes the world's middleware outside-in and
normalises `ctx.call` at every hop, so a middleware that rewrites arguments hands the next
layer a context that agrees with the call it is passing on.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Sequence

from pydantic_core import to_jsonable_python

from .ctx import Ctx
from .errors import WorldBug
from .tool import Tool

Handler = Callable[[Ctx, "Call"], Any]
Middleware = Callable[[Ctx, "Call", Handler], Any]
StartupHook = Callable[..., None]


@dataclass(frozen=True)
class Call:
    name: str
    arguments: Mapping[str, Any]
    tool: Tool

    def with_arguments(self, **changes: Any) -> "Call":
        return replace(self, arguments={**self.arguments, **changes})


def build_chain(middlewares: Sequence[Middleware], innermost: Handler) -> Handler:
    handler = innermost
    for middleware in reversed(list(middlewares)):
        handler = _wrap(middleware, handler)
    return handler


def _wrap(middleware: Middleware, next_handler: Handler) -> Handler:
    def handler(ctx: Ctx, call: Call) -> Any:
        def forward(inner_ctx: Ctx, inner_call: Call) -> Any:
            if inner_ctx.call is not inner_call:
                inner_ctx = inner_ctx.with_call(inner_call)
            return next_handler(inner_ctx, inner_call)

        if ctx.call is not call:
            ctx = ctx.with_call(call)
        return middleware(ctx, call, forward)

    return handler


def invoke(ctx: Ctx, call: Call) -> Any:
    arguments = call.tool.validate(call.arguments)
    if not call.tool.transaction:
        return _serialise(call, call.tool.fn(ctx, **arguments))
    with ctx.db.transaction():
        return _serialise(call, call.tool.fn(ctx, **arguments))


def _serialise(call: Call, result: Any) -> Any:
    if isinstance(result, (bytes, bytearray)):
        raise WorldBug(
            f"tool '{call.name}' returned bytes; a tool result has to be JSON, so encode it"
        )
    try:
        return to_jsonable_python(result)
    except Exception as e:
        raise WorldBug(
            f"tool '{call.name}' returned a result that is not JSON: {e}"
        ) from e
