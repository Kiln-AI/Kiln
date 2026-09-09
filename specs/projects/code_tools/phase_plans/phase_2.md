---
status: complete
---

# Phase 2: Execution Engine

## Overview

Implement the full execution engine for Code Tools: the child-side sandbox worker (`sandbox/worker.py`), the synthetic `kiln.tools` / `kiln.async_tools` modules (`sandbox/tools_api.py`), and the parent-side `PythonCodeTool.run()` orchestration in `tools/code_tool.py`. This phase makes code tools fully executable — spawning subprocesses, routing nested tool calls via IPC, enforcing depth caps, concurrency semaphores, and timeouts.

## Steps

### 1. Create `sandbox/tools_api.py` — synthetic modules + typed exceptions + bridge

The child-side bridge that provides `kiln.tools`, `kiln.async_tools`, and typed exceptions.

- **Typed exceptions**: `ToolNotAllowed`, `ToolTimeout`, `ToolCallError` (with `.tool`, `.message`, `.raw` attrs). These are importable from `kiln.tools`.
- **`ToolCallBridge`**: thread-safe bridge that allocates `call_id`s, sends `tool_call`/`list_tools` messages to the parent via the `requests` queue, and waits on per-call `threading.Event`s for replies from the `responses` queue.
  - `call(name, kwargs)`: JSON-roundtrips kwargs, allocates call_id, puts `tool_call` message, blocks on event, maps reply to return/exception.
  - `list_tools()`: puts `list_tools` message, returns list of dicts.
  - `start_dispatcher()`: daemon thread reading responses and resolving pending calls.
- **Module installation** (`install_tools_modules(requests, responses)`): creates `kiln`, `kiln.tools`, `kiln.async_tools` as `types.ModuleType`, installs into `sys.modules`. `tools.__getattr__` returns sync callable proxies; `async_tools.__getattr__` returns async proxies via `asyncio.to_thread`. Both modules expose `list_tools()` and the exception classes.

### 2. Create `sandbox/worker.py` — child process entry point

```python
def child_main(code: str, kwargs: dict, requests: Queue, responses: Queue) -> None:
```

- Redirects stdout/stderr to `StringIO` (PyInstaller guard); truncates to 64KB with marker.
- Calls `install_tools_modules(requests, responses)` to set up the synthetic `kiln` module.
- `exec(compile(code, "<code_tool>", "exec"), namespace)`.
- Looks up `namespace["run"]`; missing/not-callable -> result error.
- `call_entrypoint(run_fn, kwargs)` (handles sync/async).
- Serializes return value: `str` pass-through; `dict/list/int/float/bool/None` -> `json.dumps`; non-serializable -> error naming the type.
- Trimmed traceback: keeps frames from `<code_tool>` onward.
- Puts exactly one `result` message.

### 3. Implement `PythonCodeTool.run()` in `tools/code_tool.py`

Full parent-side orchestration:

- **`ChildOutcome` dataclass**: `ok`, `error`, `traceback_str`, `stdout`, `stderr`, `duration_ms`, `timed_out`, `crashed`.
- **`ToolCallLogEntry` dataclass**: `tool_name`, `arguments`, `output_preview`, `is_error`, `duration_ms`.
- **Trust check (stopgap)**: `is_code_eval_trusted(str(project.path))` -> `ToolCallResult(is_error=True)`. Marked with `# TODO: replace with real trust mechanism (Phase 6)`.
- **Depth check**: `contextvars.ContextVar("_code_tool_depth", default=0)`. At entry, `depth >= 10` -> error. Else `depth + 1` via token.
- **Semaphore**: module-level `CODE_TOOL_MAX_CONCURRENCY = 8`. `asyncio.Semaphore` created lazily. Acquired only at depth 0; nested bypasses.
- **`_invoke()` method**: spawns child via `start_process_with_light_main`, runs message pump polling `requests` queue every 0.1s, checking deadline and child liveness. Dispatches `tool_call`/`list_tools` messages to `_serve()` as `asyncio.create_task`. Cancels pending tasks in `finally`. Cleans up queues and process.
- **`_serve()` method**: resolves tool name against allowlist (lazy name->ToolId map from `tool_allowlist`), validates kwargs against tool's schema, calls `await tool.run()`, puts reply. Records to `tool_call_recorder`.
- **`run()` method**: maps `ChildOutcome` -> `ToolCallResult` per spec error table.
- **Constructor**: accepts `tool_call_recorder: Callable[[ToolCallLogEntry], None] | None = None`.

### 4. Wire name resolution in `_serve()`

- Build lazy name->ToolId map from `code_tool.tool_allowlist`. For each tool ID, derive the function name locally: MCP last segment, RAG `rag_config.tool_name`, code tool `tool_function_name`, built-in known constants, kiln_task server properties.
- No match -> `not_allowed` reply listing available names.
- Two matches -> `call_error` "ambiguous".
- Resolve via `tool_from_id_and_project(tool_id, project, task)`.
- Validate kwargs via `validate_schema_with_value_error`.
- `await tool.run(context, **kwargs)`.

## Tests

Tests go in `libs/core/kiln_ai/sandbox/test_code_tool_execution.py` (new file — no existing test file for execution engine).

### Child/protocol tests (real spawns):
- `test_sync_run_returns_string`: sync `run()` returns a string result
- `test_async_run_returns_string`: async `run()` with internal gather
- `test_async_run_with_asyncio_run_errors`: `asyncio.run()` inside async `run` -> clear error
- `test_return_serialization_matrix`: parametrized — str pass-through, dict/list/int/float/bool/None -> json, non-serializable nested value -> error, non-serializable top-level type -> error
- `test_string_passthrough_no_parsing`: JSON-object string returned as str, not parsed
- `test_stdout_stderr_capture`: captured correctly
- `test_stdout_truncation`: >64KB truncated with marker
- `test_traceback_shows_code_tool_lines`: traceback trimmed to `<code_tool>` frames
- `test_missing_run_defense`: code without `run` -> error
- `test_import_forms`: `from kiln import tools`, `import kiln.tools`, `from kiln.tools import ToolCallError` all work
- `test_exception_classes_identical_across_modules`: same exception objects in both modules
- `test_json_unsafe_kwargs_error`: non-JSON-serializable tool kwargs raise in-frame ToolCallError

### Parent-side tests (pytest-asyncio, mock tools):
- `test_happy_path`: simple run returning a string
- `test_nested_tool_success`: code calls a tool, gets result
- `test_nested_tool_error`: code calls a tool that returns is_error
- `test_nested_tool_not_allowed`: code calls unknown tool -> ToolNotAllowed with available names
- `test_nested_tool_ambiguous`: two allowlisted tools with same function name -> ToolCallError
- `test_nested_tool_invalid_kwargs`: bad kwargs -> ToolCallError
- `test_list_tools`: `tools.list_tools()` returns correct content
- `test_timeout_kills_child`: timeout during sleep
- `test_timeout_during_nested_call`: timeout while nested call in flight
- `test_crash_via_os_exit`: `os._exit(3)` -> crashed outcome
- `test_depth_cap_at_10`: nested code-tool chain hits depth 10 -> error
- `test_semaphore_top_level_only_no_deadlock`: 8 parents each spawning a nested code tool -> all complete (deadlock regression test)
- `test_trust_refusal`: untrusted project -> error without spawn
- `test_tool_call_recorder`: recorder gets entries with correct fields
- `test_spawn_lock_identity`: `PythonCodeTool` and `run_scorer` share `_spawn_lock`
