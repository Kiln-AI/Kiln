"""Tests for the shared parent-side sandbox bridge.

Parent-side tests (NestedToolServer, module surface) use fake tool doubles and a
collecting responses stand-in. The ``run_bridged_child`` tests spawn real children
via the stdlib child entry point (``sandbox.worker.child_main``), mirroring the
existing ``test_code_tool_execution.py`` style.
"""

import multiprocessing
from unittest.mock import patch

import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.sandbox.worker import child_main
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallDefinition,
    ToolCallResult,
)
from kiln_ai.tools.sandbox_bridge import (
    CODE_SANDBOX_MAX_CONCURRENCY,
    BridgeResult,
    NestedToolServer,
    ToolCallLogEntry,
    _close_queues,
    _depth,
    _example_kwargs,
    _poll_get,
    _render_params_schema,
    run_bridged_child,
)

REGISTRY_PATH = "kiln_ai.tools.tool_registry.tool_from_id_and_project"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTool(KilnToolInterface):
    """Minimal tool double. ``fn_name`` intentionally differs from the tool_id slug."""

    def __init__(
        self,
        tool_id: str,
        fn_name: str,
        fn_desc: str = "fake",
        params: dict | None = None,
        result: ToolCallResult | None = None,
    ):
        self._id = tool_id
        self._name = fn_name
        self._desc = fn_desc
        self._params = params or {"type": "object", "properties": {}}
        self._result = result or ToolCallResult(output="ok")

    async def id(self):
        return self._id

    async def name(self):
        return self._name

    async def description(self):
        return self._desc

    async def toolcall_definition(self) -> ToolCallDefinition:
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._desc,
                "parameters": self._params,
            },
        }

    async def run(self, context=None, **kwargs) -> ToolCallResult:
        return self._result


class _CollectingResponses:
    """Stand-in for the responses queue — records ``put`` payloads."""

    def __init__(self):
        self.messages: list[dict] = []

    def put(self, msg: dict) -> None:
        self.messages.append(msg)


def _make_project(tmp_path) -> Project:
    p = Project(name="test_project", path=tmp_path / "project")
    p.save_to_file()
    return p


def _spawn_queues():
    ctx = multiprocessing.get_context("spawn")
    return ctx.Queue(), ctx.Queue()


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_shared_concurrency_bound_is_16():
    assert CODE_SANDBOX_MAX_CONCURRENCY == 16


def test_bridge_result_defaults():
    r = BridgeResult()
    assert r.result_msg is None
    assert r.timed_out is False
    assert r.crashed is False
    assert r.exit_code is None
    assert r.stdout == ""
    assert r.stderr == ""
    assert r.duration_ms == 0


def test_render_params_schema():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "string"}},
        "required": ["a"],
    }
    rendered = _render_params_schema(schema)
    assert "a: number (required)" in rendered
    assert "b: string (optional)" in rendered


def test_render_params_schema_empty():
    assert _render_params_schema({"type": "object", "properties": {}}) == (
        "(no parameters)"
    )


def test_example_kwargs():
    schema = {"type": "object", "properties": {"a": {}, "b": {}}}
    assert _example_kwargs(schema) == "a=..., b=..."


def test_poll_get_empty_returns_none():
    requests, responses = _spawn_queues()
    try:
        assert _poll_get(requests) is None
    finally:
        _close_queues(requests, responses)


def test_close_queues_is_idempotent_and_safe():
    requests, responses = _spawn_queues()
    _close_queues(requests, responses)
    # Second close (already closed) must not raise.
    _close_queues(requests, responses)


# ---------------------------------------------------------------------------
# NestedToolServer
# ---------------------------------------------------------------------------


class TestNestedToolServer:
    @pytest.mark.asyncio
    async def test_name_map_uses_tool_name_not_slug(self, tmp_path):
        project = _make_project(tmp_path)
        fake = _FakeTool("kiln_tool::add_numbers", "fake_add")
        server = NestedToolServer(
            allowlist=["kiln_tool::add_numbers"],
            project=project,
            task=None,
            context=None,
        )
        with patch(REGISTRY_PATH, return_value=fake):
            name_map = await server.name_map()
        assert name_map == {"fake_add": ["kiln_tool::add_numbers"]}

    @pytest.mark.asyncio
    async def test_tools_info(self, tmp_path):
        project = _make_project(tmp_path)
        params = {"type": "object", "properties": {"a": {"type": "number"}}}
        fake = _FakeTool(
            "kiln_tool::add_numbers", "fake_add", fn_desc="adds", params=params
        )
        server = NestedToolServer(
            allowlist=["kiln_tool::add_numbers"],
            project=project,
            task=None,
            context=None,
        )
        with patch(REGISTRY_PATH, return_value=fake):
            info = await server.tools_info()
        assert info == [
            {
                "name": "fake_add",
                "description": "adds",
                "parameters_schema": params,
            }
        ]

    @pytest.mark.asyncio
    async def test_serve_tool_call_success_and_records(self, tmp_path):
        project = _make_project(tmp_path)
        fake = _FakeTool(
            "kiln_tool::add_numbers", "fake_add", result=ToolCallResult(output="42")
        )
        log: list[ToolCallLogEntry] = []
        server = NestedToolServer(
            allowlist=["kiln_tool::add_numbers"],
            project=project,
            task=None,
            context=None,
            recorder=log.append,
        )
        responses = _CollectingResponses()
        msg = {
            "type": "tool_call",
            "call_id": 1,
            "tool_name": "fake_add",
            "arguments": {},
        }
        with patch(REGISTRY_PATH, return_value=fake):
            await server.serve(msg, responses)

        assert responses.messages == [{"type": "tool_result", "call_id": 1, "ok": "42"}]
        assert len(log) == 1
        assert log[0].tool_name == "fake_add"
        assert log[0].is_error is False
        assert log[0].output_preview == "42"

    @pytest.mark.asyncio
    async def test_serve_not_allowed_lists_available(self, tmp_path):
        project = _make_project(tmp_path)
        fake = _FakeTool("kiln_tool::add_numbers", "fake_add")
        log: list[ToolCallLogEntry] = []
        server = NestedToolServer(
            allowlist=["kiln_tool::add_numbers"],
            project=project,
            task=None,
            context=None,
            recorder=log.append,
        )
        responses = _CollectingResponses()
        msg = {
            "type": "tool_call",
            "call_id": 2,
            "tool_name": "missing_tool",
            "arguments": {},
        }
        with patch(REGISTRY_PATH, return_value=fake):
            await server.serve(msg, responses)

        assert len(responses.messages) == 1
        err = responses.messages[0]["error"]
        assert err["kind"] == "not_allowed"
        assert err["available"] == ["fake_add"]
        assert log[0].is_error is True

    @pytest.mark.asyncio
    async def test_serve_list_tools(self, tmp_path):
        project = _make_project(tmp_path)
        fake = _FakeTool("kiln_tool::add_numbers", "fake_add", fn_desc="adds")
        server = NestedToolServer(
            allowlist=["kiln_tool::add_numbers"],
            project=project,
            task=None,
            context=None,
        )
        responses = _CollectingResponses()
        with patch(REGISTRY_PATH, return_value=fake):
            await server.serve({"type": "list_tools", "call_id": 3}, responses)

        assert len(responses.messages) == 1
        reply = responses.messages[0]
        assert reply["call_id"] == 3
        assert reply["ok_list"][0]["name"] == "fake_add"


# ---------------------------------------------------------------------------
# run_bridged_child (real spawns)
# ---------------------------------------------------------------------------


def _empty_server(tmp_path) -> NestedToolServer:
    project = _make_project(tmp_path)
    return NestedToolServer(allowlist=[], project=project, task=None, context=None)


class TestRunBridgedChild:
    @pytest.mark.asyncio
    async def test_result_message_returned_raw(self, tmp_path):
        result = await run_bridged_child(
            target=child_main,
            args=('def run(x):\n    return "hi " + x\n', {"x": "there"}),
            timeout_s=10,
            server=_empty_server(tmp_path),
        )
        assert result.timed_out is False
        assert result.crashed is False
        assert result.result_msg is not None
        assert result.result_msg["ok"] == "hi there"

    @pytest.mark.asyncio
    async def test_crash_reports_exit_code(self, tmp_path):
        result = await run_bridged_child(
            target=child_main,
            args=("import os\ndef run(x):\n    os._exit(4)\n", {"x": "a"}),
            timeout_s=10,
            server=_empty_server(tmp_path),
        )
        assert result.crashed is True
        assert result.exit_code == 4
        assert result.result_msg is None

    @pytest.mark.asyncio
    async def test_timeout_kills_child(self, tmp_path):
        result = await run_bridged_child(
            target=child_main,
            args=("import time\ndef run(x):\n    time.sleep(30)\n", {"x": "a"}),
            timeout_s=0.3,
            server=_empty_server(tmp_path),
        )
        assert result.timed_out is True
        assert result.result_msg is None

    @pytest.mark.asyncio
    async def test_depth_cap_returns_error_without_spawn(self, tmp_path):
        token = _depth.set(10)
        try:
            result = await run_bridged_child(
                target=child_main,
                args=('def run(x):\n    return "should not run"\n', {"x": "a"}),
                timeout_s=10,
                server=_empty_server(tmp_path),
            )
        finally:
            _depth.reset(token)
        assert result.result_msg == {
            "error": "maximum nested code execution depth exceeded — check for a cycle"
        }
        assert result.timed_out is False
        assert result.crashed is False
