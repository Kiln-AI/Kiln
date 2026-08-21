---
status: complete
---

# Phase 3: Test Run Dataset-Item Harness

## Overview

Replace the four manual free-text test inputs with a recent-TaskRun picker, extend test support to llm_judge, add shape-validity gating for Save, and handle the empty-dataset state. This delivers the "Test Run" right-pane specified in `70 section 2` and `architecture.md section 3`.

## Steps

### Backend: extend `test_v2_eval` for llm_judge builder input

1. **Add optional llm_judge builder fields to `TestV2EvalRequest`** (`eval_api.py`):
   - Add `llm_judge_builder_input: CreateLlmJudgeConfigRequest | None = None` field.
   - When `llm_judge_builder_input` is set, the handler calls `materialize_llm_judge_properties()` to bake properties (ignoring `request.properties`). This reuses the same baking path as `create_llm_judge_config`.
   - Regenerate OpenAPI schema after.

2. **Add `testV2EvalLlmJudge` client function** (`v2_eval_api.ts`):
   - A wrapper that calls `testV2Eval` with the `llm_judge_builder_input` field set and a placeholder `properties` value.

### Frontend: TaskRun picker replacing free-text inputs

3. **Add `fetchTaskRuns` utility** to `v2_eval_api.ts`:
   - Calls `GET /api/projects/{project_id}/tasks/{task_id}/runs` and returns sorted (most recent first) `TaskRun[]`.

4. **Rewrite the test pane in `eval_config_builder.svelte`**:
   - Remove the four free-text inputs (`test_final_message`, `test_task_input`, `test_trace`, `test_reference_data`).
   - Add state: `selected_task_run: TaskRun | null`, `available_runs: TaskRun[]`, `runs_loading`, `runs_error`, `advanced_reference_data`.
   - On mount, call `fetchTaskRuns(project_id, task_id)` to populate `available_runs`.
   - Render: if `available_runs.length === 0` show empty-dataset message. Otherwise show `TaskRunPicker` for selection, and once selected show a preview card with input/output + "Change" button.
   - **Advanced** collapse section for `reference_data` JSON input.
   - **Run button**: maps `selected_task_run` -> `EvalTaskInput` (mirroring `EvalTaskInput.from_task_run()`).
   - For llm_judge: calls `testV2EvalLlmJudge()` with the builder input from the llm judge form bindings.
   - For other types: calls `testV2Eval()` with properties from the form component.

5. **Enable test pane for all types including llm_judge**:
   - Remove `can_submit_v2` gating (`eval_config_type && !is_llm_judge`).
   - Show test pane for all types. Adjust `can_submit_v2` / `can_submit_llm` to both go through the same test gating logic.

6. **Shape-validity gates Save** (fix `test_has_run`):
   - Replace boolean `test_has_run` with `test_has_valid_run: boolean`.
   - After a successful test, validate the returned scores against `evaluator.output_scores`: check that every declared score name exists in the result.
   - Only `test_has_valid_run = true` bypasses the "Save Without Testing?" dialog.
   - Invalid shape shows a warning alert explaining the mismatch.

7. **Empty-dataset state**:
   - When `available_runs.length === 0` (after loading), show a message: "Run your task to generate sample inputs."
   - In this state, Save always routes through the "Save Without Testing?" confirm dialog.

8. **Score results render V1-parity floats**:
   - Keep current simple float display. No score badge component (explicitly out of scope).

### Schema regeneration

9. After backend changes, regenerate OpenAPI schema with `generate_schema`.

## Tests

### Backend (pytest)
- `test_test_v2_eval_with_llm_judge_builder_input`: Verify that when `llm_judge_builder_input` is set, `materialize_llm_judge_properties` is called and the adapter evaluates correctly.

### Frontend (vitest)
- `test_run_picker_renders_runs`: Verify TaskRunPicker renders when runs exist.
- `test_empty_dataset_state`: Verify empty state message when no runs.
- `test_taskrun_to_eval_input_mapping`: Verify the client-side TaskRun -> EvalTaskInput mapping.
- `test_shape_validity_gates_save`: Verify that test_has_valid_run requires shape-valid scores.
- `test_llm_judge_test_uses_builder_input`: Verify llm_judge test uses the builder input path.
- `test_save_without_testing_shown_for_all_types`: Verify save-without-testing dialog for all types including llm_judge.
- `test_advanced_reference_data`: Verify the advanced section for reference_data.
- `test_fetchTaskRuns_api`: Verify the fetchTaskRuns API client function.
