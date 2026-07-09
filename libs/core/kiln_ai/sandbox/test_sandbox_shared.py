"""Tests for sandbox shared helpers — spawn lock identity and call_entrypoint."""

import asyncio

import pytest

from kiln_ai.adapters.eval import sandbox_worker
from kiln_ai.adapters.eval.sandbox_worker import run_scorer
from kiln_ai.sandbox.entrypoint import call_entrypoint
from kiln_ai.sandbox.spawn import _spawn_lock, start_process_with_light_main


class TestSpawnLockIdentity:
    def test_spawn_lock_shared_with_eval(self):
        """run_scorer and code tools share the same _spawn_lock (PyInstaller #7410)."""
        from kiln_ai.sandbox import spawn as spawn_mod

        assert spawn_mod._spawn_lock is _spawn_lock

    def test_run_scorer_delegates_to_shared_helpers(self):
        """sandbox_worker uses start_process_with_light_main from sandbox.spawn."""
        assert (
            sandbox_worker.start_process_with_light_main
            is start_process_with_light_main
        )

    def test_run_scorer_still_works(self):
        """Regression: run_scorer delegates to shared helpers and still works."""
        code = (
            "def score(output, trace, reference_data, task_input):\n"
            "    return {'ok': 1.0}\n"
        )
        result = run_scorer(
            code,
            {"output": "x", "trace": None, "reference_data": None, "task_input": "y"},
            timeout=10,
        )
        assert result["ok"] == {"ok": 1.0}


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
