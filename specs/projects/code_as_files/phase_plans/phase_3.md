---
status: complete
---

# Phase 3: The `kiln` test shim

## Overview

Two parts, per implementation_plan.md Phase 3, functional_spec §5/§6, architecture §4/§9.

**A) Behavior-preserving extraction (decision 6).** Factor the shared synthetic
`kiln.tools` / `kiln.async_tools` *surface* — the proxy attribute behavior, the
`list_tools` wiring, and the three exception classes (`ToolNotAllowed`,
`ToolTimeout`, `ToolCallError`) — out of `sandbox/tools_api.py` into a new
stdlib-only helper `sandbox/tools_surface.py` that BOTH the sandbox bridge and
the new test shim import. This is a pure refactor: the sandbox runtime must
behave exactly as before, and the existing sandbox suite must pass unchanged
(the extraction guard). No change to execution semantics, nesting, trust,
timeouts, or the injected-module wiring beyond moving shared code behind an
import.

**B) The kiln test shim.** A new `tool_testing/` pytest plugin shipped with
`kiln_ai`, registered via a `pytest11` entry point, that installs the SAME
synthetic surface (built from the extracted helper) into `sys.modules` at plugin
load — so `from kiln import tools` at the top of an author's `tool.py` resolves
during collection — and provides a function-scoped, auto-reset `kiln_tools`
fixture backed by an in-process fake bridge. Never spawns a subprocess, never
calls a real tool, never loaded inside the sandbox.

## Steps

### Part A — extraction

1. **New `libs/core/kiln_ai/sandbox/tools_surface.py`** (stdlib only). Holds the
   one definition of the surface:
   - The three exception classes `ToolNotAllowed`, `ToolTimeout`,
     `ToolCallError` (moved verbatim from `tools_api.py`, same `.tool` /
     `.message` / `.raw` attributes and constructors).
   - `_SyncToolsModule` / `_AsyncToolsModule` (`types.ModuleType` subclasses,
     moved verbatim — `__getattr__` returns proxies that call
     `bridge.call(name, args, kw)` / `asyncio.to_thread(bridge.call, ...)`).
   - A `ToolBridge` `Protocol` documenting the required bridge shape
     (`.call(name, args, kwargs) -> str`, `.list_tools() -> list[dict]`).
   - `build_tools_modules(bridge) -> (kiln_mod, tools_mod, async_tools_mod)` —
     builds the three module objects wired to `bridge` (identical wiring to the
     current `install_tools_modules`: exception classes attached, sync
     `list_tools = bridge.list_tools`, async `list_tools` via
     `asyncio.to_thread`), WITHOUT installing them.
   - `install_tools_modules_for_bridge(bridge)` — calls `build_tools_modules`
     then registers `kiln` / `kiln.tools` / `kiln.async_tools` in `sys.modules`.

2. **Refactor `libs/core/kiln_ai/sandbox/tools_api.py`** to import from
   `tools_surface`:
   - Import `ToolNotAllowed`, `ToolTimeout`, `ToolCallError`,
     `install_tools_modules_for_bridge` from `tools_surface`; re-export the three
     exceptions (module-level names preserved for any importer / back-compat).
   - `ToolCallBridge` now references the imported exceptions (unchanged logic).
   - `install_tools_modules(requests, responses)` keeps its exact signature and
     behavior: build `ToolCallBridge`, `start_dispatcher()`, then delegate module
     construction/installation to `install_tools_modules_for_bridge(bridge)`;
     return the bridge.
   - Delete the now-moved `_SyncToolsModule` / `_AsyncToolsModule` definitions.
   - `worker.py` still does `from kiln_ai.sandbox.tools_api import
     install_tools_modules` — unchanged.

### Part B — the shim

3. **New package `libs/core/kiln_ai/tool_testing/`** (stdlib + kiln_ai only):
   - `fake_bridge.py`:
     - `RecordedToolCall` dataclass: `name: str`, `arguments: dict[str, Any]`
       (so `kiln_tools.calls[0].name` works).
     - `FakeToolBridge`: an in-process registry-backed bridge satisfying the
       `ToolBridge` protocol.
       - `set(name, reply, *, declaration=None)` — `reply` is `str` (returned
         verbatim) or callable `(**kwargs) -> str`; validates type; records a
         declaration (`{"name": name, **declaration}`) for `list_tools`.
       - `set_error(name, exc)` — register an exception instance to raise;
         records a declaration too.
       - `calls: list[RecordedToolCall]` — ordered record.
       - `call(name, args, kwargs) -> str` — records the call first (under a
         lock), then dispatches in the SAME order the runtime does
         (`tools/code_tool.py`: not-allowed branch precedes the positional-args
         branch): a name is "registered" if it has a reply OR an error;
         unregistered name → `ToolNotAllowed` FIRST (regardless of arguments,
         mirroring the runtime and its `test_positional_on_nonsense_name_still_not_allowed`);
         only then, for a registered name, positional args → `ToolCallError`
         (keyword-args-only fidelity); registered error → raise it; callable
         reply → `reply(**kwargs)` (must return `str`); str reply → returned
         verbatim.
       - `list_tools() -> list[dict]` — the registered declarations.
       - `reset()` — clears replies, errors, declarations, and calls.
   - `plugin.py`:
     - Module-global `_bridge = FakeToolBridge()`.
     - `pytest_configure(config)` → `install_tools_modules_for_bridge(_bridge)`
       (installs `kiln` / `kiln.tools` / `kiln.async_tools` before collection).
     - `kiln_tools` fixture (function scope): `_bridge.reset()`, `yield _bridge`,
       `_bridge.reset()` (auto-reset between tests).
   - `__init__.py`: export `FakeToolBridge`, `RecordedToolCall`.

4. **Register the `pytest11` entry point** in `libs/core/pyproject.toml`:
   ```toml
   [project.entry-points.pytest11]
   kiln_tools = "kiln_ai.tool_testing.plugin"
   ```
   Re-sync the editable install so pytest discovers it; verify with
   `importlib.metadata.entry_points(group="pytest11")` and by running the shim
   tests (fixture resolves, `kiln` in `sys.modules`).

## Tests

New `libs/core/kiln_ai/tool_testing/test_tool_testing.py`:

- `test_plugin_installed_kiln_modules_at_load` — `kiln`, `kiln.tools`,
  `kiln.async_tools` are already in `sys.modules` (installed at plugin load).
- `test_exception_classes_are_the_runtime_classes` — `kiln.tools.ToolCallError`
  (and the other two) `is` the class `sandbox/tools_surface.py` defines and the
  runtime raises; sync and async modules share identical exception classes.
- `test_set_static_reply` — `set(name, "literal")`; `tools.name()` returns it
  verbatim; recorded in `.calls`.
- `test_set_callable_reply` — callable `(**kwargs) -> str` receives kwargs and
  its return is used; `.calls[0].arguments` captured.
- `test_set_error` — `set_error(name, ToolCallError(...))`; calling raises that
  exact exception.
- `test_unregistered_name_raises_tool_not_allowed` — an unset name → raises
  `ToolNotAllowed`.
- `test_positional_args_on_registered_tool_raise_tool_call_error` — a REGISTERED
  `tools.x(1)` → `ToolCallError` (keyword-only fidelity).
- `test_positional_on_unregistered_name_still_not_allowed` — regression mirroring
  the runtime's `test_positional_on_nonsense_name_still_not_allowed`: an
  UNREGISTERED tool called positionally → `ToolNotAllowed` (not `ToolCallError`),
  proving the not-allowed check precedes the positional-args check.
- `test_calls_are_ordered` — multiple calls recorded in order with arguments.
- `test_list_tools_returns_declarations` — `list_tools()` returns registered
  declarations (name + author-supplied fields); async `list_tools` too.
- `test_async_tools_under_gather` — `await asyncio.gather(async_tools.a(...),
  async_tools.b(...))` resolves via the same registry; both calls recorded.
- `test_auto_reset_between_tests` (a pair of tests) — registry/calls set in one
  test are empty at the start of the next.
- `test_end_to_end_sample_tool_py` — write a sample `tool.py` that does
  `from kiln import tools` at top level and defines `run(...)` calling
  `tools.get_user(...)`; import it (module-level `from kiln import tools`
  resolves), set a stub reply via `kiln_tools`, call `tool.run(...)`, assert on
  the output and on `kiln_tools.calls`.

## Verification

- Full existing sandbox suite (`sandbox/test_code_tool_execution.py`,
  `sandbox/test_sandbox_shared.py`) passes UNCHANGED — the extraction guard.
- New `tool_testing` tests pass with the plugin auto-loaded via the entry point.
- `uv run ./checks.sh --agent-mode`: ruff lint/format + ty on changed files
  clean; only the documented pre-existing, out-of-scope failures remain. Revert
  any `uv.lock` churn.
