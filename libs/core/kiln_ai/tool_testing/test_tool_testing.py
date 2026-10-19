"""Behavioral tests for the ``kiln`` test shim (functional spec §5/§6).

These tests exercise the shipped pytest plugin the same way an author would: the
plugin is auto-loaded via the ``pytest11`` entry point, so the synthetic ``kiln``
modules are already installed and the ``kiln_tools`` fixture is available.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterator

import pytest

from kiln_ai.sandbox import tools_surface
from kiln_ai.tool_testing.fake_bridge import FakeToolBridge, RecordedToolCall


class TestPluginInstall:
    def test_kiln_modules_installed_at_plugin_load(self) -> None:
        # pytest_configure (plugin load) installed these before any collection.
        assert "kiln" in sys.modules
        assert "kiln.tools" in sys.modules
        assert "kiln.async_tools" in sys.modules

    def test_from_kiln_import_tools_resolves(self) -> None:
        # This is the import a tool.py does at its top level.
        from kiln import async_tools, tools

        assert tools is sys.modules["kiln.tools"]
        assert async_tools is sys.modules["kiln.async_tools"]

    def test_exception_classes_are_the_runtime_classes(self) -> None:
        from kiln import async_tools, tools

        # A test catching kiln.tools.ToolCallError catches the same class the
        # runtime (sandbox) raises — one definition, shared surface.
        assert tools.ToolCallError is tools_surface.ToolCallError
        assert tools.ToolNotAllowed is tools_surface.ToolNotAllowed
        assert tools.ToolTimeout is tools_surface.ToolTimeout
        # sync and async modules expose the identical classes
        assert async_tools.ToolCallError is tools.ToolCallError
        assert async_tools.ToolNotAllowed is tools.ToolNotAllowed
        assert async_tools.ToolTimeout is tools.ToolTimeout


class TestSetReplies:
    def test_static_reply_returned_verbatim(self, kiln_tools: FakeToolBridge) -> None:
        from kiln import tools

        kiln_tools.set("get_user", '{"id": 1234, "name": "Alice"}')
        assert tools.get_user(id=1234) == '{"id": 1234, "name": "Alice"}'

    def test_callable_reply_receives_kwargs(self, kiln_tools: FakeToolBridge) -> None:
        import json

        from kiln import tools

        kiln_tools.set("list_jobs", lambda **kw: json.dumps(sorted(kw["ids"])))
        assert tools.list_jobs(ids=["b", "a"]) == '["a", "b"]'

    def test_calls_recorded_with_arguments(self, kiln_tools: FakeToolBridge) -> None:
        from kiln import tools

        kiln_tools.set("get_user", "ok")
        tools.get_user(id=7, verbose=True)
        assert kiln_tools.calls == [
            RecordedToolCall(name="get_user", arguments={"id": 7, "verbose": True})
        ]
        assert kiln_tools.calls[0].name == "get_user"

    def test_set_rejects_non_str_non_callable(self, kiln_tools: FakeToolBridge) -> None:
        with pytest.raises(TypeError, match="must be a str or a callable"):
            kiln_tools.set("bad", 123)  # type: ignore[arg-type]

    def test_callable_returning_non_str_raises(
        self, kiln_tools: FakeToolBridge
    ) -> None:
        from kiln import tools

        kiln_tools.set("bad", lambda **kw: 123)  # type: ignore[return-value,arg-type]
        with pytest.raises(TypeError, match="must return a str"):
            tools.bad()


class TestErrors:
    def test_set_error_raises_that_exception(self, kiln_tools: FakeToolBridge) -> None:
        from kiln.tools import ToolCallError

        boom = ToolCallError(tool="explode", message="kaboom", raw="raw-output")
        kiln_tools.set_error("explode", boom)
        with pytest.raises(ToolCallError) as exc_info:
            from kiln import tools

            tools.explode()
        assert exc_info.value is boom
        assert exc_info.value.tool == "explode"
        assert exc_info.value.message == "kaboom"
        assert exc_info.value.raw == "raw-output"

    def test_set_error_supports_all_three_types(
        self, kiln_tools: FakeToolBridge
    ) -> None:
        from kiln import tools
        from kiln.tools import ToolNotAllowed, ToolTimeout

        kiln_tools.set_error("slow", ToolTimeout(tool="slow", message="too slow"))
        kiln_tools.set_error("nope", ToolNotAllowed(tool="nope", message="denied"))
        with pytest.raises(ToolTimeout):
            tools.slow()
        with pytest.raises(ToolNotAllowed):
            tools.nope()

    def test_set_error_rejects_non_exception(self, kiln_tools: FakeToolBridge) -> None:
        with pytest.raises(TypeError, match="must be an exception instance"):
            kiln_tools.set_error("x", "not an exception")  # type: ignore[arg-type]

    def test_unregistered_name_raises_tool_not_allowed(
        self, kiln_tools: FakeToolBridge
    ) -> None:
        from kiln import tools
        from kiln.tools import ToolNotAllowed

        with pytest.raises(ToolNotAllowed) as exc_info:
            tools.never_registered(x=1)
        assert exc_info.value.tool == "never_registered"
        # still recorded so authors can inspect the attempted call
        assert kiln_tools.calls[0].name == "never_registered"

    def test_positional_args_on_registered_tool_raise_tool_call_error(
        self, kiln_tools: FakeToolBridge
    ) -> None:
        from kiln import tools
        from kiln.tools import ToolCallError

        kiln_tools.set("add", "3")
        with pytest.raises(ToolCallError, match="keyword arguments"):
            tools.add(1, 2)

    def test_positional_on_unregistered_name_still_not_allowed(
        self, kiln_tools: FakeToolBridge
    ) -> None:
        # Mirrors the runtime's test_positional_on_nonsense_name_still_not_allowed:
        # the not-allowed check precedes the positional-args check, so an unknown
        # tool raises ToolNotAllowed regardless of how it was called.
        from kiln import tools
        from kiln.tools import ToolNotAllowed

        with pytest.raises(ToolNotAllowed):
            tools.bad_tool(1, 2)


class TestListTools:
    def test_list_tools_returns_declarations(self, kiln_tools: FakeToolBridge) -> None:
        from kiln import tools

        kiln_tools.set(
            "get_user",
            "{}",
            declaration={"description": "Get a user", "parameters": {"id": "int"}},
        )
        kiln_tools.set_error(
            "explode", tools.ToolCallError(tool="explode", message="x")
        )
        listed = tools.list_tools()
        by_name = {d["name"]: d for d in listed}
        assert set(by_name) == {"get_user", "explode"}
        assert by_name["get_user"]["description"] == "Get a user"
        assert by_name["get_user"]["parameters"] == {"id": "int"}

    async def test_async_list_tools(self, kiln_tools: FakeToolBridge) -> None:
        from kiln import async_tools

        kiln_tools.set("get_user", "{}")
        listed = await async_tools.list_tools()
        assert [d["name"] for d in listed] == ["get_user"]


class TestAsyncTools:
    async def test_async_tools_under_gather(self, kiln_tools: FakeToolBridge) -> None:
        from kiln import async_tools

        kiln_tools.set("a", lambda **kw: f"a:{kw['v']}")
        kiln_tools.set("b", lambda **kw: f"b:{kw['v']}")

        results = await asyncio.gather(
            async_tools.a(v=1),
            async_tools.b(v=2),
        )
        assert set(results) == {"a:1", "b:2"}
        # both calls were routed through the same registry / call log
        assert {c.name for c in kiln_tools.calls} == {"a", "b"}

    async def test_async_and_sync_share_registry(
        self, kiln_tools: FakeToolBridge
    ) -> None:
        from kiln import async_tools, tools

        kiln_tools.set("shared", "same-reply")
        assert tools.shared() == "same-reply"
        assert await async_tools.shared() == "same-reply"


class TestAutoReset:
    # These two tests assert the fixture resets registry + call log per test.
    def test_auto_reset_first(self, kiln_tools: FakeToolBridge) -> None:
        assert kiln_tools.calls == []
        from kiln import tools

        kiln_tools.set("leaky", "value")
        tools.leaky()
        assert len(kiln_tools.calls) == 1

    def test_auto_reset_second(self, kiln_tools: FakeToolBridge) -> None:
        # Nothing from the previous test leaked in.
        assert kiln_tools.calls == []
        from kiln import tools
        from kiln.tools import ToolNotAllowed

        with pytest.raises(ToolNotAllowed):
            tools.leaky()


# Sample tool.py source: does `from kiln import tools` at the top level (must
# resolve at import time) and calls a nested tool inside run().
_SAMPLE_TOOL_SOURCE = textwrap.dedent(
    """\
    import json
    from kiln import tools

    def run(job_ids):
        user = json.loads(tools.get_user(id=1234))
        jobs = json.loads(tools.list_jobs(ids=job_ids))
        return json.dumps({"name": user["name"], "jobs": jobs})
    """
)


@pytest.fixture
def sample_tool_module(tmp_path: Path) -> Iterator[Any]:
    """Write a sample tool.py, import it as `tool`, clean up sys.modules after."""
    (tmp_path / "tool.py").write_text(_SAMPLE_TOOL_SOURCE, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    sys.modules.pop("tool", None)
    try:
        # Top-level `from kiln import tools` resolves here — the whole point of
        # installing the surface at plugin load rather than in a fixture.
        module = importlib.import_module("tool")
        yield module
    finally:
        sys.modules.pop("tool", None)
        sys.path.remove(str(tmp_path))


class TestEndToEnd:
    def test_sample_tool_py_imports_and_runs(
        self, kiln_tools: FakeToolBridge, sample_tool_module: Any
    ) -> None:
        import json

        kiln_tools.set("get_user", '{"id": 1234, "name": "Alice"}')
        kiln_tools.set("list_jobs", lambda **kw: json.dumps(sorted(kw["ids"])))

        out = sample_tool_module.run(job_ids=["b", "a"])

        parsed = json.loads(out)
        assert parsed == {"name": "Alice", "jobs": ["a", "b"]}
        # call assertions, in order
        assert [c.name for c in kiln_tools.calls] == ["get_user", "list_jobs"]
        assert kiln_tools.calls[0].arguments == {"id": 1234}
        assert kiln_tools.calls[1].arguments == {"ids": ["b", "a"]}

    def test_sample_tool_py_unknown_tool_raises(
        self, kiln_tools: FakeToolBridge, sample_tool_module: Any
    ) -> None:
        from kiln.tools import ToolNotAllowed

        # get_user is registered but list_jobs is not: the second call raises.
        kiln_tools.set("get_user", '{"id": 1234, "name": "Alice"}')
        with pytest.raises(ToolNotAllowed):
            sample_tool_module.run(job_ids=["a"])
