---
status: complete
---

# Phase 1: Task data model + validation

## Overview

Introduce the backbone of multiturn tasks at the data layer:

- A new `TurnMode` string enum with values `single_turn` and `multiturn`.
- A `turn_mode` field on `Task`, defaulting to `single_turn`. Existing on-disk tasks without the field hydrate to `single_turn` via the Pydantic default (no explicit migration validator needed).
- A model-level guardrail that loudly rejects `multiturn` combined with `input_json_schema` or `output_json_schema`.
- API-level immutability: PATCH on a task with a `turn_mode` value differing from the current one is rejected at the server with a 400.

This phase is backend-only. No frontend changes, no run-plumbing, no leaf filtering — those are Phase 2/3/4.

## Steps

1. **`libs/core/kiln_ai/datamodel/datamodel_enums.py`** — append `TurnMode`:

   ```python
   class TurnMode(str, Enum):
       single_turn = "single_turn"
       multiturn = "multiturn"
   ```

2. **`libs/core/kiln_ai/datamodel/task.py`**:
   - Import `TurnMode` from `datamodel_enums`.
   - Add a `turn_mode: TurnMode = Field(default=TurnMode.single_turn, description=...)` field on the `Task` class.
   - Add a `@model_validator(mode="after")` named `validate_turn_mode_compatibility` that raises `ValueError` if `turn_mode == TurnMode.multiturn` and either `input_json_schema is not None` or `output_json_schema is not None`. Each branch carries an actionable message (no silent fallback).

3. **`libs/server/kiln_server/task_api.py update_task`** — add an immutability check that mirrors the existing `input_json_schema`/`output_json_schema` pattern (compare value, not presence) right alongside it:

   ```python
   if (
       "turn_mode" in task_updates
       and task_updates["turn_mode"] != original_task.turn_mode.value
   ):
       raise HTTPException(
           status_code=400,
           detail="Task turn_mode cannot be changed after creation.",
       )
   ```

   Comparing values rather than blocking presence lets the frontend round-trip the full task object without hitting a false 400.

## Tests

In `libs/core/kiln_ai/datamodel/test_task.py`:

- `test_task_turn_mode_defaults_to_single_turn`: a freshly constructed `Task` has `turn_mode == TurnMode.single_turn`.
- `test_task_loads_legacy_json_without_turn_mode_as_single_turn`: validating a Task dict missing `turn_mode` (with `loading_from_file=True` context, mirroring on-disk behaviour) yields `TurnMode.single_turn`.
- `test_task_multiturn_rejects_input_json_schema`: building a `Task` with `turn_mode=multiturn` and `input_json_schema=json_joke_schema` raises `ValidationError`/`ValueError` with a message mentioning "structured input".
- `test_task_multiturn_rejects_output_json_schema`: same shape for `output_json_schema`.
- `test_task_single_turn_allows_both_schemas`: a `single_turn` task with both `input_json_schema` and `output_json_schema` set validates successfully.

In `libs/server/kiln_server/test_task_api.py`:

- `test_update_task_turn_mode_unchanged_succeeds`: PATCH includes `turn_mode` matching the existing value → 200, response body echoes the same `turn_mode`.
- `test_update_task_turn_mode_change_rejected`: PATCH includes `turn_mode` differing from the existing value → 400 with "Task turn_mode cannot be changed after creation." message.
- `test_create_task_multiturn_with_structured_input_schema_rejected`: POST creating a multiturn task with `input_json_schema` set → 422 (FastAPI's idiomatic response when `Task.validate_and_save_with_subrelations` surfaces a `ValidationError` — verify the actual code in the existing test file's create-error pattern; if the create path returns 400 instead, follow that).
