"""Shared definition of the synthetic ``kiln.tools`` module surface.

Stdlib only — no Pydantic / Kiln-model / DB / UI imports.

This is the single source of truth for the ``kiln`` / ``kiln.tools`` /
``kiln.async_tools`` surface that user code (``from kiln import tools``) sees.
Both the sandbox runtime (``sandbox/tools_api.py``) and the test shim
(``tool_testing/``) build the exact same module objects from here, so runtime
and tests can never drift — a test that catches ``kiln.tools.ToolCallError``
catches the same class the runtime raises.

The surface is parameterized over a *bridge* (see :class:`ToolBridge`): the
sandbox injects its real IPC bridge, the shim injects an in-process fake. This
module contains no execution, IPC, or subprocess behavior of its own.
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any, Protocol

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
# Bridge protocol
# ---------------------------------------------------------------------------


class ToolBridge(Protocol):
    """Behavior the synthetic modules require of a bridge.

    ``call`` receives the tool name plus the positional/keyword arguments the
    user passed to the proxy and returns the tool's raw output string (or raises
    one of the typed exceptions). ``list_tools`` returns the tool declarations.
    """

    def call(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str: ...

    def list_tools(self) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Synthetic module objects
# ---------------------------------------------------------------------------


class _SyncToolsModule(types.ModuleType):
    """``kiln.tools`` — sync callable proxies for tool calls."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        bridge: ToolBridge = self._bridge  # type: ignore[attr-defined]
        return lambda *args, **kw: bridge.call(name, args, kw)


class _AsyncToolsModule(types.ModuleType):
    """``kiln.async_tools`` — awaitable proxies for tool calls."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        bridge: ToolBridge = self._bridge  # type: ignore[attr-defined]

        async def _async_proxy(*args: Any, **kw: Any) -> str:
            return await asyncio.to_thread(bridge.call, name, args, kw)

        return _async_proxy


def build_tools_modules(
    bridge: ToolBridge,
) -> tuple[types.ModuleType, _SyncToolsModule, _AsyncToolsModule]:
    """Build the ``kiln`` / ``kiln.tools`` / ``kiln.async_tools`` modules.

    Wires the modules to *bridge* and returns them WITHOUT installing them into
    ``sys.modules`` (see :func:`install_tools_modules_for_bridge`).
    """
    # -- kiln --
    kiln_mod = types.ModuleType("kiln")
    kiln_mod.__path__ = []  # type: ignore[attr-defined]  # make it a package so `from kiln import ...` works

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

    return kiln_mod, tools_mod, async_tools_mod


def install_tools_modules_for_bridge(
    bridge: ToolBridge,
) -> tuple[types.ModuleType, _SyncToolsModule, _AsyncToolsModule]:
    """Build and install the synthetic ``kiln`` package into ``sys.modules``.

    Returns the built modules. After this call ``from kiln import tools`` (and
    ``kiln.async_tools``) resolves against these objects.
    """
    kiln_mod, tools_mod, async_tools_mod = build_tools_modules(bridge)

    sys.modules["kiln"] = kiln_mod
    sys.modules["kiln.tools"] = tools_mod
    sys.modules["kiln.async_tools"] = async_tools_mod

    return kiln_mod, tools_mod, async_tools_mod
