"""Tests for sandbox_worker -- multiprocessing scorer execution.

These tests SPAWN child processes. Keep them fast. Scorer code is passed
as a string so nothing local needs pickling.
"""

import pytest

from kiln_ai.adapters.eval.sandbox_worker import run_scorer


def _inputs(output: str = "hello", **overrides: object) -> dict:
    defaults: dict = {
        "output": output,
        "trace": None,
        "reference_data": None,
        "task_input": "test input",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_scorer_returns_dict(self):
        code = (
            "def score(output, trace, reference_data, task_input):\n"
            "    return {'accuracy': 1.0}\n"
        )
        result = run_scorer(code, _inputs(), timeout=10)
        assert "ok" in result
        assert result["ok"] == {"accuracy": 1.0}

    def test_scorer_uses_output(self):
        code = (
            "def score(output, trace, reference_data, task_input):\n"
            "    return {'has_hello': 1.0 if 'hello' in output else 0.0}\n"
        )
        result = run_scorer(code, _inputs(output="hello world"), timeout=10)
        assert result["ok"] == {"has_hello": 1.0}

        result2 = run_scorer(code, _inputs(output="goodbye"), timeout=10)
        assert result2["ok"] == {"has_hello": 0.0}

    def test_scorer_uses_stdlib(self):
        code = (
            "import math\n"
            "def score(output, trace, reference_data, task_input):\n"
            "    return {'sqrt4': math.sqrt(4)}\n"
        )
        result = run_scorer(code, _inputs(), timeout=10)
        assert result["ok"] == {"sqrt4": 2.0}

    def test_scorer_uses_kiln_helpers(self):
        code = (
            "from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers\n"
            "def score(output, trace, reference_data, task_input):\n"
            "    return {'pass': KilnEvalHelpers.pass_fail(True)}\n"
        )
        result = run_scorer(code, _inputs(), timeout=10)
        assert result["ok"] == {"pass": 1.0}


# ---------------------------------------------------------------------------
# Async scorer support
# ---------------------------------------------------------------------------


class TestAsyncScorer:
    def test_async_score_returns_dict(self):
        code = (
            "async def score(output, trace, reference_data, task_input):\n"
            "    return {'accuracy': 1.0}\n"
        )
        result = run_scorer(code, _inputs(), timeout=10)
        assert "ok" in result
        assert result["ok"] == {"accuracy": 1.0}

    def test_async_score_with_gather(self):
        code = (
            "import asyncio\n"
            "\n"
            "async def _check_a(output):\n"
            "    return 1.0 if 'hello' in output else 0.0\n"
            "\n"
            "async def _check_b(output):\n"
            "    return 0.5\n"
            "\n"
            "async def score(output, trace, reference_data, task_input):\n"
            "    a, b = await asyncio.gather(_check_a(output), _check_b(output))\n"
            "    return {'check_a': a, 'check_b': b}\n"
        )
        result = run_scorer(code, _inputs(output="hello world"), timeout=10)
        assert "ok" in result
        assert result["ok"] == {"check_a": 1.0, "check_b": 0.5}

    def test_async_score_raising(self):
        code = (
            "async def score(output, trace, reference_data, task_input):\n"
            "    raise ValueError('async boom')\n"
        )
        result = run_scorer(code, _inputs(), timeout=10)
        assert "error" in result
        assert "async boom" in result["error"]
        assert "traceback" in result

    def test_async_score_timeout(self):
        code = (
            "import asyncio\n"
            "async def score(output, trace, reference_data, task_input):\n"
            "    await asyncio.sleep(10)\n"
            "    return {'x': 1.0}\n"
        )
        with pytest.raises(RuntimeError, match="timed out"):
            run_scorer(code, _inputs(), timeout=1)


# ---------------------------------------------------------------------------
# Stdout / stderr capture
# ---------------------------------------------------------------------------


class TestCapture:
    def test_stdout_captured(self):
        code = (
            "def score(output, trace, reference_data, task_input):\n"
            "    print('debug info')\n"
            "    return {'x': 1.0}\n"
        )
        result = run_scorer(code, _inputs(), timeout=10)
        assert "ok" in result
        assert "debug info" in result["stdout"]

    def test_stderr_captured(self):
        code = (
            "import sys\n"
            "def score(output, trace, reference_data, task_input):\n"
            "    print('err msg', file=sys.stderr)\n"
            "    return {'x': 1.0}\n"
        )
        result = run_scorer(code, _inputs(), timeout=10)
        assert "ok" in result
        assert "err msg" in result["stderr"]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestErrors:
    def test_runtime_exception(self):
        code = (
            "def score(output, trace, reference_data, task_input):\n"
            "    raise ValueError('boom')\n"
        )
        result = run_scorer(code, _inputs(), timeout=10)
        assert "error" in result
        assert "boom" in result["error"]
        assert "traceback" in result

    def test_missing_score_function(self):
        code = "x = 1\n"
        result = run_scorer(code, _inputs(), timeout=10)
        assert "error" in result
        assert "score" in result["error"].lower()

    def test_score_not_callable(self):
        code = "score = 42\n"
        result = run_scorer(code, _inputs(), timeout=10)
        assert "error" in result
        assert "not callable" in result["error"]

    def test_syntax_error_in_code(self):
        code = "def score(\n"
        result = run_scorer(code, _inputs(), timeout=10)
        assert "error" in result
        assert "traceback" in result

    def test_timeout(self):
        code = (
            "import time\n"
            "def score(output, trace, reference_data, task_input):\n"
            "    time.sleep(10)\n"
            "    return {'x': 1.0}\n"
        )
        with pytest.raises(RuntimeError, match="timed out"):
            run_scorer(code, _inputs(), timeout=1)

    def test_crash_via_os_exit(self):
        code = (
            "import os\n"
            "def score(output, trace, reference_data, task_input):\n"
            "    os._exit(1)\n"
        )
        with pytest.raises(RuntimeError, match="exit code"):
            run_scorer(code, _inputs(), timeout=10)
