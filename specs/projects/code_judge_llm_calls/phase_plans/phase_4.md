---
status: complete
---

# Phase 4: Code-eval bridge integration

## Overview

Wire the code-eval sandbox onto the shared bridge (arch §3.2–3.4). Code judges can now
call `from kiln import tools` / `async_tools` (incl. `tools.llm` / `tools.llm_judge`) from
their `score()`. The single-result-queue scorer worker is replaced by the two-queue bridge
protocol; `CodeEvalAdapter.evaluate` hosts the parent pump and the per-eval nested-tool
server; the global code-eval execution lock is deleted (concurrency is now the shared
depth-0 semaphore inside `run_bridged_child`). Also lands two Phase-3 review carry-forwards:
queue lifecycle centralization inside `run_bridged_child`, and a generalized depth-cap message.

## Steps

1. **`adapters/eval/sandbox_worker.py`** — replace `run_scorer` + `_execute_scorer` with
   `execute_scorer_bridged(code, inputs, requests, responses)`:
   - redirect stdout/stderr (existing), `install_tools_modules(requests, responses)`,
     `exec(compile(code, "<code_eval>", "exec"), namespace)`.
   - keep existing `score` lookup + signature checks (defined / callable / accepts
     `output`|`trace`) and declared-param injection from `output`/`trace`/`reference_data`/
     `task_input`; each validation-failure puts `{"type":"result","error":...,stdout,stderr}`.
   - `result = call_entrypoint(score_fn, call_kwargs)` (sync/async).
   - success: `requests.put({"type":"result","ok":result,stdout,stderr})` — `ok` is the scores
     dict **verbatim** (no `_serialize_result`).
   - exception: `requests.put({"type":"result","error":str(exc),"traceback":format_exc(),stdout,stderr})`.
   - Remove single-queue `run_scorer`; drop `multiprocessing`/`queue`/`start_process_with_light_main` imports.

2. **`adapters/eval/v2_eval_code_eval.py`** — `CodeEvalAdapter.evaluate` hosts the pump:
   - trust gate unchanged, short-circuits before any spawn.
   - `inputs = {output, trace, reference_data, task_input}` (existing).
   - `server = NestedToolServer(allowlist=props.tool_allowlist, project=self.target_task.parent,
     task=self.target_task, context=ToolCallContext(allow_saving=False,
     eval_output_schema=BaseEval.build_score_schema(self.eval, allow_float_scores=False)),
     recorder=None)`.
   - `res = await run_bridged_child(target=execute_scorer_bridged, args=(props.code, inputs),
     timeout_s=float(props.timeout_seconds), server=server)`.
   - `res.timed_out` → RuntimeError timed out; `res.crashed` → RuntimeError crashed;
     `result_msg` has `error` → RuntimeError failed + traceback; else `raw = result_msg["ok"]`,
     require dict, `return V2EvalResult(scores=self._validate_scores(raw))`.
   - Delete `_code_eval_execution_lock` + the `async with`. Keep grant/revoke/is_code_eval_trusted
     and `_resolve_project_path`/`_validate_scores`.

3. **Carry-forward — centralize queue lifecycle in `run_bridged_child` (`tools/sandbox_bridge.py`)**:
   - Move `multiprocessing.get_context("spawn")` + two `Queue()` creations INTO `run_bridged_child`
     (after depth/semaphore gates), close them in its `finally`. Drop the `requests`/`responses`
     params from the signature. Remove `_close_queues` from `_pump`'s finally.
   - Update `PythonCodeTool._invoke` to match (no queue creation; drop `multiprocessing` import).

4. **Carry-forward — generalize the depth-cap message**: `"max code tool depth exceeded — check
   for a cycle"` → `"maximum nested code execution depth exceeded — check for a cycle"`. Update the
   two tests asserting the old string.

5. **Update existing tests broken by the removal of `run_scorer`**:
   - `test_sandbox_worker.py` / `test_sandbox_worker_perf.py` / `_heavy_main_bench.py`: sync
     `run_scorer` helper that spawns `execute_scorer_bridged` via `run_bridged_child` (empty server).
   - `test_v2_eval_code_eval.py`: patch `run_bridged_child` (AsyncMock → `BridgeResult`) instead of
     `run_scorer`; remove the now-invalid global-lock serialization test.
   - `test_sandbox_shared.py` / `test_code_tool_execution.py` (spawn-lock identity + depth msg).
   - `test_sandbox_bridge.py`: drop `requests`/`responses` kwargs; new depth msg.
   - `app/desktop/studio_server/test_eval_api.py`: patch `run_bridged_child`.

## Tests

- New `adapters/eval/test_code_eval_bridge.py` (real spawns):
  - `score()` calls `tools.llm_judge` (patch `adapter_for_task` in parent) → scores route back.
  - `score()` calls `tools.llm` (text + schema→JSON string).
  - sync and `async def score` using `asyncio.gather` over two `async_tools.llm` calls.
  - allowlist enforcement: `tools.<not_allowlisted>` → `ToolNotAllowed`.
  - timeout kills a child mid-LLM-call (parent-side adapter hangs).
  - PARALLEL code evals run concurrently (wall-clock < sum of per-item sleeps) — regression vs deleted lock.
  - trust short-circuit before spawn (`run_bridged_child` not called).
  - identity: code tools and code evals share one `run_bridged_child` / `_spawn_lock` / semaphore.
- `test_code_eval_samples.py` — unchanged, still green (real scorer sample code through the bridge).
</content>
</invoke>
