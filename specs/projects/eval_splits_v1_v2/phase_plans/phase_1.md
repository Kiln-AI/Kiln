---
status: complete
---

# Phase 1: Merge `scosman/evals_v2` and back out #1621's split surface

## Overview

Land the `scosman/evals_v2` merge on this branch and leave the tree green with **no `split`
parameter anywhere**. No new behavior: this phase only reconciles two lines of work.

Per architecture §10, conflicts resolve toward **evals_v2's** shape (`eval_set_filter_id:
DatasetFilterId | None`, the `EvalInput` model, `validate_filter_fields`), and #1621's split
implementation is **deleted rather than reconciled** — `val_set_filter_id`, `EvalSplitName`,
`filter_id_for_split`, `migrate_val_set_filter_id`, `split_filter_id_from_eval`,
`eval_set_filter_id_override`, and the `split` params on the run and results APIs are all
replaced by phases 2–6.

The merge base is `df0fd56`, so this is wide, but only six files conflict textually. The larger
surface is the non-conflicting #1621 code that has to come out, plus its tests.

## Steps

### 1. Merge

`git merge --no-ff origin/scosman/evals_v2`. Six conflicted files.

### 2. Resolve conflicts

1. **`app/desktop/desktop_server.py`** — union of both sides. Keep HEAD's
   `from app.desktop.studio_server.chat import connect_chat_api, connect_chat_auto_api` and add
   evals_v2's `from app.desktop.studio_server.code_tool_api import connect_code_tool_api`; drop
   evals_v2's now-duplicate `chat` import line.

2. **`app/desktop/studio_server/eval_api.py`** (import block) — take evals_v2's `EvalScores`,
   `EvalTaskInput`; drop HEAD's `EvalSplitName` (deleted in step 3).

3. **`libs/core/kiln_ai/adapters/eval/eval_runner.py`** — take evals_v2's side:

   ```python
   if self.eval.eval_set_filter_id is None:
       raise ValueError("eval_set_filter_id is required for task_run_eval mode")
   filter = dataset_filter_from_id(self.eval.eval_set_filter_id)
   ```

4. **`libs/core/kiln_ai/datamodel/eval.py`** — take evals_v2 on all three hunks: `Annotated` in
   the `typing` import; `eval_set_filter_id: DatasetFilterId | None` with evals_v2's description;
   evals_v2's `train_set_filter_id` description plus its `eval_input_filter_id` field. Drop
   `val_set_filter_id` entirely.

5. **`libs/core/kiln_ai/adapters/eval/test_eval_runner.py`** — keep both sides (evals_v2 adds
   `test_run_job_wrapped_rate_limit_raises_retryable_with_detail`).

6. **`app/web_ui/src/lib/api_schema.d.ts`** — generated; regenerate with
   `app/web_ui/src/lib/generate_schema.sh` after the Python side settles.

### 3. Delete #1621's split surface

**`libs/core/kiln_ai/datamodel/eval.py`**
- Delete the `EvalSplitName` literal and its comment.
- Delete `Eval.filter_id_for_split`.
- Delete the `migrate_val_set_filter_id` validator. `_split_tag_suffix` stays — still used by
  `migrate_train_set_filter_id` (phase 2 removes that).
- Drop the `raise_exhaustive_enum_error` import if it becomes unused.

**`libs/core/kiln_ai/adapters/eval/eval_runner.py`**
- Delete the `eval_set_filter_id_override` constructor parameter, the `self.eval_set_filter_id_override`
  attribute, the `eval_config_eval` guard against it, and the docstring paragraph describing it.
- Restore the `collect_tasks_for_task_run_eval` docstring bullet to "should be in the eval set
  filter".

**`app/desktop/studio_server/eval_api.py`**
- Delete `split_filter_id_from_eval`.
- Delete the `split` query parameter and the split-filtering block in `get_eval_run_results`.

**`app/desktop/studio_server/jobs/workers/eval.py`**
- Delete `EvalJobParams.split`, `_split_override`, and `_dataset_filter_id`.
- `compute_state` resolves the filter from `eval.eval_set_filter_id` directly. That field is now
  `| None`, so guard it:

  ```python
  if eval.eval_set_filter_id is None:
      raise ValueError(f"Eval '{eval.id}' has no eval_set_filter_id")
  filter = dataset_filter_from_id(eval.eval_set_filter_id)
  ```

  Phase 5 replaces this with `resolve_split`.
- `_build_eval_runner` drops the override argument and the `_eval_and_task` call that fed it.
- Drop the now-unused `EvalSplitName`, `DatasetFilterId`, `split_filter_id_from_eval` and `Eval`
  imports as applicable.

**`app/desktop/studio_server/jobs/api.py`**
- Delete the pre-job split resolution block and the
  `from ..eval_api import eval_from_id, split_filter_id_from_eval` import.

**`libs/server/kiln_server/spec_api.py`, `app/desktop/studio_server/copilot_api.py`**
- Stop passing `val_set_filter_id=` to `Eval(...)`. `spec_utils`' 4-tuples stay as they are
  (architecture §8 keeps the widening); phase 3 wires the val entry into `splits`.

### 4. Non-conflicting merge fallout

Git merged these files cleanly, but the two branches disagree about APIs they don't share, so
they only break at import or type-check time:

- **`registry.eval_adapter_from_type` was renamed** on evals_v2 to
  `legacy_eval_adapter_from_type(eval_config)` (taking the config, not its type). The
  #1621-side `judge_feedback_batch_runner.py` still imports the old name. Rename the import and
  the call; update the two patch targets in `test_judge_feedback_batch_runner.py` and the one in
  `test_eval_runner.py`.

  The rename also makes a **new state reachable**: the new function raises `NotImplementedError`
  for `EvalConfigType.v2`, which the old one could not represent, and `JudgeFeedbackBatchRunner`
  has no V2 dispatch arm. Building one is judge-axis work and out of scope here, so refuse at the
  API boundary instead — a 422 from `judge_feedback_batch_api.validate_judge_eval`, which all
  three batch endpoints already call, so a batch naming a V2 judge cannot be created or run.
- **`EvalConfig.model_name` / `model_provider` became `str | None`** on evals_v2 (V2 configs
  carry the model inside `properties`). The #1621-side job-properties models declare them `str`.
  Blank them with `or ""`, matching how those same files already handle an MCP run config that
  carries no model.
- The merge also **duplicated** `test_run_job_wrapped_rate_limit_raises_retryable_with_detail`
  in `test_eval_runner.py` — both branches added it. Keep one, patching
  `legacy_eval_adapter_from_type`.

### 5. Tests

Remove the #1621 tests for the deleted surface and fix assertions that reference
`val_set_filter_id`:

- `libs/core/kiln_ai/datamodel/test_eval_model.py` — delete the val-field, val-migration and
  `filter_id_for_split` tests.
- `libs/core/kiln_ai/adapters/eval/test_eval_runner.py` — delete the
  `eval_set_filter_id_override` tests.
- `app/desktop/studio_server/jobs/workers/test_eval.py` — delete the split/override tests.
- `app/desktop/studio_server/jobs/test_api.py` — delete the split pre-check tests.
- `app/desktop/studio_server/test_eval_api.py` — delete the `?split=` results tests.
- `libs/server/kiln_server/test_spec_api.py`, `app/desktop/studio_server/test_copilot_api.py` —
  drop the `val_set_filter_id` assertions.

### 6. Regenerate schema and run checks

`app/web_ui/src/lib/generate_schema.sh`, then `uv run ./checks.sh --agent-mode`.

The integration branch arrives lint-red: `judge_feedback_batch.py` and
`judge_feedback_batch_runner.py` carry ambiguous unicode in their design-review comment blocks
(RUF003 on `×` and `–`). Replace those two characters with ASCII — the phase's end state is a
green tree.

## Tests

Two tests are added, both for raise paths the merge created:

- `test_create_rejects_v2_judge` — creating a judge feedback batch against a V2 eval config is a
  422 naming the reason, and no batch is written.
- `test_compute_state_without_eval_set_filter_raises` — the eval job worker raises for an
  EvalInput-backed eval rather than reporting a zero total, which would let a resume
  short-circuit to "complete". Phase 5 replaces this raise with `resolve_split`.

Otherwise the phase adds no behavior, so its verification is that the existing suite passes with
the split surface removed, plus:

- The full Python suite passes on the merged tree (`test_eval_model.py`, `test_eval_runner.py`,
  `test_eval_api.py`, `jobs/test_api.py`, `jobs/workers/test_eval.py`,
  `test_spec_api.py`, `test_copilot_api.py`).
- `evals_v2`'s own eval tests — `validate_filter_fields`, the `EvalInput` model and the V2 judge
  types — pass unchanged, confirming the conflict resolutions took evals_v2's semantics.
- The web suite, lint, format, type check and build pass.
- The generated OpenAPI client contains no `split` parameter — the check that #1621's API surface
  is fully gone rather than partly gone.
