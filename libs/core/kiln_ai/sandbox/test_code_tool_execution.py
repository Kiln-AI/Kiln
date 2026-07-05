"""Tests for the code-tool execution engine.

Child/protocol tests spawn real child processes. Parent-side tests use
mock tool doubles. Shaped after the existing ``test_sandbox_worker.py`` suite.
"""

import asyncio
import json
import textwrap
from unittest.mock import AsyncMock, patch

import pytest

from kiln_ai.adapters.eval.v2_eval_code_eval import (
    grant_code_eval_trust,
    revoke_code_eval_trust,
)
from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.project import Project
from kiln_ai.sandbox.spawn import _spawn_lock
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallDefinition,
    ToolCallResult,
)
from kiln_ai.tools.code_tool import (
    CODE_TOOL_MAX_CONCURRENCY,
    PythonCodeTool,
    ToolCallLogEntry,
    _code_tool_depth,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SCHEMA = {
    "type": "object",
    "properties": {"x": {"type": "string"}},
}
EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _make_code_tool(code: str, **overrides) -> CodeTool:
    defaults = {
        "name": "Test Tool",
        "tool_function_name": "test_tool",
        "tool_description": "A test tool",
        "parameters_schema": VALID_SCHEMA,
        "code": code,
        "timeout_seconds": 10,
    }
    defaults.update(overrides)
    return CodeTool(**defaults)


def _make_project(tmp_path) -> Project:
    p = Project(name="test_project", path=tmp_path / "project")
    p.save_to_file()
    return p


def _make_python_code_tool(
    tmp_path,
    code: str,
    tool_allowlist=None,
    tool_call_recorder=None,
    **overrides,
) -> PythonCodeTool:
    project = _make_project(tmp_path)
    ct = _make_code_tool(
        code,
        tool_allowlist=tool_allowlist or [],
        **overrides,
    )
    ct.parent = project
    return PythonCodeTool(
        ct,
        project,
        tool_call_recorder=tool_call_recorder,
    )


class FakeTool(KilnToolInterface):
    """Minimal tool double for testing nested calls."""

    def __init__(
        self,
        tool_id: str,
        fn_name: str,
        fn_desc: str = "fake",
        params: dict | None = None,
        result: ToolCallResult | None = None,
        delay: float = 0,
    ):
        self._id = tool_id
        self._name = fn_name
        self._desc = fn_desc
        self._params = params or EMPTY_SCHEMA
        self._result = result or ToolCallResult(output="ok")
        self._delay = delay

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
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        return self._result


# ---------------------------------------------------------------------------
# Child / protocol tests (real spawns)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _trust_all_projects(tmp_path):
    """Grant trust for tests so the trust gate doesn't block execution."""
    path = str(tmp_path / "project")
    grant_code_eval_trust(path)
    yield
    revoke_code_eval_trust(path)


class TestChildSyncRun:
    @pytest.mark.asyncio
    async def test_sync_run_returns_string(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            'def run(x):\n    return "hello " + x\n',
        )
        result = await tool.run(None, x="world")
        assert not result.is_error
        assert result.output == "hello world"

    @pytest.mark.asyncio
    async def test_sync_run_returns_dict(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            'def run(x):\n    return {"value": x}\n',
        )
        result = await tool.run(None, x="test")
        assert not result.is_error
        assert json.loads(result.output) == {"value": "test"}

    @pytest.mark.asyncio
    async def test_sync_run_returns_none(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            "def run(x):\n    pass\n",
        )
        result = await tool.run(None, x="test")
        assert not result.is_error
        assert result.output == "null"


class TestChildAsyncRun:
    @pytest.mark.asyncio
    async def test_async_run_returns_string(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            textwrap.dedent("""\
                import asyncio
                async def run(x):
                    async def greet(name):
                        return "hi " + name
                    results = await asyncio.gather(greet(x), greet(x + "!"))
                    return " ".join(results)
            """),
        )
        result = await tool.run(None, x="a")
        assert not result.is_error
        assert result.output == "hi a hi a!"

    @pytest.mark.asyncio
    async def test_asyncio_run_inside_async_errors(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            textwrap.dedent("""\
                import asyncio
                async def helper():
                    return 1
                async def run(x):
                    return asyncio.run(helper())
            """),
        )
        result = await tool.run(None, x="test")
        assert result.is_error
        assert (
            "cannot be called from a running event loop" in result.output.lower()
            or "cannot" in result.output.lower()
        )


class TestReturnSerialization:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "code,expected",
        [
            ('def run(x):\n    return "raw"\n', "raw"),
            ("def run(x):\n    return 42\n", "42"),
            ("def run(x):\n    return 3.14\n", "3.14"),
            ("def run(x):\n    return True\n", "true"),
            ("def run(x):\n    return False\n", "false"),
            ("def run(x):\n    return None\n", "null"),
            ("def run(x):\n    return [1, 2]\n", "[1, 2]"),
            ('def run(x):\n    return {"k": "v"}\n', '{"k": "v"}'),
        ],
        ids=[
            "str",
            "int",
            "float",
            "bool_true",
            "bool_false",
            "none",
            "list",
            "dict",
        ],
    )
    async def test_serialization(self, tmp_path, code, expected):
        tool = _make_python_code_tool(tmp_path, code)
        result = await tool.run(None, x="test")
        assert not result.is_error
        assert result.output == expected

    @pytest.mark.asyncio
    async def test_non_serializable_type_errors(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            "def run(x):\n    return object()\n",
        )
        result = await tool.run(None, x="test")
        assert result.is_error
        assert "must return str or JSON-serializable" in result.output

    @pytest.mark.asyncio
    async def test_non_serializable_nested_value_errors(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            "def run(x):\n    return {'fn': lambda: None}\n",
        )
        result = await tool.run(None, x="test")
        assert result.is_error
        assert "non-JSON-serializable" in result.output

    @pytest.mark.asyncio
    async def test_string_passthrough_no_parsing(self, tmp_path):
        """JSON-shaped string returned by run() comes back as-is, not parsed."""
        tool = _make_python_code_tool(
            tmp_path,
            'def run(x):\n    return \'{"key": "value"}\'\n',
        )
        result = await tool.run(None, x="test")
        assert not result.is_error
        assert result.output == '{"key": "value"}'


class TestStdoutStderr:
    @pytest.mark.asyncio
    async def test_stdout_captured(self, tmp_path):
        project = _make_project(tmp_path)
        ct = _make_code_tool(
            'def run(x):\n    print("debug")\n    return "ok"\n',
        )
        ct.parent = project
        pct = PythonCodeTool(ct, project)
        outcome = await pct._invoke(None, {"x": "test"})
        assert outcome.ok == "ok"
        assert "debug" in outcome.stdout

    @pytest.mark.asyncio
    async def test_stdout_truncation(self, tmp_path):
        project = _make_project(tmp_path)
        ct = _make_code_tool(
            'def run(x):\n    print("A" * 100000)\n    return "ok"\n',
        )
        ct.parent = project
        pct = PythonCodeTool(ct, project)
        outcome = await pct._invoke(None, {"x": "test"})
        assert outcome.ok == "ok"
        assert len(outcome.stdout) <= 64 * 1024 + 50
        assert "truncated" in outcome.stdout


class TestTraceback:
    @pytest.mark.asyncio
    async def test_traceback_shows_code_tool_lines(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            textwrap.dedent("""\
                def helper():
                    raise ValueError("kaboom")
                def run(x):
                    helper()
            """),
        )
        result = await tool.run(None, x="test")
        assert result.is_error
        assert "kaboom" in result.output
        assert "<code_tool>" in result.output
        assert "worker.py" not in result.output


class TestMissingRun:
    @pytest.mark.asyncio
    async def test_missing_run_defense(self, tmp_path):
        """Even if save-time validation is bypassed, child handles missing run()."""
        project = _make_project(tmp_path)
        ct = CodeTool.__new__(CodeTool)
        object.__setattr__(
            ct,
            "__dict__",
            {
                "name": "bad",
                "tool_function_name": "bad",
                "tool_description": "bad",
                "parameters_schema": EMPTY_SCHEMA,
                "code": "x = 1\n",
                "timeout_seconds": 10,
                "tool_allowlist": [],
                "description": None,
                "is_archived": False,
                "id": "test123",
                "v": 1,
                "created_at": None,
                "created_by": None,
                "path": None,
            },
        )
        object.__setattr__(ct, "__pydantic_fields_set__", set())
        pct = PythonCodeTool(ct, project)
        grant_code_eval_trust(str(project.path))
        result = await pct.run(None)
        assert result.is_error
        assert "run" in result.output.lower()


class TestImportForms:
    @pytest.mark.asyncio
    async def test_from_kiln_import_tools(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            textwrap.dedent("""\
                from kiln import tools
                def run(x):
                    return type(tools).__name__
            """),
        )
        result = await tool.run(None, x="test")
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_import_kiln_tools(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            textwrap.dedent("""\
                import kiln.tools
                def run(x):
                    return type(kiln.tools).__name__
            """),
        )
        result = await tool.run(None, x="test")
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_from_kiln_tools_import_exception(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            textwrap.dedent("""\
                from kiln.tools import ToolCallError
                def run(x):
                    return ToolCallError.__name__
            """),
        )
        result = await tool.run(None, x="test")
        assert not result.is_error
        assert result.output == "ToolCallError"

    @pytest.mark.asyncio
    async def test_from_kiln_import_async_tools(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            textwrap.dedent("""\
                from kiln import async_tools
                def run(x):
                    return type(async_tools).__name__
            """),
        )
        result = await tool.run(None, x="test")
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_exception_classes_identical_across_modules(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            textwrap.dedent("""\
                from kiln import tools, async_tools
                def run(x):
                    same_not_allowed = tools.ToolNotAllowed is async_tools.ToolNotAllowed
                    same_timeout = tools.ToolTimeout is async_tools.ToolTimeout
                    same_call_error = tools.ToolCallError is async_tools.ToolCallError
                    return str(same_not_allowed and same_timeout and same_call_error)
            """),
        )
        result = await tool.run(None, x="test")
        assert not result.is_error
        assert result.output == "True"


class TestJsonUnsafeKwargs:
    @pytest.mark.asyncio
    async def test_json_unsafe_kwargs_raise_in_frame(self, tmp_path):
        """Non-JSON-serializable tool kwargs raise ToolCallError inside child."""
        code = textwrap.dedent("""\
            from kiln.tools import ToolCallError
            from kiln import tools
            def run(x):
                try:
                    tools.some_tool(bad=object())
                except ToolCallError as e:
                    return f"caught: {e.tool}"
                return "no error"
        """)
        tool = _make_python_code_tool(tmp_path, code)
        result = await tool.run(None, x="test")
        assert not result.is_error
        assert "caught: some_tool" in result.output


# ---------------------------------------------------------------------------
# Parent-side tests (mock tools)
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_simple_run(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            'def run(x):\n    return "result_" + x\n',
        )
        result = await tool.run(None, x="abc")
        assert not result.is_error
        assert result.output == "result_abc"


class TestNestedToolCalls:
    @pytest.mark.asyncio
    async def test_nested_tool_success(self, tmp_path):
        fake = FakeTool(
            "kiln_tool::add_numbers",
            "add_numbers",
            params=EMPTY_SCHEMA,
            result=ToolCallResult(output="42"),
        )
        code = textwrap.dedent("""\
            from kiln import tools
            def run(x):
                result = tools.add_numbers()
                return "got: " + result
        """)
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=["kiln_tool::add_numbers"],
        )
        with patch(
            "kiln_ai.tools.tool_registry.tool_from_id_and_project",
            return_value=fake,
        ):
            result = await tool.run(None, x="test")
        assert not result.is_error
        assert result.output == "got: 42"

    @pytest.mark.asyncio
    async def test_nested_tool_is_error(self, tmp_path):
        fake = FakeTool(
            "kiln_tool::add_numbers",
            "add_numbers",
            params=EMPTY_SCHEMA,
            result=ToolCallResult(
                output="tool failed", is_error=True, error_message="tool failed"
            ),
        )
        code = textwrap.dedent("""\
            from kiln.tools import ToolCallError
            from kiln import tools
            def run(x):
                try:
                    tools.add_numbers()
                except ToolCallError as e:
                    return f"error: {e.message}"
                return "no error"
        """)
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=["kiln_tool::add_numbers"],
        )
        with patch(
            "kiln_ai.tools.tool_registry.tool_from_id_and_project",
            return_value=fake,
        ):
            result = await tool.run(None, x="test")
        assert not result.is_error
        assert "error: tool failed" in result.output

    @pytest.mark.asyncio
    async def test_nested_tool_not_allowed(self, tmp_path):
        code = textwrap.dedent("""\
            from kiln.tools import ToolNotAllowed
            from kiln import tools
            def run(x):
                try:
                    tools.nonexistent_tool()
                except ToolNotAllowed as e:
                    return f"not allowed: {e.tool}"
                return "no error"
        """)
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=["kiln_tool::add_numbers"],
        )
        with patch(
            "kiln_ai.tools.code_tool.PythonCodeTool._function_name_for_tool_id",
            new_callable=AsyncMock,
            return_value="add_numbers",
        ):
            result = await tool.run(None, x="test")
        assert not result.is_error
        assert "not allowed: nonexistent_tool" in result.output

    @pytest.mark.asyncio
    async def test_nested_tool_ambiguous(self, tmp_path):
        code = textwrap.dedent("""\
            from kiln.tools import ToolCallError
            from kiln import tools
            def run(x):
                try:
                    tools.search()
                except ToolCallError as e:
                    return f"ambiguous: {e.message}"
                return "no error"
        """)
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=[
                "mcp::remote::server1::search",
                "mcp::remote::server2::search",
            ],
        )
        result = await tool.run(None, x="test")
        assert not result.is_error
        assert "ambiguous" in result.output.lower()

    @pytest.mark.asyncio
    async def test_nested_tool_invalid_kwargs(self, tmp_path):
        fake = FakeTool(
            "kiln_tool::add_numbers",
            "add_numbers",
            params={
                "type": "object",
                "properties": {"a": {"type": "integer"}},
                "required": ["a"],
            },
            result=ToolCallResult(output="42"),
        )
        code = textwrap.dedent("""\
            from kiln.tools import ToolCallError
            from kiln import tools
            def run(x):
                try:
                    tools.add_numbers(a="not_an_int")
                except ToolCallError as e:
                    return f"invalid: {e.tool}"
                return "no error"
        """)
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=["kiln_tool::add_numbers"],
        )
        with patch(
            "kiln_ai.tools.tool_registry.tool_from_id_and_project",
            return_value=fake,
        ):
            result = await tool.run(None, x="test")
        assert not result.is_error
        assert "invalid: add_numbers" in result.output


class TestListTools:
    @pytest.mark.asyncio
    async def test_list_tools_returns_content(self, tmp_path):
        fake = FakeTool(
            "kiln_tool::add_numbers",
            "add_numbers",
            fn_desc="Add two numbers",
            params={
                "type": "object",
                "properties": {"a": {"type": "integer"}},
            },
        )
        code = textwrap.dedent("""\
            import json
            from kiln import tools
            def run(x):
                tool_list = tools.list_tools()
                return json.dumps(tool_list)
        """)
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=["kiln_tool::add_numbers"],
        )
        with patch(
            "kiln_ai.tools.tool_registry.tool_from_id_and_project",
            return_value=fake,
        ):
            result = await tool.run(None, x="test")
        assert not result.is_error
        tool_list = json.loads(result.output)
        assert len(tool_list) == 1
        assert tool_list[0]["name"] == "add_numbers"
        assert tool_list[0]["description"] == "Add two numbers"


class TestTimeout:
    @pytest.mark.asyncio
    async def test_timeout_kills_child(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            "import time\ndef run(x):\n    time.sleep(30)\n    return 'done'\n",
            timeout_seconds=1,
        )
        result = await tool.run(None, x="test")
        assert result.is_error
        assert "timed out" in result.output

    @pytest.mark.asyncio
    async def test_timeout_during_nested_call(self, tmp_path):
        slow_fake = FakeTool(
            "kiln_tool::add_numbers",
            "add_numbers",
            params=EMPTY_SCHEMA,
            result=ToolCallResult(output="42"),
            delay=30,
        )
        code = textwrap.dedent("""\
            from kiln import tools
            def run(x):
                return tools.add_numbers()
        """)
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=["kiln_tool::add_numbers"],
            timeout_seconds=1,
        )
        with patch(
            "kiln_ai.tools.tool_registry.tool_from_id_and_project",
            return_value=slow_fake,
        ):
            result = await tool.run(None, x="test")
        assert result.is_error
        assert "timed out" in result.output


class TestCrash:
    @pytest.mark.asyncio
    async def test_crash_via_os_exit(self, tmp_path):
        tool = _make_python_code_tool(
            tmp_path,
            "import os\ndef run(x):\n    os._exit(3)\n",
        )
        result = await tool.run(None, x="test")
        assert result.is_error
        assert "crashed" in result.output
        assert "exit code" in result.output


class TestDepthCap:
    @pytest.mark.asyncio
    async def test_depth_cap_at_10(self, tmp_path):
        """Depth >= 10 returns an error without spawning."""
        tool = _make_python_code_tool(tmp_path, 'def run(x):\n    return "ok"\n')
        token = _code_tool_depth.set(10)
        try:
            result = await tool.run(None, x="test")
        finally:
            _code_tool_depth.reset(token)
        assert result.is_error
        assert "max code tool depth exceeded" in result.output


class TestSemaphore:
    @pytest.mark.asyncio
    async def test_semaphore_top_level_only_no_deadlock(self, tmp_path):
        """Regression: nested code-tool calls bypass the semaphore.

        If nested calls counted against the semaphore, 8 parents each
        spawning a nested code-tool child would deadlock (parents hold
        all 8 slots, children wait forever).

        This test sets MAX_CONCURRENCY parents running concurrently,
        each at depth 1 (simulating nested calls). All should complete
        without deadlock because nested calls bypass the semaphore.
        """
        code = 'def run(x):\n    return "nested_ok"\n'
        results = []

        async def run_nested(i: int):
            tool = _make_python_code_tool(tmp_path, code)
            token = _code_tool_depth.set(1)
            try:
                r = await tool.run(None, x=str(i))
                results.append(r)
            finally:
                _code_tool_depth.reset(token)

        await asyncio.gather(*(run_nested(i) for i in range(CODE_TOOL_MAX_CONCURRENCY)))
        assert len(results) == CODE_TOOL_MAX_CONCURRENCY
        assert all(not r.is_error for r in results)


class TestTrustRefusal:
    @pytest.mark.asyncio
    async def test_trust_refusal_no_spawn(self, tmp_path):
        project = Project(name="untrusted", path=tmp_path / "untrusted")
        project.save_to_file()
        revoke_code_eval_trust(str(project.path))
        ct = _make_code_tool('def run(x):\n    return "should_not_run"\n')
        ct.parent = project
        pct = PythonCodeTool(ct, project)
        result = await pct.run(None, x="test")
        assert result.is_error
        assert "not trusted" in result.error_message.lower()


class TestToolCallRecorder:
    @pytest.mark.asyncio
    async def test_recorder_gets_entries(self, tmp_path):
        fake = FakeTool(
            "kiln_tool::add_numbers",
            "add_numbers",
            params=EMPTY_SCHEMA,
            result=ToolCallResult(output="42"),
        )
        log: list[ToolCallLogEntry] = []
        code = textwrap.dedent("""\
            from kiln import tools
            def run(x):
                r = tools.add_numbers()
                return r
        """)
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=["kiln_tool::add_numbers"],
            tool_call_recorder=log.append,
        )
        with patch(
            "kiln_ai.tools.tool_registry.tool_from_id_and_project",
            return_value=fake,
        ):
            result = await tool.run(None, x="test")
        assert not result.is_error
        assert len(log) == 1
        assert log[0].tool_name == "add_numbers"
        assert not log[0].is_error
        assert log[0].output_preview == "42"
        assert log[0].duration_ms >= 0


class TestAsyncToolsConcurrency:
    @pytest.mark.asyncio
    async def test_async_tools_gather_truly_concurrent(self, tmp_path):
        """async_tools + gather provides real parallelism via to_thread.

        Two fake tools each take ~0.3s. If sequential, wall clock >= 0.6s.
        With true concurrency via gather + to_thread, wall clock < 0.6s.
        """
        slow_fake = FakeTool(
            "kiln_tool::add_numbers",
            "add_numbers",
            params=EMPTY_SCHEMA,
            result=ToolCallResult(output="done"),
            delay=0.3,
        )
        code = textwrap.dedent("""\
            import asyncio, time
            from kiln import async_tools
            async def run(x):
                start = time.monotonic()
                a, b = await asyncio.gather(
                    async_tools.add_numbers(),
                    async_tools.add_numbers(),
                )
                elapsed = time.monotonic() - start
                return f"{elapsed:.2f}"
        """)
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=["kiln_tool::add_numbers"],
        )
        with patch(
            "kiln_ai.tools.tool_registry.tool_from_id_and_project",
            return_value=slow_fake,
        ):
            result = await tool.run(None, x="test")
        assert not result.is_error
        elapsed = float(result.output)
        assert elapsed < 0.6, f"Expected < 0.6s (concurrent), got {elapsed:.2f}s"


class _EchoFakeTool(KilnToolInterface):
    """Fake tool that echoes its kwargs back, proving per-call routing."""

    def __init__(self, tool_id: str, fn_name: str, params: dict):
        self._id = tool_id
        self._name = fn_name
        self._params = params

    async def id(self):
        return self._id

    async def name(self):
        return self._name

    async def description(self):
        return "echo"

    async def toolcall_definition(self) -> ToolCallDefinition:
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": "echo",
                "parameters": self._params,
            },
        }

    async def run(self, context=None, **kwargs) -> ToolCallResult:
        return ToolCallResult(output=json.dumps(kwargs, sort_keys=True))


class TestCallIdRouting:
    @pytest.mark.asyncio
    async def test_concurrent_calls_routed_to_correct_caller(self, tmp_path):
        """4 threads each pass a unique idx kwarg; each gets its own value back.

        The echo tool returns the kwargs it received. Each thread asserts it
        got back the idx it sent, proving call_id routing maps the right
        response to the right waiting caller under concurrency.
        """
        idx_schema = {
            "type": "object",
            "properties": {"idx": {"type": "string"}},
            "required": ["idx"],
        }
        code = textwrap.dedent("""\
            import json, threading
            from kiln import tools
            def run(x):
                results = [None] * 4
                errors = []
                def call_tool(i):
                    try:
                        raw = tools.add_numbers(idx=str(i))
                        results[i] = json.loads(raw)["idx"]
                    except Exception as e:
                        errors.append(f"thread {i}: {e}")
                threads = [threading.Thread(target=call_tool, args=(i,)) for i in range(4)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                if errors:
                    return "errors: " + str(errors)
                return ",".join(results)
        """)
        fake = _EchoFakeTool(
            "kiln_tool::add_numbers",
            "add_numbers",
            params=idx_schema,
        )
        tool = _make_python_code_tool(
            tmp_path,
            code,
            tool_allowlist=["kiln_tool::add_numbers"],
        )
        with patch(
            "kiln_ai.tools.tool_registry.tool_from_id_and_project",
            return_value=fake,
        ):
            result = await tool.run(None, x="test")
        assert not result.is_error
        parts = result.output.split(",")
        assert len(parts) == 4
        assert parts == ["0", "1", "2", "3"]


class TestUnicodePassthrough:
    @pytest.mark.asyncio
    async def test_unicode_not_escaped(self, tmp_path):
        """ensure_ascii=False: non-ASCII chars pass through un-escaped."""
        tool = _make_python_code_tool(
            tmp_path,
            'def run(x):\n    return {"name": "\\u65e5\\u672c\\u8a9e"}\n',
        )
        result = await tool.run(None, x="test")
        assert not result.is_error
        parsed = json.loads(result.output)
        assert parsed["name"] == "日本語"
        assert "\\u" not in result.output


class TestSpawnLockIdentity:
    def test_spawn_lock_shared(self):
        """PythonCodeTool and run_scorer share the same _spawn_lock."""
        from kiln_ai.adapters.eval import sandbox_worker

        assert (
            sandbox_worker.start_process_with_light_main.__module__
            == "kiln_ai.sandbox.spawn"
        )
        from kiln_ai.sandbox.spawn import _spawn_lock as shared_lock

        assert shared_lock is _spawn_lock
