---
status: complete
---

# Phase 11: code_eval serialize execution

## Overview

Two changes that improve the code_eval subprocess execution:

1. **Item 3.1 — Full-execution serialization.** The existing `_spawn_lock` (a `threading.Lock` in `sandbox_worker.py`) only serializes the `p.start()` call (PyInstaller spawn race, issue #7410). Per spec, the *entire* code_eval execution should be serialized so only one sandboxed subprocess runs at a time. This is implemented via a module-level `asyncio.Lock` in `v2_eval_code_eval.py`, acquired around the `await loop.run_in_executor(...)` call. Waiting code_evals suspend as coroutines (not blocking executor threads). The narrow `_spawn_lock` in `sandbox_worker.py` is kept as-is.

2. **Item 6.11 — Sandbox timeout test speed-up.** In `test_sandbox_worker.py`, the timeout test uses `sleep(60)` with a 2s timeout. Change to `sleep(10)` with a 1s timeout for faster failure while keeping the same safety margin.

## Steps

1. In `v2_eval_code_eval.py`, add a module-level `asyncio.Lock` named `_code_eval_execution_lock`.
2. In `CodeEvalAdapter.evaluate()`, wrap the `await loop.run_in_executor(...)` call with `async with _code_eval_execution_lock:` — placed after the trust check but around the executor call and its result processing. This ensures only one code_eval subprocess runs at a time.
3. In `test_sandbox_worker.py`, change `test_timeout`: `sleep(60)` -> `sleep(10)`, `timeout=2` -> `timeout=1`.
4. Add a serialization test in `test_v2_eval_code_eval.py` that proves two concurrent `evaluate()` calls do not overlap (use a shared counter / timing approach with `asyncio.gather`).

## Tests

- `test_concurrent_evaluations_are_serialized`: Two `evaluate()` calls launched with `asyncio.gather` should never overlap. Instrument via a mock `run_scorer` that increments/decrements a counter with a small sleep, asserting the counter never exceeds 1.
- `test_timeout` (modified): Verify the timeout test still works with the faster `sleep(10)` / 1s timeout values.
