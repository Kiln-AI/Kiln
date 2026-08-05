"""Synthetic ``kiln.tools`` / ``kiln.async_tools`` modules for code-tool children.

Stdlib only — no Pydantic / Kiln-model / DB / UI imports.

Provides:

* Typed exceptions: ``ToolNotAllowed``, ``ToolTimeout``, ``ToolCallError``
* ``ToolCallBridge``: thread-safe IPC bridge (child -> parent tool calls)
* ``install_tools_modules()``: injects ``kiln``, ``kiln.tools``,
  ``kiln.async_tools`` into ``sys.modules`` so user code can
  ``from kiln import tools`` etc.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import types
from multiprocessing import Queue
from typing import Any

# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class ToolNotAllowed(Exception):
    """The requested tool is not in this code tool's allowlist."""

    def __init__(self, tool: str, message: str) -> None:
        self.tool = tool
        self.message = message
        self.raw: str | None = None
        super().__init__(message)


class ToolTimeout(Exception):
    """A nested tool call timed out."""

    def __init__(self, tool: str, message: str) -> None:
        self.tool = tool
        self.message = message
        self.raw: str | None = None
        super().__init__(message)


class ToolCallError(Exception):
    """Catch-all for nested tool-call failures."""

    def __init__(self, tool: str, message: str, raw: str | None = None) -> None:
        self.tool = tool
        self.message = message
        self.raw = raw
        super().__init__(message)


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

    # -- kiln --
    kiln_mod = types.ModuleType("kiln")
    kiln_mod.__path__ = []  # make it a package so `from kiln import ...` works

    # -- kiln.tools (sync) --
    tools_mod = _SyncToolsModule("kiln.tools")
    tools_mod._bridge = bridge  # type: ignore[attr-defined]
    tools_mod.ToolNotAllowed = ToolNotAllowed  # type: ignore[attr-defined]
    tools_mod.ToolTimeout = ToolTimeout  # type: ignore[attr-defined]
    tools_mod.ToolCallError = ToolCallError  # type: ignore[attr-defined]
    tools_mod.list_tools = bridge.list_tools  # type: ignore[attr-defined]

    # -- kiln.async_tools (async) --
    async_tools_mod = _AsyncToolsModule("kiln.async_tools")
    async_tools_mod._bridge = bridge  # type: ignore[attr-defined]
    async_tools_mod.ToolNotAllowed = ToolNotAllowed  # type: ignore[attr-defined]
    async_tools_mod.ToolTimeout = ToolTimeout  # type: ignore[attr-defined]
    async_tools_mod.ToolCallError = ToolCallError  # type: ignore[attr-defined]

    async def _async_list_tools() -> list[dict[str, Any]]:
        return await asyncio.to_thread(bridge.list_tools)

    async_tools_mod.list_tools = _async_list_tools  # type: ignore[attr-defined]

    kiln_mod.tools = tools_mod  # type: ignore[attr-defined]
    kiln_mod.async_tools = async_tools_mod  # type: ignore[attr-defined]

    sys.modules["kiln"] = kiln_mod
    sys.modules["kiln.tools"] = tools_mod
    sys.modules["kiln.async_tools"] = async_tools_mod

    return bridge


class _SyncToolsModule(types.ModuleType):
    """``kiln.tools`` — sync callable proxies for tool calls."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        bridge: ToolCallBridge = self._bridge  # type: ignore[attr-defined]
        return lambda *args, **kw: bridge.call(name, args, kw)


class _AsyncToolsModule(types.ModuleType):
    """``kiln.async_tools`` — awaitable proxies for tool calls."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        bridge: ToolCallBridge = self._bridge  # type: ignore[attr-defined]

        async def _async_proxy(*args: Any, **kw: Any) -> str:
            return await asyncio.to_thread(bridge.call, name, args, kw)

        return _async_proxy
