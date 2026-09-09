---
status: complete
---

# Phase 1: Library Foundations

## Overview

Establish the core library infrastructure for Code Tools: the sandbox package (shared spawn helper + entrypoint), the CodeTool datamodel, tool_id extensions, and a registry refactor. The existing eval sandbox_worker is mechanically refactored to delegate to the new shared helpers, keeping the entire eval test suite green and unchanged.

## Steps

### 1. Create `kiln_ai/sandbox/` package (stdlib-only)

1a. `sandbox/__init__.py` — empty.

1b. `sandbox/spawn.py` — Extract `_spawn_lock` and the `__main__` stub-swap block from `adapters/eval/sandbox_worker.py` into:
```python
_spawn_lock = threading.Lock()

def start_process_with_light_main(p: multiprocessing.process.BaseProcess) -> None:
```
This is THE process-global lock shared by both code-evals and code tools.

1c. `sandbox/entrypoint.py` — Shared entrypoint caller:
```python
def call_entrypoint(fn: Callable, kwargs: dict) -> Any:
    result = fn(**kwargs)
    if inspect.iscoroutine(result):
        result = asyncio.run(result)
    return result
```

### 2. Refactor `adapters/eval/sandbox_worker.py`

Mechanical, behavior-identical refactor:
- `_execute_scorer` delegates to `call_entrypoint(score_fn, kwargs)` instead of inline `asyncio.run`.
- `run_scorer` delegates to `start_process_with_light_main(p)` instead of inline lock + stub swap.
- Remove the module-level `_spawn_lock` (now imported from `sandbox.spawn`).
- All existing eval tests must pass unchanged.

### 3. Create `datamodel/code_tool.py`

`CodeTool(KilnParentedModel)` with:
- Fields per architecture section 3 (name, description, is_archived, tool_function_name, tool_description, parameters_schema, code, timeout_seconds, tool_allowlist).
- `tool_function_name` field validator: `^[a-z][a-z0-9_]{0,63}$`.
- Model validator for code trio: size cap (64KB UTF-8), `compile()`, AST check for module-level `run` (`FunctionDef` or `AsyncFunctionDef`).
- Model validator for allowlist: reject skill IDs, reject unmanaged IDs, reject duplicates, reject self-reference.
- `parameters_schema` validator using `validate_schema_dict(v, require_object=True)`.

### 4. Register CodeTool as Project child

- Add `"code_tools": CodeTool` to `Project.parent_of`.
- Add typed accessor method `code_tools()`.
- Add import and export in `datamodel/__init__.py`.

### 5. Extend `datamodel/tool_id.py`

- Add `CODE_TOOL_ID_PREFIX = "kiln_tool::code::"`.
- Add `build_code_tool_id(code_tool_id)` and `code_tool_id_from_tool_id(tool_id)` helpers.
- Add branch in `_check_tool_id` for `CODE_TOOL_ID_PREFIX`.

### 6. Refactor `tools/tool_registry.py`

- Add `tool_from_id_and_project(tool_id, project, task=None)` that resolves tools given a project directly (needed for test endpoint and nested-call dispatcher).
- Refactor `tool_from_id(tool_id, task)` to be a thin wrapper deriving the project from the task and calling `tool_from_id_and_project`.
- Add CODE_TOOL_ID_PREFIX branch that loads the CodeTool artifact and wraps it in a placeholder (lazy import to avoid circular dependency; full PythonCodeTool is phase 2).

## Tests

### test_code_tool.py (new)
- `test_valid_sync_run`: CodeTool with `def run(...)` accepted
- `test_valid_async_run`: CodeTool with `async def run(...)` accepted
- `test_missing_run_rejected`: code without `run` function rejected
- `test_nested_run_rejected`: `run` defined inside a class/function rejected
- `test_run_not_callable_rejected`: `run = 42` rejected
- `test_syntax_error_rejected`: invalid Python syntax rejected
- `test_code_size_cap`: code > 64KB rejected
- `test_schema_validation`: invalid schema rejected; valid schema accepted
- `test_function_name_pattern`: valid/invalid function names (parametrized)
- `test_allowlist_rejects_skill_ids`: skill tool IDs in allowlist rejected
- `test_allowlist_rejects_unmanaged_ids`: unmanaged tool IDs rejected
- `test_allowlist_rejects_duplicates`: duplicate tool IDs rejected
- `test_allowlist_rejects_self_reference`: self-referencing code tool ID rejected
- `test_defaults`: default values correct (timeout=60, allowlist=[], etc.)
- `test_save_load_roundtrip`: save to file and load back with parent project
- `test_project_parent_registration`: Project.code_tools() returns CodeTool instances

### test_tool_id.py (append)
- `test_valid_code_tool_ids`: code tool IDs accepted by `_check_tool_id`
- `test_invalid_code_tool_ids`: malformed code tool IDs rejected
- `test_build_code_tool_id`: builder produces correct format
- `test_code_tool_id_from_tool_id`: parser extracts correct ID

### test_tool_registry.py (append)
- `test_tool_from_id_and_project_builtins`: builtins work without project
- `test_tool_from_id_and_project_mcp`: MCP tools work with project
- `test_tool_from_id_code_tool`: code tool ID resolves correctly
- `test_tool_from_id_code_tool_missing`: missing code tool raises ValueError

### sandbox tests
- Verify `run_scorer` still uses `_spawn_lock` from `sandbox.spawn` (identity assertion)
- Verify `call_entrypoint` handles sync and async functions
- All existing `test_sandbox_worker.py` and `test_sandbox_worker_perf.py` pass unchanged
