"""Sandbox-side ``kiln.tools`` bridge for code-tool children.

Stdlib only — no Pydantic / Kiln-model / DB / UI imports.

The synthetic-module *surface* (proxy behavior, ``list_tools`` wiring, and the
typed exception classes ``ToolNotAllowed`` / ``ToolTimeout`` / ``ToolCallError``)
lives in :mod:`kiln_ai.sandbox.tools_surface`, shared with the test shim so
runtime and tests present one definition of ``kiln.tools``. This module provides
the sandbox's real IPC bridge and wires it into that surface.

Provides:

* ``ToolCallBridge``: thread-safe IPC bridge (child -> parent tool calls)
* ``install_tools_modules()``: injects ``kiln``, ``kiln.tools``,
  ``kiln.async_tools`` into ``sys.modules`` so user code can
  ``from kiln import tools`` etc.

``ToolNotAllowed`` / ``ToolTimeout`` / ``ToolCallError`` are re-exported here
(they are defined in ``tools_surface``) so existing importers keep working.
"""

from __future__ import annotations

import json
import threading
from multiprocessing import Queue
from typing import Any

from kiln_ai.sandbox.tools_surface import (
    ToolCallError,
    ToolNotAllowed,
    ToolTimeout,
    install_tools_modules_for_bridge,
)

__all__ = [
    "ToolCallBridge",
    "ToolCallError",
    "ToolNotAllowed",
    "ToolTimeout",
    "install_tools_modules",
]


# ---------------------------------------------------------------------------
# Child-side IPC bridge
# ---------------------------------------------------------------------------


class ToolCallBridge:
    """Thread-safe bridge between user code and the parent message pump.

    One bridge per child process.  ``call()`` and ``list_tools()`` may be
    invoked from any user thread (or from ``asyncio.to_thread`` for the
    async mirror).
    """

    def __init__(self, requests: Queue, responses: Queue) -> None:  # type: ignore[type-arg]
        self._requests = requests
        self._responses = responses
        self._lock = threading.Lock()
        self._next_id = 0
        self._pending: dict[int, _PendingCall] = {}

    # -- public API --

    def call(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        """Issue a ``tool_call`` to the parent; block until reply.

        Returns the raw output string on success.  Raises one of the
        typed exceptions on failure.
        """
        try:
            safe_kwargs = json.loads(json.dumps(kwargs, ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            raise ToolCallError(
                tool=name,
                message=f"tool arguments must be JSON-serializable: {exc}",
            ) from exc

        # Serialize positional args so the parent can produce a helpful error
        try:
            safe_args = json.loads(json.dumps(list(args), ensure_ascii=False))
        except (TypeError, ValueError):
            safe_args = [repr(a) for a in args]

        call_id, pending = self._allocate()
        msg: dict[str, Any] = {
            "type": "tool_call",
            "call_id": call_id,
            "tool_name": name,
            "arguments": safe_kwargs,
        }
        if safe_args:
            msg["positional_args"] = safe_args
        self._requests.put(msg)
        pending.event.wait()
        return self._resolve(call_id, name, pending)

    def list_tools(self) -> list[dict[str, Any]]:
        """Ask the parent for the allowlisted tool definitions."""
        call_id, pending = self._allocate()
        self._requests.put({"type": "list_tools", "call_id": call_id})
        pending.event.wait()
        msg = pending.result
        assert msg is not None
        if "ok_list" in msg:
            return msg["ok_list"]  # type: ignore[return-value]
        err = msg.get("error", {})
        raise ToolCallError(
            tool="list_tools",
            message=err.get("message", "unknown error"),
        )

    def start_dispatcher(self) -> None:
        """Start the daemon thread that reads parent replies."""
        t = threading.Thread(target=self._dispatch_loop, daemon=True)
        t.start()

    # -- internals --

    def _allocate(self) -> tuple[int, "_PendingCall"]:
        with self._lock:
            cid = self._next_id
            self._next_id += 1
            p = _PendingCall()
            self._pending[cid] = p
            return cid, p

    def _dispatch_loop(self) -> None:
        try:
            while True:
                try:
                    msg = self._responses.get()
                except (EOFError, OSError, ValueError):
                    break
                cid = msg.get("call_id")
                with self._lock:
                    pending = self._pending.pop(cid, None)
                if pending is not None:
                    pending.result = msg
                    pending.event.set()
        finally:
            with self._lock:
                orphans = list(self._pending.values())
                self._pending.clear()
            for p in orphans:
                p.result = {
                    "error": {
                        "kind": "call_error",
                        "message": "Parent process disconnected or queue closed.",
                    }
                }
                p.event.set()

    def _resolve(self, call_id: int, name: str, pending: "_PendingCall") -> str:
        msg = pending.result
        assert msg is not None
        if "ok" in msg:
            return msg["ok"]
        err = msg.get("error", {})
        kind = err.get("kind", "call_error")
        message = err.get("message", "unknown error")
        raw = err.get("raw")
        if kind == "not_allowed":
            raise ToolNotAllowed(tool=name, message=message)
        if kind == "timeout":
            raise ToolTimeout(tool=name, message=message)
        raise ToolCallError(tool=name, message=message, raw=raw)


class _PendingCall:
    __slots__ = ("event", "result")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Module installation
# ---------------------------------------------------------------------------


def install_tools_modules(
    requests: Queue,
    responses: Queue,  # type: ignore[type-arg]
) -> ToolCallBridge:
    """Create and install the synthetic ``kiln`` package into ``sys.modules``.

    Returns the bridge so the caller can inspect it if needed.
    """
    bridge = ToolCallBridge(requests, responses)
    bridge.start_dispatcher()
    install_tools_modules_for_bridge(bridge)
    return bridge
