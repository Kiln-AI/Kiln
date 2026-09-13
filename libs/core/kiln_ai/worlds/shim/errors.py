"""The exception hierarchy a world package raises and the runtime translates.

Two kinds, and the split is the whole point. `WorldBug` is a programmer error: a tool
registered with an impossible signature, a fixture frozen from another schema, a call on a
destroyed instance. It is never shown to an agent. `ToolError` and its subclasses are what
the agent is meant to see, and they cross the wire as `{"code", "message", "details"}`.

The names keep Seahaven's spelling, `SeahavenError` included, so a world's
`except SeahavenError` survives the swap from this shim to Seahaven itself.
"""

from __future__ import annotations

from typing import Any


class SeahavenError(Exception):
    """Base of everything the runtime raises."""


class WorldBug(SeahavenError):
    """A programmer error in the world or its runtime. Never shown to an agent."""


class ToolError(SeahavenError):
    """A failure the agent should see, carried over the wire as a coded error."""

    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.code!r}, message={self.message!r}, "
            f"details={self.details!r})"
        )


class ArgumentError(ToolError):
    """Arguments that failed the tool's pydantic model."""

    def __init__(self, tool: str, violations: list[dict[str, str]]) -> None:
        rendered = "; ".join(f"{v['path']}: {v['message']}" for v in violations)
        super().__init__(
            "invalid_arguments", f"invalid arguments: {rendered}", violations
        )
        self.tool = tool
        self.violations = violations


class DbError(ToolError):
    """A SQLite failure. The engine's own text is kept on the exception but out of the
    message, so a stray database error never leaks schema detail to an agent; callers that
    want the text (the `controller_run_sql` control tool) read `sqlite_message`."""

    def __init__(
        self,
        sqlite_message: str,
        sqlite_code: int | None = None,
        refusals: tuple[str, ...] = (),
    ) -> None:
        message = f"not allowed: {refusals[0]}" if refusals else "database error"
        super().__init__("db_error", message, None)
        self.sqlite_message = sqlite_message
        self.sqlite_code = sqlite_code
        self.refusals = refusals

    def __repr__(self) -> str:
        return (
            f"DbError(sqlite_message={self.sqlite_message!r}, "
            f"sqlite_code={self.sqlite_code!r}, refusals={self.refusals!r})"
        )


class UnknownTool(ToolError):
    def __init__(self, name: str) -> None:
        super().__init__("unknown_tool", f"unknown tool: {name}", None)
        self.name = name


class WorldGap(ToolError):
    """The world does not implement this operation. Distinct from a product error: it marks
    a hole in the replica, which the validity harness counts rather than scores."""

    def __init__(
        self,
        operation: str,
        message: str = "not implemented in this world",
        details: Any = None,
    ) -> None:
        super().__init__(
            "world_gap",
            message,
            {"operation": operation} if details is None else details,
        )
        self.operation = operation
