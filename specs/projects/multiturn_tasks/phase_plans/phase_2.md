---
status: complete
---

# Phase 2: Run plumbing + leaf filters

## Overview

Wire continuation runs through the `/run` endpoint and exclude interior nodes from list views and dataset splits. Phase 1 already added `Task.turn_mode` plus the create-time validators; this phase consumes that field at runtime.

End state for Phase 2:

- `RunTaskRequest.parent_task_run_id: str | None` accepted by the run endpoint.
- `run_task` loads the parent run, threads `prior_trace` + `parent_task_run` into the adapter, and rejects bad combinations (single-turn task → 400; missing parent → 404). The adapter already produces a TaskRun with `parent_task_run_id` set and a trace that extends the parent's, so no adapter-layer changes are needed.
- `get_runs_summary` returns leaves only — runs whose ids are not the `parent_task_run_id` of any other run.
- `DatasetSplit.build_split_contents` skips interior nodes before applying the user filter, so multiturn dataset splits only contain leaves.
- For single-turn tasks both filters are no-ops because `parent_task_run_id` is never set.

Backend-only. Frontend (Phases 3 + 4) ships separately.

## Steps

1. **`libs/server/kiln_server/run_api.py` — `RunTaskRequest`:** add the new field.

   ```python
   parent_task_run_id: str | None = Field(
       default=None,
       description=(
           "When set, treat this as a continuation of the given parent run "
           "(multiturn tasks only). The parent run's trace is passed as "
           "prior_trace, and parent_task_run_id is set on the resulting TaskRun."
       ),
   )
   ```

   Field name deliberately mirrors `TaskRun.parent_task_run_id` — same concept, same name.

2. **`libs/server/kiln_server/run_api.py` — `run_task` handler:** load and validate the parent before invoking the adapter. Add a `from kiln_ai.datamodel.datamodel_enums import TurnMode` import (joining the existing enum import) and replace the final `return await adapter.invoke(input)` block with:

   ```python
   prior_trace = None
   parent_task_run = None
   if request.parent_task_run_id is not None:
       if task.turn_mode != TurnMode.multiturn:
           raise HTTPException(
               status_code=400,
               detail="parent_task_run_id is only valid for multiturn tasks.",
           )
       parent_task_run = TaskRun.from_id_and_parent_path(
           request.parent_task_run_id, task.path
       )
       if parent_task_run is None:
           raise HTTPException(
               status_code=404,
               detail=f"Parent run not found: {request.parent_task_run_id}",
           )
       prior_trace = parent_task_run.trace

   return await adapter.invoke(
       input,
       prior_trace=prior_trace,
       parent_task_run=parent_task_run,
   )
   ```

   The adapter's `invoke` already accepts both kwargs, the formatter selection in `build_chat_formatter` already uses `prior_trace`, and `generate_run` already sets `parent_task_run_id` on the produced TaskRun.

3. **`libs/server/kiln_server/run_api.py` — `get_runs_summary`:** filter interior nodes.

   ```python
   runs = task.runs(readonly=True)
   parent_ids: set[str] = {
       r.parent_task_run_id for r in runs if r.parent_task_run_id
   }
   return [
       RunSummary.from_run(run)
       for run in runs
       if run.id not in parent_ids
   ]
   ```

   For single-turn tasks `parent_ids` is empty, so this is a no-op.

4. **`libs/core/kiln_ai/datamodel/dataset_split.py` — `build_split_contents`:** materialize `runs` once, compute `parent_ids`, skip interior nodes, then run the user filter.

   ```python
   runs = list(task.runs())
   parent_ids = {r.parent_task_run_id for r in runs if r.parent_task_run_id}
   valid_ids = []
   for task_run in runs:
       if task_run.id in parent_ids:
           continue
       if filter(task_run):
           valid_ids.append(task_run.id)
   # existing shuffle / split logic unchanged
   ```

   Same shape as the run_api filter; single-turn tasks unaffected.

## Tests

In `libs/server/kiln_server/test_run_api.py`:

- `test_run_task_continuation_multiturn`: POST `/run` with `parent_task_run_id` for a multiturn task. Mocks the adapter `invoke`; asserts the adapter was called with `prior_trace=parent.trace` and `parent_task_run=<the parent run>`, and the returned TaskRun carries the parent's id in `parent_task_run_id` plus a trace that extends the parent's.
- `test_run_task_continuation_single_turn_rejected`: POST `/run` with `parent_task_run_id` against a single-turn task → 400 with "parent_task_run_id is only valid for multiturn tasks." message. Adapter `invoke` is not called.
- `test_run_task_continuation_parent_not_found`: POST `/run` against a multiturn task with a non-existent `parent_task_run_id` → 404 with "Parent run not found: …" message.
- `test_get_runs_summaries_multiturn_returns_leaf_only`: build a multiturn task with three TaskRuns chained (run_b.parent_task_run_id == run_a.id, run_c.parent_task_run_id == run_b.id). GET `/runs_summaries` returns only run_c.
- `test_get_runs_summaries_single_turn_returns_all_runs`: single-turn task with three independent runs (no parent ids). GET `/runs_summaries` returns all three.

In `libs/core/kiln_ai/datamodel/test_dataset_split.py`:

- `test_build_split_contents_multiturn_excludes_interior_nodes`: multiturn task with three TaskRuns chained → `from_task(... AllSplitDefinition ...)` produces a split that contains only the leaf id.
- `test_build_split_contents_single_turn_includes_all_runs`: single-turn task with three independent runs → existing behavior preserved (three ids in the split). Regression check that the new filter doesn't affect single-turn tasks.

## Out of scope

- Frontend: Phases 3 + 4.
- `turn_mode` validators / immutability: Phase 1.
