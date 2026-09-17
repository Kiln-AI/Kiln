---
status: complete
---

# Phase 1: `enable_auto_mode` built-in tool in libs/core

## Overview

Introduce the `enable_auto_mode` built-in tool in `libs/core` so the external backend can expose it
to the model as a client-visible tool. The tool is a **signal**: when the model calls it, the app
server intercepts it by name and never executes it. The `run()` implementation exists only to keep
the `libs/core` tool surface complete and standalone (per the "libs/core is a standalone library"
invariant). This mirrors the existing `call_kiln_api` tool's shape (`KilnApiCallTool`,
`KilnBuiltInToolId.CALL_KILN_API`, `tool_registry.py` case). Architecture §7.

## Steps

1. `libs/core/kiln_ai/datamodel/tool_id.py`: add `ENABLE_AUTO_MODE = "kiln_tool::enable_auto_mode"`
   to `KilnBuiltInToolId`.
2. New file `libs/core/kiln_ai/tools/built_in_tools/enable_auto_mode_tool.py`: `EnableAutoModeTool`
   subclassing `KilnTool`.
   - `name="enable_auto_mode"`, module constant `ENABLE_AUTO_MODE_TOOL_NAME = "enable_auto_mode"`.
   - `tool_id=KilnBuiltInToolId.ENABLE_AUTO_MODE`.
   - description: model-facing copy explaining auto-mode (suggest a signed-off multi-step plan, call
     it alone, user may decline).
   - `parameters_schema`: object with a single optional `reason: string`, no `required`.
   - `run()` is a signal no-op returning `ToolCallResult(output=json.dumps({"status": "enabled"}))`.
     Accept `context=None, **kwargs` like the other built-ins so both call conventions work.
3. `libs/core/kiln_ai/tools/tool_registry.py`: add
   `case KilnBuiltInToolId.ENABLE_AUTO_MODE: return EnableAutoModeTool()` (import the class).
4. Do NOT modify the app server's `FUNCTION_NAME_TO_TOOL_ID` (out of scope; interception by name).

## Tests

- `test_enable_auto_mode_tool.py`:
  - `test_tool_metadata`: `name()`, `id()`, description non-empty/contains key copy.
  - `test_toolcall_definition`: schema has optional `reason: string`, no `required` key (or empty).
  - `test_run_returns_enabled_signal`: `run()` returns `{"status": "enabled"}` JSON, not an error.
  - `test_run_with_reason_arg`: `run(reason="...")` still returns the enabled signal (no-op ignores).
  - `test_run_with_positional_context` / `test_run_without_context`: both call conventions work.
- `test_tool_registry.py`:
  - `test_tool_from_id_enable_auto_mode`: returns `EnableAutoModeTool`, correct id/name.
- (Existing exhaustive-enum `match` ensures the registry covers the new enum member at type-check.)
