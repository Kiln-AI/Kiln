"""Tools for the harness, not for the agent.

Every world carries three. They read the instance and never write it, they are absent from
`list_tools`, and the wire refuses them unless the server was started with
`--include-control-tools`. They are how a grader learns what an episode actually did:
`controller_changes` is the net diff, `controller_digest` a hash of the tracked state, and
`controller_run_sql` a read-only query for anything the first two do not answer.

They bypass the middleware chain, the transaction and the process gate: a control call is an
observation of the world, not an action in it, and must not be reshaped by the world's own
error handling or blocked behind agent traffic. It does not count as a step either, so
`final_state.step_count` stays the number of decisions the agent made.
"""

from __future__ import annotations

import sqlite3
from contextvars import ContextVar
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from pydantic_core import to_jsonable_python

from .changes import convert
from .ctx import Ctx
from .db import SqlValue
from .errors import ToolError, WorldBug
from .tool import Tool

if TYPE_CHECKING:
    from .instances import Instance

_CURRENT: ContextVar["Instance"] = ContextVar("shim_control_instance")


def _instance() -> "Instance":
    try:
        return _CURRENT.get()
    except LookupError as e:
        raise WorldBug(
            "a control tool ran outside control.dispatch; it has no instance to read"
        ) from e


def controller_run_sql(
    ctx: Ctx, sql: str, params: list[SqlValue] | None = None
) -> dict[str, Any]:
    """Run one read-only SQL statement against this instance and return its rows."""
    db = _instance().inspect()
    try:
        cursor = db.conn.execute(sql, tuple(params or ()))
        fetched = cursor.fetchall()
    except sqlite3.Error as e:
        # Unlike DbError, the engine's own text is the point here: the caller is the
        # harness, debugging its own query.
        raise ToolError(
            "db_error", str(e), {"sqlite_code": getattr(e, "sqlite_errorcode", None)}
        ) from e
    columns = [column[0] for column in cursor.description or ()]
    return {
        "columns": columns,
        "rows": [[convert(value) for value in row] for row in fetched],
        "row_count": len(fetched),
        "truncated": False,
    }


def controller_changes(ctx: Ctx) -> list[dict[str, Any]]:
    """Every row this instance has inserted, updated or deleted since it started."""
    return [change.to_dict() for change in _instance().changes()]


def controller_digest(ctx: Ctx) -> str:
    """A SHA-256 over this instance's tracked rows: equal digests mean equal state."""
    return _instance().digest()


def control_tools() -> list[Tool]:
    return [
        replace(Tool.from_function(function), control=True)
        for function in (controller_run_sql, controller_changes, controller_digest)
    ]


def dispatch(instance: "Instance", ctx: Ctx) -> Any:
    call = ctx.call
    if call is None:
        raise WorldBug("control dispatch needs a call on the context")
    arguments = call.tool.validate(call.arguments)
    token = _CURRENT.set(instance)
    try:
        return to_jsonable_python(call.tool.fn(ctx, **arguments))
    finally:
        _CURRENT.reset(token)
