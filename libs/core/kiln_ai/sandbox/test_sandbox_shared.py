"""Tests for sandbox shared helpers — spawn lock identity and call_entrypoint."""

import asyncio

import pytest

from kiln_ai.adapters.eval.sandbox_worker import execute_scorer_bridged
from kiln_ai.datamodel.project import Project
from kiln_ai.sandbox.entrypoint import call_entrypoint
from kiln_ai.sandbox.spawn import _spawn_lock, start_process_with_light_main
from kiln_ai.tools.sandbox_bridge import NestedToolServer, run_bridged_child


class TestSpawnLockIdentity:
    def test_spawn_lock_shared_with_eval(self):
        """Code evals and code tools share the same _spawn_lock (PyInstaller #7410)."""
        from kiln_ai.sandbox import spawn as spawn_mod

        assert spawn_mod._spawn_lock is _spawn_lock

    def test_bridge_delegates_to_shared_spawn_helper(self):
        """The shared bridge spawns via start_process_with_light_main from sandbox.spawn."""
        from kiln_ai.tools import sandbox_bridge

        assert (
            sandbox_bridge.start_process_with_light_main
            is start_process_with_light_main
        )

    @pytest.mark.asyncio
    async def test_scorer_runs_through_bridge(self):
        """Regression: a scorer executes through the shared bridge and returns its dict."""
        code = (
            "def score(output, trace, reference_data, task_input):\n"
            "    return {'ok': 1.0}\n"
        )
        server = NestedToolServer(
            allowlist=[], project=Project(name="shared_test"), task=None, context=None
        )
        res = await run_bridged_child(
            target=execute_scorer_bridged,
            args=(
                code,
                {
                    "output": "x",
                    "trace": None,
                    "reference_data": None,
                    "task_input": "y",
                },
            ),
            timeout_s=10,
            server=server,
        )
        assert res.result_msg is not None
        assert res.result_msg["ok"] == {"ok": 1.0}


class TestCallEntrypoint:
    def test_sync_function(self):
        def fn(x):
            return x * 2

        assert call_entrypoint(fn, {"x": 5}) == 10

    def test_async_function(self):
        async def fn(x):
            return x + 1

        assert call_entrypoint(fn, {"x": 5}) == 6

    def test_async_with_gather(self):
        async def fn(values):
            async def double(v):
                return v * 2

            return await asyncio.gather(*(double(v) for v in values))

        result = call_entrypoint(fn, {"values": [1, 2, 3]})
        assert result == [2, 4, 6]

    def test_sync_returning_non_coroutine(self):
        def fn():
            return "plain"

        assert call_entrypoint(fn, {}) == "plain"

    def test_propagates_exception(self):
        def fn():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            call_entrypoint(fn, {})

    def test_async_propagates_exception(self):
        async def fn():
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError, match="async boom"):
            call_entrypoint(fn, {})
