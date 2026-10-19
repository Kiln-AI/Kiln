"""In-process fake bridge backing the ``kiln_tools`` test fixture.

Stdlib + kiln_ai only. No subprocess, no IPC, no real tool execution — this is
the test-only counterpart to ``sandbox/tools_api.py``'s ``ToolCallBridge``. It
satisfies the same :class:`~kiln_ai.sandbox.tools_surface.ToolBridge` protocol,
so the synthetic ``kiln`` / ``kiln.tools`` / ``kiln.async_tools`` modules built
from the shared surface behave identically whether they wrap the real IPC bridge
(runtime) or this fake (tests).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Union

from kiln_ai.sandbox.tools_surface import (
    ToolCallError,
    ToolNotAllowed,
)

# A registered reply: a literal string (returned verbatim) or a callable that
# receives the call's keyword arguments and returns a string.
ToolReply = Union[str, Callable[..., str]]


@dataclass
class RecordedToolCall:
    """One recorded tool call: the tool ``name`` and its keyword ``arguments``."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


class FakeToolBridge:
    """Registry-backed stand-in for the sandbox tool-call bridge.

    Authors drive it through the ``kiln_tools`` fixture:

    * :meth:`set` registers a reply (static string or callable) for a tool name.
    * :meth:`set_error` registers an exception a tool name should raise.
    * :attr:`calls` records every call in order for assertions.
    * :meth:`list_tools` returns the registered declarations.

    An unregistered name raises :class:`ToolNotAllowed`, matching the runtime's
    allowlist miss.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._replies: dict[str, ToolReply] = {}
        self._errors: dict[str, BaseException] = {}
        self._declarations: dict[str, dict[str, Any]] = {}
        self.calls: list[RecordedToolCall] = []

    # -- registration --

    def set(
        self,
        name: str,
        reply: ToolReply,
        *,
        declaration: dict[str, Any] | None = None,
    ) -> None:
        """Register *reply* for tool *name*.

        *reply* is a ``str`` (returned verbatim, matching the string-returns
        contract) or a callable ``(**kwargs) -> str``. Optionally attach a
        *declaration* dict surfaced by :meth:`list_tools`.
        """
        if not isinstance(reply, str) and not callable(reply):
            raise TypeError(
                f"kiln_tools.set('{name}', ...): reply must be a str or a "
                f"callable (**kwargs) -> str, got {type(reply).__name__}"
            )
        with self._lock:
            self._replies[name] = reply
            self._errors.pop(name, None)
            self._declarations[name] = self._build_declaration(name, declaration)

    def set_error(
        self,
        name: str,
        exc: BaseException,
        *,
        declaration: dict[str, Any] | None = None,
    ) -> None:
        """Register *exc* to be raised whenever tool *name* is called."""
        if not isinstance(exc, BaseException):
            raise TypeError(
                f"kiln_tools.set_error('{name}', ...): exc must be an exception "
                f"instance, got {type(exc).__name__}"
            )
        with self._lock:
            self._errors[name] = exc
            self._replies.pop(name, None)
            self._declarations[name] = self._build_declaration(name, declaration)

    def reset(self) -> None:
        """Clear all registrations and the call log (per-test reset)."""
        with self._lock:
            self._replies.clear()
            self._errors.clear()
            self._declarations.clear()
            self.calls.clear()

    # -- ToolBridge protocol --

    def call(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        """Resolve a tool call against the registry.

        Records the call first, then dispatches in the same order the runtime
        does (``tools/code_tool.py``): the not-allowed check comes FIRST, so an
        unregistered name raises :class:`ToolNotAllowed` regardless of arguments;
        only for a registered name do positional arguments raise
        :class:`ToolCallError` (tools are keyword-only); then a registered error
        is raised, otherwise the static or callable reply is returned.
        """
        with self._lock:
            self.calls.append(RecordedToolCall(name=name, arguments=dict(kwargs)))
            error = self._errors.get(name)
            has_reply = name in self._replies
            reply = self._replies.get(name)

        # A name is "registered" if it has either a reply or an error. Mirror the
        # runtime's not-allowed branch, which precedes the positional-args branch.
        if not has_reply and error is None:
            raise ToolNotAllowed(
                tool=name,
                message=(
                    f"Tool '{name}' is not registered with kiln_tools. Register a "
                    f"reply with kiln_tools.set('{name}', ...) or an error with "
                    f"kiln_tools.set_error('{name}', ...)."
                ),
            )

        if args:
            raise ToolCallError(
                tool=name,
                message=(
                    f"Tool '{name}' was called with positional arguments; tool "
                    f"calls must use keyword arguments."
                ),
            )

        if error is not None:
            raise error

        if callable(reply):
            result = reply(**kwargs)
            if not isinstance(result, str):
                raise TypeError(
                    f"kiln_tools reply callable for '{name}' must return a str, "
                    f"got {type(result).__name__}"
                )
            return result

        # A non-callable reply is a str (enforced at set()).
        assert isinstance(reply, str)
        return reply

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the registered tool declarations (name + supplied fields)."""
        with self._lock:
            return [dict(decl) for decl in self._declarations.values()]

    # -- internals --

    @staticmethod
    def _build_declaration(
        name: str, declaration: dict[str, Any] | None
    ) -> dict[str, Any]:
        decl: dict[str, Any] = dict(declaration) if declaration else {}
        decl["name"] = name
        return decl
