---
status: complete
---

# Phase 3: Extract the shared parent pump

## Overview

Pure, behavior-preserving refactor of shipped code-tool internals (arch §3.1). Today the
sandbox pump + nested-call server live inside `PythonCodeTool` (`code_tool.py`) and the
concurrency primitives are module-level. Extract them into a reusable, parent-side unit
(`tools/sandbox_bridge.py`) so Phase 4 can host the same pump for code evals. No observable
behavior change to code tools; existing `sandbox/test_code_tool_execution.py` proves it.

## Steps

1. **New file `libs/core/kiln_ai/tools/sandbox_bridge.py`** (parent-side; may import the Kiln stack).
   Extract from `code_tool.py`:
   - `CODE_SANDBOX_MAX_CONCURRENCY = 16` — REPLACES `CODE_TOOL_MAX_CONCURRENCY = 8` (arch §3.4;
     intentionally raises the code-tool bound 8 → 16 as the shared pool unifies).
   - `_depth: ContextVar[int]` (was `_code_tool_depth`), `_semaphore`, `_semaphore_init_lock`,
     `_get_semaphore()`.
   - `ToolCallLogEntry` dataclass (moved; re-exported from `code_tool.py` for API compat).
   - `BridgeResult` dataclass: `result_msg: dict | None`, `timed_out`, `crashed`, `exit_code`,
     `stdout`, `stderr`, `duration_ms`.
   - `NestedToolServer(allowlist, project, task, context, recorder=None)` with `async serve(msg, responses)`
     (verbatim `_serve` — tool_call + list_tools), `async name_map()` (`_build_name_map`),
     `async tools_info()` (`_get_tools_info`), plus `_canonical_tool_name` and `_record`.
     Parameterized on the passed-in allowlist/project/task/context/recorder.
   - `async run_bridged_child(*, target, args, timeout_s, requests, responses, server) -> BridgeResult`:
     verbatim port of `_run_child`'s spawn+pump loop MINUS result interpretation. Owns the depth cap
     (>=10 → error `result_msg`), the depth-0-only semaphore acquisition (moved from `_invoke`),
     spawns `target(*args, requests, responses)` via `start_process_with_light_main`, dispatches
     tool_call/list_tools to `server.serve(...)`, returns `BridgeResult` on first `result`, timeout,
     or crash. Closes the queues in `finally`.
   - Move `_poll_get`, `_close_queues`, `_render_params_schema`, `_example_kwargs`.
   - Import cycle guard: `serve` uses a function-local `from kiln_ai.tools.code_tool import PythonCodeTool`
     for the unchanged `is_timeout` check.

2. **Refactor `PythonCodeTool` (`code_tool.py`) to a thin caller.**
   - Keep `ChildOutcome` here; re-export `ToolCallLogEntry` from `sandbox_bridge`.
   - `_invoke(context, kwargs)`: build a `NestedToolServer` (allowlist=`self._code_tool.tool_allowlist`,
     project, task, `context`, recorder=`self._tool_call_recorder`), create the spawn queues, call
     `run_bridged_child(target=child_main, args=(self._code_tool.code, kwargs), timeout_s=...)`, map
     `BridgeResult.result_msg` → `ChildOutcome` EXACTLY as today (ok / error+traceback / timed_out / crashed).
   - Keep `_build_name_map()` as a thin delegator to a `NestedToolServer` (a test calls it directly).
   - Delete the now-moved bodies (`_run_child`, `_serve`, `_get_tools_info`, `_canonical_tool_name`,
     `_record`, depth/semaphore module state, helper fns).

3. **Update references to relocated symbols in tests** (import-path/name only, no behavior changes):
   - `sandbox/test_code_tool_execution.py`: import `CODE_SANDBOX_MAX_CONCURRENCY` and `_depth` from
     `sandbox_bridge`; keep `PythonCodeTool`/`ToolCallLogEntry` from `code_tool`. Update the 4 body
     usages. The `test_semaphore_top_level_only_no_deadlock` count follows the bound (now 16); no `== 8`
     assertion exists, so no numeric assertion changes.

## Tests

- Existing `sandbox/test_code_tool_execution.py` — stays green unchanged (behavioral proof of the extraction).
- Existing `sandbox/test_sandbox_shared.py`, `adapters/eval/test_sandbox_worker.py`,
  `datamodel/test_code_tool.py`, `tools/test_tool_registry.py`, `studio_server/test_code_tool_api.py` — stay green.
- New `tools/test_sandbox_bridge.py` — module-surface tests: `CODE_SANDBOX_MAX_CONCURRENCY == 16`;
  `BridgeResult` shape; `NestedToolServer.name_map`/`tools_info` resolve allowlisted tools; `serve`
  handles tool_call success/not-allowed/list_tools and records via recorder; `run_bridged_child`
  depth-cap error result; timeout and crash `BridgeResult`s via a fake target; `_poll_get`/`_close_queues`.
