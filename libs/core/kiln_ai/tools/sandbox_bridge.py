"""Shared parent-side sandbox bridge.

Owns everything the parent needs to drive one bridged child run: the bounded
concurrency pool, the nesting-depth cap, the spawn+pump loop, and the nested
tool-call server (allowlist resolution, kwarg validation, error-kind mapping,
recording). Both :class:`~kiln_ai.tools.code_tool.PythonCodeTool` and the code-eval
adapter build on this.

Parent-side only — may import the Kiln stack (NOT stdlib-only like the child in
``sandbox/``).
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import multiprocessing
import queue
import threading
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable

from kiln_ai.datamodel.json_schema import validate_schema_with_value_error
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.sandbox.spawn import start_process_with_light_main
from kiln_ai.tools.base_tool import ToolCallContext

logger = logging.getLogger(__name__)

CODE_SANDBOX_MAX_CONCURRENCY = 16
"""Maximum concurrent top-level sandbox invocations (process-wide).

Shared by code tools and code judges. Raises code tools' prior bound of 8 as a
side effect of unifying the pool (arch §3.4)."""

_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    "_code_sandbox_depth", default=0
)

_semaphore: asyncio.Semaphore | None = None
_semaphore_init_lock = threading.Lock()


async def _get_semaphore() -> asyncio.Semaphore:
    """Lazily create the semaphore inside the running event loop."""
    global _semaphore
    if _semaphore is None:
        with _semaphore_init_lock:
            if _semaphore is None:
                _semaphore = asyncio.Semaphore(CODE_SANDBOX_MAX_CONCURRENCY)
    sem = _semaphore
    assert sem is not None
    return sem


@dataclass
class ToolCallLogEntry:
    tool_name: str
    arguments: dict[str, Any]
    output_preview: str
    is_error: bool
    duration_ms: int


@dataclass
class BridgeResult:
    """Raw outcome of one bridged child run — no result interpretation.

    Exactly one of a ``result`` message, a timeout, or a crash terminates the run.
    ``result_msg`` carries the child's final ``result`` dict verbatim (or a synthetic
    error dict for the depth cap); callers interpret it into their own result type.
    """

    result_msg: dict[str, Any] | None = None
    timed_out: bool = False
    crashed: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0


class NestedToolServer:
    """Handles nested tool-call IPC for one bridged run.

    Owns allowlist resolution and the ``serve`` dispatcher (formerly
    ``PythonCodeTool._serve``). Parameterized on the run's allowlist, project,
    task, calling context, and optional recorder.
    """

    def __init__(
        self,
        allowlist: list[ToolId],
        project: Project | None,
        task: Task | None,
        context: ToolCallContext | None,
        recorder: Callable[[ToolCallLogEntry], None] | None = None,
    ):
        self._allowlist = allowlist
        self._project = project
        self._task = task
        self._context = context
        self._recorder = recorder
        self._name_map: dict[str, list[ToolId]] | None = None

    async def serve(
        self,
        msg: dict[str, Any],
        responses: multiprocessing.Queue[dict[str, Any]],
    ) -> None:
        call_id = msg["call_id"]

        if msg["type"] == "list_tools":
            try:
                tools_info = await self.tools_info()
                responses.put(
                    {"type": "tool_result", "call_id": call_id, "ok_list": tools_info}
                )
            except Exception as exc:
                responses.put(
                    {
                        "type": "tool_result",
                        "call_id": call_id,
                        "error": {
                            "kind": "call_error",
                            "message": str(exc),
                            "raw": None,
                            "available": None,
                        },
                    }
                )
            return

        tool_name = msg["tool_name"]
        arguments = msg["arguments"]
        positional_args: list[Any] = msg.get("positional_args", [])
        start = monotonic()

        try:
            name_map = await self.name_map()
            available_names = sorted(name_map.keys())

            tool_ids = name_map.get(tool_name)
            if tool_ids is None:
                err_msg = (
                    f"Tool '{tool_name}' is not available. "
                    f"Available tools: {available_names}."
                )
                responses.put(
                    {
                        "type": "tool_result",
                        "call_id": call_id,
                        "error": {
                            "kind": "not_allowed",
                            "message": err_msg,
                            "raw": None,
                            "available": available_names,
                        },
                    }
                )
                self._record(tool_name, arguments, "not allowed", True, start)
                return

            if len(tool_ids) > 1:
                responses.put(
                    {
                        "type": "tool_result",
                        "call_id": call_id,
                        "error": {
                            "kind": "call_error",
                            "message": f"Ambiguous tool name '{tool_name}' — resolves to multiple allowlisted tools.",
                            "raw": None,
                            "available": None,
                        },
                    }
                )
                self._record(tool_name, arguments, "ambiguous", True, start)
                return

            tool_id = tool_ids[0]

            from kiln_ai.tools.tool_registry import tool_from_id_and_project

            tool = tool_from_id_and_project(
                tool_id, project=self._project, task=self._task
            )

            tool_def = await tool.toolcall_definition()
            params_schema = tool_def["function"]["parameters"]
            params_desc = _render_params_schema(params_schema)

            if positional_args:
                err_msg = (
                    f"Tool '{tool_name}' must be called with keyword arguments, "
                    f"e.g. tools.{tool_name}({_example_kwargs(params_schema)}). "
                    f"Expected parameters: {params_desc}."
                )
                responses.put(
                    {
                        "type": "tool_result",
                        "call_id": call_id,
                        "error": {
                            "kind": "call_error",
                            "message": err_msg,
                            "raw": None,
                            "available": None,
                        },
                    }
                )
                self._record(tool_name, arguments, err_msg, True, start)
                return

            schema_str = json.dumps(params_schema, ensure_ascii=False)
            try:
                validate_schema_with_value_error(
                    arguments,
                    schema_str,
                    f"Invalid arguments for tool '{tool_name}'.",
                )
            except ValueError as exc:
                err_msg = f"{exc} Expected parameters: {params_desc}."
                responses.put(
                    {
                        "type": "tool_result",
                        "call_id": call_id,
                        "error": {
                            "kind": "call_error",
                            "message": err_msg,
                            "raw": None,
                            "available": None,
                        },
                    }
                )
                self._record(tool_name, arguments, err_msg, True, start)
                return

            result = await tool.run(self._context, **arguments)

            if result.is_error:
                from kiln_ai.tools.code_tool import PythonCodeTool

                is_timeout = isinstance(tool, PythonCodeTool) and "timed out" in (
                    result.output or ""
                )
                kind = "timeout" if is_timeout else "call_error"
                responses.put(
                    {
                        "type": "tool_result",
                        "call_id": call_id,
                        "error": {
                            "kind": kind,
                            "message": result.error_message or result.output,
                            "raw": result.output,
                            "available": None,
                        },
                    }
                )
                self._record(tool_name, arguments, result.output, True, start)
            else:
                responses.put(
                    {
                        "type": "tool_result",
                        "call_id": call_id,
                        "ok": result.output,
                    }
                )
                self._record(tool_name, arguments, result.output, False, start)

        except asyncio.TimeoutError as exc:
            logger.warning(
                "Nested sandbox call timed out for '%s': %s",
                tool_name,
                exc,
            )
            responses.put(
                {
                    "type": "tool_result",
                    "call_id": call_id,
                    "error": {
                        "kind": "timeout",
                        "message": str(exc) or f"Tool '{tool_name}' timed out",
                        "raw": None,
                        "available": None,
                    },
                }
            )
            self._record(tool_name, arguments, str(exc), True, start)

        except Exception as exc:
            logger.warning(
                "Nested sandbox call failed for '%s': %s",
                tool_name,
                exc,
            )
            responses.put(
                {
                    "type": "tool_result",
                    "call_id": call_id,
                    "error": {
                        "kind": "call_error",
                        "message": str(exc),
                        "raw": None,
                        "available": None,
                    },
                }
            )
            self._record(tool_name, arguments, str(exc), True, start)

    def _record(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        output: str,
        is_error: bool,
        start: float,
    ) -> None:
        if self._recorder is None:
            return
        duration_ms = int((monotonic() - start) * 1000)
        preview = output[:1024] if output else ""
        self._recorder(
            ToolCallLogEntry(
                tool_name=tool_name,
                arguments=arguments,
                output_preview=preview,
                is_error=is_error,
                duration_ms=duration_ms,
            )
        )

    async def name_map(self) -> dict[str, list[ToolId]]:
        if self._name_map is not None:
            return self._name_map

        name_map: dict[str, list[ToolId]] = {}
        for tool_id in self._allowlist:
            fn_name = await self._canonical_tool_name(tool_id)
            name_map.setdefault(fn_name, []).append(tool_id)

        self._name_map = name_map
        return name_map

    async def _canonical_tool_name(self, tool_id: str) -> str:
        """Return the canonical function name for *tool_id*.

        This is the SINGLE source of truth for the dispatch name used by
        both ``name_map()`` and ``tools_info()`` / ``list_tools()``.
        It resolves every tool kind via the same path the child sees,
        guaranteeing the name the user calls matches the name in the map.
        """
        from kiln_ai.tools.tool_registry import tool_from_id_and_project

        tool = tool_from_id_and_project(tool_id, project=self._project, task=self._task)
        return await tool.name()

    async def tools_info(self) -> list[dict[str, Any]]:
        """Return tool definitions for ``list_tools()``."""
        result: list[dict[str, Any]] = []
        for tool_id in self._allowlist:
            try:
                from kiln_ai.tools.tool_registry import tool_from_id_and_project

                tool = tool_from_id_and_project(
                    tool_id, project=self._project, task=self._task
                )
                tool_def = await tool.toolcall_definition()
                result.append(
                    {
                        "name": tool_def["function"]["name"],
                        "description": tool_def["function"]["description"],
                        "parameters_schema": tool_def["function"]["parameters"],
                    }
                )
            except Exception:
                fn_name = await self._canonical_tool_name(tool_id)
                result.append(
                    {
                        "name": fn_name,
                        "description": "(unavailable)",
                        "parameters_schema": {},
                    }
                )
        return result


async def run_bridged_child(
    *,
    target: Callable[..., None],
    args: tuple[Any, ...],
    timeout_s: float,
    server: NestedToolServer,
) -> BridgeResult:
    """Spawn ``target(*args, requests, responses)`` and pump its nested tool calls.

    Owns the full queue lifecycle: it creates the spawn ``requests``/``responses``
    queues (after the depth/semaphore gates) and closes them in its ``finally``, so
    neither caller creates or owns queues and cleanup is identical for both.

    Dispatches ``tool_call`` / ``list_tools`` messages to *server* and returns a
    :class:`BridgeResult` on the first ``result`` message (raw msg), a timeout, or a
    crash. Enforces the nesting-depth cap (>=10 → error result, no spawn) and acquires
    the shared bounded semaphore only at depth 0 (nested runs bypass — counting them
    deadlocks the pool).
    """
    depth = _depth.get()
    if depth >= 10:
        return BridgeResult(
            result_msg={
                "error": "maximum nested code execution depth exceeded — check for a cycle"
            }
        )

    token = _depth.set(depth + 1)
    try:
        if depth == 0:
            cm = await _get_semaphore()
        else:
            cm = contextlib.nullcontext()  # type: ignore[assignment]

        async with cm:
            ctx = multiprocessing.get_context("spawn")
            requests: multiprocessing.Queue[dict[str, Any]] = ctx.Queue()
            responses: multiprocessing.Queue[dict[str, Any]] = ctx.Queue()
            try:
                return await _pump(target, args, timeout_s, requests, responses, server)
            finally:
                _close_queues(requests, responses)
    finally:
        _depth.reset(token)


async def _pump(
    target: Callable[..., None],
    args: tuple[Any, ...],
    timeout_s: float,
    requests: multiprocessing.Queue[dict[str, Any]],
    responses: multiprocessing.Queue[dict[str, Any]],
    server: NestedToolServer,
) -> BridgeResult:
    loop = asyncio.get_running_loop()
    ctx = multiprocessing.get_context("spawn")

    p = ctx.Process(
        target=target,
        args=(*args, requests, responses),
        daemon=True,
    )

    await loop.run_in_executor(None, start_process_with_light_main, p)

    deadline = monotonic() + timeout_s
    pending_tasks: set[asyncio.Task[None]] = set()
    start_time = monotonic()

    try:
        while True:
            msg = await loop.run_in_executor(None, _poll_get, requests)

            if monotonic() > deadline:
                elapsed = int((monotonic() - start_time) * 1000)
                p.kill()
                await loop.run_in_executor(None, p.join, 5)
                return BridgeResult(timed_out=True, duration_ms=elapsed)

            if msg is None:
                if not p.is_alive() and requests.empty():
                    elapsed = int((monotonic() - start_time) * 1000)
                    return BridgeResult(
                        crashed=True,
                        exit_code=p.exitcode,
                        duration_ms=elapsed,
                    )
                continue

            if msg["type"] in ("tool_call", "list_tools"):
                t = asyncio.create_task(server.serve(msg, responses))
                pending_tasks.add(t)
                t.add_done_callback(pending_tasks.discard)

            elif msg["type"] == "result":
                elapsed = int((monotonic() - start_time) * 1000)
                await loop.run_in_executor(None, p.join, 5)
                return BridgeResult(
                    result_msg=msg,
                    stdout=msg.get("stdout", ""),
                    stderr=msg.get("stderr", ""),
                    duration_ms=elapsed,
                )
    finally:
        for t in pending_tasks:
            t.cancel()
        if p.is_alive():
            p.kill()
            await loop.run_in_executor(None, p.join, 5)


def _render_params_schema(schema: dict[str, Any]) -> str:
    """Render a JSON schema's properties into a readable parameter list.

    Example output: ``a: number (required), b: number (required)``
    """
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    if not props:
        return "(no parameters)"
    parts: list[str] = []
    for name, prop in props.items():
        ptype = prop.get("type", "any")
        req = "required" if name in required else "optional"
        parts.append(f"{name}: {ptype} ({req})")
    return ", ".join(parts)


def _example_kwargs(schema: dict[str, Any]) -> str:
    """Render example keyword-argument syntax from a schema.

    Example output: ``a=..., b=...``
    """
    props = schema.get("properties", {})
    if not props:
        return ""
    return ", ".join(f"{name}=..." for name in props)


def _poll_get(q: multiprocessing.Queue) -> dict[str, Any] | None:  # type: ignore[type-arg]
    """Non-blocking get with short timeout so the pump can re-check deadlines."""
    try:
        return q.get(timeout=0.1)
    except (queue.Empty, EOFError, OSError, ValueError):
        return None


def _close_queues(*queues: multiprocessing.Queue) -> None:  # type: ignore[type-arg]
    for q in queues:
        try:
            q.close()
            q.join_thread()
        except Exception:
            pass
