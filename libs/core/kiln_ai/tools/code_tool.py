"""PythonCodeTool — parent-side runtime for user-authored code tools.

Spawns a child process per invocation, pumps nested tool-call IPC,
enforces depth caps, concurrency bounds, and wall-clock timeouts.
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

from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.json_schema import validate_schema_with_value_error
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import ToolId, build_code_tool_id
from kiln_ai.sandbox.spawn import start_process_with_light_main
from kiln_ai.sandbox.worker import child_main
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)

logger = logging.getLogger(__name__)

CODE_TOOL_MAX_CONCURRENCY = 8
"""Maximum concurrent top-level code-tool invocations (process-wide)."""

_code_tool_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    "_code_tool_depth", default=0
)

_semaphore: asyncio.Semaphore | None = None
_semaphore_init_lock = threading.Lock()


async def _get_semaphore() -> asyncio.Semaphore:
    """Lazily create the semaphore inside the running event loop."""
    global _semaphore
    if _semaphore is None:
        with _semaphore_init_lock:
            if _semaphore is None:
                _semaphore = asyncio.Semaphore(CODE_TOOL_MAX_CONCURRENCY)
    sem = _semaphore
    assert sem is not None
    return sem


@dataclass
class ChildOutcome:
    ok: str | None = None
    error: str | None = None
    traceback_str: str | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    crashed: bool = False
    exit_code: int | None = None


@dataclass
class ToolCallLogEntry:
    tool_name: str
    arguments: dict[str, Any]
    output_preview: str
    is_error: bool
    duration_ms: int


class PythonCodeTool(KilnToolInterface):
    """Wraps a :class:`CodeTool` artifact as a :class:`KilnToolInterface`."""

    def __init__(
        self,
        code_tool: CodeTool,
        project: Project,
        task: Task | None = None,
        tool_call_recorder: Callable[[ToolCallLogEntry], None] | None = None,
    ):
        self._code_tool = code_tool
        self._project = project
        self._task = task
        self._tool_call_recorder = tool_call_recorder
        self._name_map: dict[str, list[ToolId]] | None = None

    async def id(self) -> ToolId:
        return build_code_tool_id(self._code_tool.id)

    async def name(self) -> str:
        return self._code_tool.tool_function_name

    async def description(self) -> str:
        return self._code_tool.tool_description

    async def toolcall_definition(self) -> ToolCallDefinition:
        return {
            "type": "function",
            "function": {
                "name": self._code_tool.tool_function_name,
                "description": self._code_tool.tool_description,
                "parameters": self._code_tool.parameters_schema,
            },
        }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs: Any
    ) -> ToolCallResult:
        from kiln_ai.adapters.eval.v2_eval_code_eval import is_code_eval_trusted

        if not is_code_eval_trusted(str(self._project.path)):
            return ToolCallResult(
                output="Code tools are disabled until the project is trusted in Kiln.",
                is_error=True,
                error_message="Project not trusted",
            )

        outcome = await self._invoke(context, kwargs)

        tool_name = self._code_tool.tool_function_name
        if outcome.timed_out:
            msg = f"Code tool '{tool_name}' timed out after {self._code_tool.timeout_seconds}s"
            return ToolCallResult(output=msg, is_error=True, error_message=msg)
        if outcome.crashed:
            msg = f"Code tool '{tool_name}' crashed (exit code {outcome.exit_code})"
            return ToolCallResult(output=msg, is_error=True, error_message=msg)
        if outcome.error is not None:
            tb_text = outcome.traceback_str or ""
            output = f"Code tool '{tool_name}' failed: {outcome.error}"
            if tb_text:
                output += f"\n{tb_text}"
            return ToolCallResult(
                output=output,
                is_error=True,
                error_message=outcome.error,
            )

        assert outcome.ok is not None
        return ToolCallResult(output=outcome.ok)

    async def _invoke(
        self, context: ToolCallContext | None, kwargs: dict[str, Any]
    ) -> ChildOutcome:
        depth = _code_tool_depth.get()
        if depth >= 10:
            return ChildOutcome(
                error="max code tool depth exceeded — check for a cycle"
            )

        token = _code_tool_depth.set(depth + 1)
        try:
            if depth == 0:
                cm = await _get_semaphore()
            else:
                cm = contextlib.nullcontext()  # type: ignore[assignment]

            async with cm:
                return await self._run_child(context, kwargs)
        finally:
            _code_tool_depth.reset(token)

    async def _run_child(
        self, context: ToolCallContext | None, kwargs: dict[str, Any]
    ) -> ChildOutcome:
        loop = asyncio.get_running_loop()
        ctx = multiprocessing.get_context("spawn")
        requests: multiprocessing.Queue[dict[str, Any]] = ctx.Queue()
        responses: multiprocessing.Queue[dict[str, Any]] = ctx.Queue()

        p = ctx.Process(
            target=child_main,
            args=(
                self._code_tool.code,
                kwargs,
                requests,
                responses,
            ),
            daemon=True,
        )

        await loop.run_in_executor(None, start_process_with_light_main, p)

        deadline = monotonic() + self._code_tool.timeout_seconds
        pending_tasks: set[asyncio.Task[None]] = set()
        start_time = monotonic()

        try:
            while True:
                msg = await loop.run_in_executor(None, _poll_get, requests)

                if monotonic() > deadline:
                    elapsed = int((monotonic() - start_time) * 1000)
                    p.kill()
                    p.join(timeout=5)
                    return ChildOutcome(timed_out=True, duration_ms=elapsed)

                if msg is None:
                    if not p.is_alive() and requests.empty():
                        elapsed = int((monotonic() - start_time) * 1000)
                        return ChildOutcome(
                            crashed=True,
                            exit_code=p.exitcode,
                            duration_ms=elapsed,
                        )
                    continue

                if msg["type"] in ("tool_call", "list_tools"):
                    t = asyncio.create_task(self._serve(msg, context, responses))
                    pending_tasks.add(t)
                    t.add_done_callback(pending_tasks.discard)

                elif msg["type"] == "result":
                    elapsed = int((monotonic() - start_time) * 1000)
                    p.join(timeout=5)
                    if "ok" in msg:
                        return ChildOutcome(
                            ok=msg["ok"],
                            stdout=msg.get("stdout", ""),
                            stderr=msg.get("stderr", ""),
                            duration_ms=elapsed,
                        )
                    else:
                        return ChildOutcome(
                            error=msg.get("error", "unknown error"),
                            traceback_str=msg.get("traceback"),
                            stdout=msg.get("stdout", ""),
                            stderr=msg.get("stderr", ""),
                            duration_ms=elapsed,
                        )
        finally:
            for t in pending_tasks:
                t.cancel()
            if p.is_alive():
                p.kill()
                p.join(timeout=5)
            _close_queues(requests, responses)

    async def _serve(
        self,
        msg: dict[str, Any],
        context: ToolCallContext | None,
        responses: multiprocessing.Queue[dict[str, Any]],
    ) -> None:
        call_id = msg["call_id"]

        if msg["type"] == "list_tools":
            try:
                tools_info = await self._get_tools_info()
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
            name_map = await self._build_name_map()
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

            result = await tool.run(context, **arguments)

            if result.is_error:
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
                "Code tool nested call timed out for '%s': %s",
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
                "Code tool nested call failed for '%s': %s",
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
        if self._tool_call_recorder is None:
            return
        duration_ms = int((monotonic() - start) * 1000)
        preview = output[:1024] if output else ""
        self._tool_call_recorder(
            ToolCallLogEntry(
                tool_name=tool_name,
                arguments=arguments,
                output_preview=preview,
                is_error=is_error,
                duration_ms=duration_ms,
            )
        )

    async def _build_name_map(self) -> dict[str, list[ToolId]]:
        if self._name_map is not None:
            return self._name_map

        name_map: dict[str, list[ToolId]] = {}
        for tool_id in self._code_tool.tool_allowlist:
            fn_name = await self._canonical_tool_name(tool_id)
            name_map.setdefault(fn_name, []).append(tool_id)

        self._name_map = name_map
        return name_map

    async def _canonical_tool_name(self, tool_id: str) -> str:
        """Return the canonical function name for *tool_id*.

        This is the SINGLE source of truth for the dispatch name used by
        both ``_build_name_map()`` and ``_get_tools_info()`` / ``list_tools()``.
        It resolves every tool kind via the same path the child sees,
        guaranteeing the name the user calls matches the name in the map.
        """
        from kiln_ai.tools.tool_registry import tool_from_id_and_project

        tool = tool_from_id_and_project(tool_id, project=self._project, task=self._task)
        return await tool.name()

    async def _get_tools_info(self) -> list[dict[str, Any]]:
        """Return tool definitions for ``list_tools()``."""
        result: list[dict[str, Any]] = []
        for tool_id in self._code_tool.tool_allowlist:
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
    except (queue.Empty, EOFError):
        return None


def _close_queues(*queues: multiprocessing.Queue) -> None:  # type: ignore[type-arg]
    for q in queues:
        try:
            q.close()
            q.join_thread()
        except Exception:
            pass
