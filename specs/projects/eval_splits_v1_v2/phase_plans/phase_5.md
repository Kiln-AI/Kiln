---
status: complete
---

# Phase 5: Jobs

## Overview

The eval job worker gets **one resolution rule**, shared by both consumers that need a split:
`EvalRunner` (which items to work) and `compute_state` (which items progress is measured against).
Both go through `_resolve_split`, so both always describe the *same* split of the same eval —
they still resolve separately, because `compute_state` is also called on its own by the registry
(see judgment call #4), but they can no longer disagree about which split that is. Architecture
§5.1. That shared rule is what closes
functional spec §4.3 — today `compute_state` builds its universe from
`dataset_filter_from_id(eval.eval_set_filter_id)` over `task.runs()`, which is *empty* for an
EvalInput-backed eval, so such a job would report a zero total and let a resume short-circuit to
"complete" with no work done. Today it doesn't even get that far: the same read raises
`ValueError("has no eval_set_filter_id")`, which is why phase 4's EvalInput runner path is not
reachable end to end.

`EvalJobParams.split` comes back (kept from #1621, backed out in phase 1), and `jobs/api.py`
re-gains its pre-job resolution — now through `resolve_split`, so it holds for both backings —
so a split the eval doesn't have is a 422 at request time rather than a doomed background job
(functional spec §9).

After this phase, running a train or val split, and running an EvalInput-backed split, both work
end to end through the jobs API. The read side (results, progress, summaries) is still test-only
and still TaskRun-shaped; that is phase 6.

### On the two phase-4 carry-overs

Phase 4 recorded three known limitations. Two of them are conditioned on "whichever of phases 5
and 6 next edits `run_job` / `collect_tasks_for_eval_config_eval`", both of which live in
`libs/core/kiln_ai/adapters/eval/eval_runner.py`.

**Phase 5 does not edit either.** Architecture §5 is entirely about
`app/desktop/studio_server/jobs/`; this phase changes what the runner is *handed*, never how it
runs a job or collects calibration work. Taking the `EvalJob` split-into-two-dataclasses refactor
here would be exactly the standalone refactor phase 4 declined — every construction and every
`isinstance` in a file this phase otherwise does not open. Same for the calibration dedupe fix,
which has its own test surface in `test_eval_runner.py`.

So both stay recorded rather than half-done. Phase 6 touches `eval_api.py`'s summary and progress
readers and `compute_score_summary`, but not `eval_runner.py` either — if neither phase opens that
file, these two belong in the eb-v2 alignment overview (phase 7) or a follow-up, and this plan says
so rather than leaving them attached to a phase that will not reach them.

The third carry-over — `compute_state`'s `eval_set_filter_id` read — *is* this phase's, and is the
whole point of it.

---

## Steps

### 1. `app/desktop/studio_server/jobs/workers/eval.py` — `EvalJobParams.split`

Restore the field, with `EvalSplitName` imported from `kiln_ai.datamodel.eval`:

```python
    split: EvalSplitName | None = Field(
        default=None,
        description="Which of the eval's dataset splits to run: train, val, or test. "
        "Fails with 422 if the eval has no such split. Leave null to run the test "
        "split, which is what running an eval has always meant.",
    )
```

The description no longer says "the eval set (the test set)" — the eval set *is* the test split
now, and there is no other item selection to fall back to.

An out-of-range value (`"holdout"`) is a request-validation 422 for free, which is the second row
of functional spec §9's table.

### 2. `app/desktop/studio_server/jobs/workers/eval.py` — one resolution, two consumers

Add the method architecture §5.1 specifies. Phase 4 deliberately left this inline in
`_build_eval_runner` because its second caller didn't exist yet; it exists now.

```python
    def _resolve_split(
        self, eval: Eval, task: Task, params: EvalJobParams
    ) -> ResolvedSplit:
        name: EvalSplitName = params.split or "test"
        split = resolve_split(task, eval, name)
        if split is None:
            raise ValueError(f"Eval '{eval.id}' has no '{name}' split.")
        return split
```

Message wording matches `eval_api.resolved_split_or_422` exactly: the split as the caller spelled
it, and the eval id, per architecture §7. In practice this raise is unreachable —
`jobs/api.py` pre-resolves a named split, and `Eval.validate_splits` guarantees a test split for
any eval that loads — but the method is what makes the return type non-optional for both callers.

### 3. `app/desktop/studio_server/jobs/workers/eval.py` — `_compute_state_sync`

Replace the `eval_set_filter_id` guard, the `dataset_filter_from_id` call and the bare-id sets:

```python
        split = self._resolve_split(eval, task, params)
        split_items = split.item_keys()

        scored_items = {
            eval_run_item_key(run)
            for run in eval_config.runs(readonly=True)
            if run.task_run_config_id == params.run_config_id
        }
        success = len(scored_items & split_items)

        return JobDerivedState(
            total=len(split),
            success=success,
            is_complete=success >= len(split),
        )
```

Two behavior changes, both intended:

- `total` is the split's size in the split's own store, so an EvalInput-backed job reports its real
  universe instead of raising (or, without the guard, reporting zero).
- Membership keys on `ItemKey`, not on a bare `dataset_id`. Architecture §3.1 / functional spec
  §5.3: both stores draw ids from one 12-digit generator, so a bare id could credit an `EvalInput`'s
  result to a `TaskRun` with the same id, and vice versa.

`error` stays `None` for the same reason as before, and the comment saying why stays.

Drop the now-unused `dataset_filter_from_id` import.

### 4. `app/desktop/studio_server/jobs/workers/eval.py` — `_build_eval_runner` and `run`

`_build_eval_runner` calls `self._resolve_split(eval, task, params)` in place of phase 4's inline
`resolve_split(task, eval, "test")` + `raise`. Nothing else about it changes.

`run()`'s comment says "the FULL eval-set size" in two places; it is the full **split** size now.
The arithmetic is unchanged — baseline comes from `compute_state`, which now measures the same
split the runner was handed, which is the property that makes the arithmetic correct at all.

### 5. `app/desktop/studio_server/jobs/api.py` — pre-resolution

Restore the block phase 1 deleted, resolving through `resolve_split` (architecture §5.2). A
module-level helper, so `asyncio.to_thread` gets a named function rather than a lambda closure:

```python
def _require_resolvable_split(
    project_id: str, task_id: str, eval_id: str, split: EvalSplitName
) -> None:
    eval = eval_from_id(project_id, task_id, eval_id)
    task = task_from_id(project_id, task_id)
    resolved_split_or_422(task, eval, split)
```

and in `run_eval_job`, before `job_registry.create`:

```python
        if params.split is not None:
            await asyncio.to_thread(
                _require_resolvable_split,
                params.project_id,
                params.task_id,
                params.eval_id,
                params.split,
            )
```

Reusing `eval_api.resolved_split_or_422` (added in phase 4) rather than restating the 422 keeps one
wording for "this eval has no such split" across the jobs API, the SSE run endpoint, and phase 6's
readers.

**Why the `is not None` guard, when architecture §7 calls the worker's raise "unreachable — the
pre-check fires first".** It still is. `Eval.validate_splits` rejects an eval without a test split,
so the only split that can be absent is one the caller *named* — and those are exactly the requests
this guard lets through to the check. Resolving unconditionally would buy no additional refusal and
would enumerate the whole dataset off disk on every job creation, immediately before the worker
enumerates it again. Functional spec §8.1's "omitting `split` produces exactly today's behavior" is
the other half of the same argument.

The pre-check deliberately **discards** what it resolved: the worker resolves again at run time,
because a job runs the items as they are when it runs, not as they were when it was requested.

### 6. Regenerate `app/web_ui/src/lib/api_schema.d.ts`

`EvalJobParams` is a request model, so the OpenAPI schema moves. `checks.sh`'s `openapi schema`
check cannot run in this container (`check_schema.sh` imports `desktop_server`, which imports
`tkinter`), so generate it with a `tkinter` stub instead — see "Check status" below for why that
substitution is trustworthy rather than a workaround.

---

## Tests

### `app/desktop/studio_server/jobs/workers/test_eval.py`

Replaced:

- `test_compute_state_without_eval_set_filter_raises` → **`test_compute_state_counts_an_eval_input_backed_split`**. Same eval, opposite expectation: it now reports the EvalInputs in its test
  split as the total instead of raising. This is the functional spec §4.3 fix stated as a test, and
  it also asserts the two negatives that make the count meaningful — an out-of-filter `EvalInput`
  and an in-filter-tagged `TaskRun` are both excluded.

New:

- `test_compute_state_counts_scored_eval_inputs` — `EvalRun`s carrying `eval_input_id` count toward
  success for an EvalInput-backed split, so a resumed job over one doesn't redo finished work.
- `test_compute_state_does_not_credit_a_task_run_scored_under_an_eval_inputs_id` — a `TaskRun` and
  an `EvalInput` constructed with the *same* id; the split is EvalInput-backed and the only
  `EvalRun` is TaskRun-sourced. Success must be 0. Kills bare-id membership (architecture §3.1).
- `test_compute_state_measures_the_requested_split` — `split="train"` reports the train universe,
  not the test one. Overlapping-but-different tag sets, so a wrong-split resolution is visible in
  the count rather than coincidentally equal.
- `test_compute_state_defaults_to_the_test_split` — `split=None` and `split="test"` produce the
  same `JobDerivedState`.
- `test_compute_state_missing_split_raises` — `split="val"` on an eval with no val split raises
  naming `'val'` and the eval id (not a field name — functional spec §9).
- `test_build_eval_runner_passes_the_requested_split` — `split="val"` reaches the runner as a
  `ResolvedSplit` named `val` holding the val items. Functional spec §4.2's "must be impossible by
  construction" for the jobs path.
- `test_build_eval_runner_missing_split_raises` — the same refusal on the runner-building path, so
  neither consumer of `_resolve_split` can silently proceed over an absent split.
- `test_run_reports_totals_against_the_requested_split` — a job with `split="train"` and some train
  items already scored reports progress against the *train* size. The test split is deliberately
  larger and fully scored, so a baseline taken from it would report the train job complete. The
  regression this guards is the §4.3 one: baseline from one split and work from another.
- `test_run_over_an_eval_input_backed_split_works_its_items` — end to end through `run()` with a
  real `EvalRunner` and a stubbed `run_job`: an EvalInput-backed eval must process its EvalInputs
  and report their count. Before this phase it raised; without the shared resolution it would
  report `0/0` and a resume would short-circuit.
- `test_run_logs_the_item_source_for_an_eval_input_backed_split` — the error log's `item_source`
  (see the review section below) is `eval_input` when the failed item came from that store, and the
  two existing error-log tests assert `task_run` for theirs.

Two fixtures/helpers absorb the setup that the two EvalInput-backed tests already duplicated
inline: an `input_backed_eval` fixture (eval + config) and `_make_eval_input` /
`_make_eval_input_run`, mirroring the existing `_make_task_run` / `_make_eval_run` pair.

Existing tests keep passing unchanged — the TaskRun-backed `eval_set_filter_id` eval folds to a
`TaskRunSplit` test split, so `compute_state` resolves the same items by a different route.

### `app/desktop/studio_server/jobs/test_api.py`

- `_EVAL_PARAMS` gains `"split": None`, and `test_run_eval_job_creates_typed_eval_job` keeps its
  `job.params == _EVAL_PARAMS` assertion — which now also asserts the new param survives the
  round trip through `model_dump(mode="json")` and back.
- **`test_run_eval_job_without_a_split_resolves_nothing`** — the existing create test already
  proves this (its params name a project that doesn't exist), but implicitly. Name it: with no
  split, creation must not resolve anything, so a 201 is the assertion.
- `test_run_eval_job_with_a_split_the_eval_has_creates_the_job` — real on-disk project/task/eval
  with a train split; `split="train"` → 201, and the stored params carry it.
- `test_run_eval_job_with_a_split_the_eval_lacks_422` — `split="val"` on that eval → 422 whose
  detail names `val` and the eval id, **and no job is created** (a doomed job is the thing being
  prevented, so assert the registry is empty).
- `test_run_eval_job_with_an_unknown_eval_404` — a named split on a missing eval → 404, no job.
- `test_run_eval_job_with_an_invalid_split_value_422` — `split="holdout"` → 422 from request
  validation, no job.

The last four need real entities on disk, which this file has none of; add a small
project/task/eval fixture set patching `kiln_server.task_api.project_from_id`, mirroring
`workers/test_eval.py`'s `resolve_project`. The 422's detail is asserted against `resp.text`, not a
JSON field: this test app is a bare `FastAPI` with `connect_jobs_api` only, so it has none of the
studio's error-shape handlers and the body is FastAPI's raw `detail`.

### Mutation sweep

`specs/projects/eval_splits_v1_v2/phase5_mutation_sweep.py`, same harness as phases 2–4.
**13 mutations, all killed**, covering:

- `_resolve_split` ignoring `params.split` (always `"test"`), and defaulting to something other
  than `"test"` when it is `None`.
- `_resolve_split` degrading an absent split to an empty one rather than raising.
- `compute_state` measuring the eval's test split while the runner runs the requested one — this
  phase's headline property stated as a mutation — and `_build_eval_runner` doing the mirror image.
- `compute_state`'s membership degrading to bare ids: each half alone (which empties the
  intersection, killed by any dedupe test) and both together (which keeps membership working but on
  bare ids — killed *only* by the id-collision test, which is why that test exists).
- `compute_state`'s `total` coming from `task.runs()` rather than the split.
- `jobs/api.py`'s pre-check dropped entirely; guarded on the inverted condition (`is None`);
  resolving a hardcoded `"test"` instead of `params.split`; and resolving but not raising.

Phases 2 and 3's sweeps are re-run against this tree: **30/30** and **23/23** still killed.

Phase 4's sweep had one entry — *worker: builds the runner over an empty split* — whose target line
this phase replaced with the shared `_resolve_split` that phase 4's own plan said the inline call
was written to become. It reported `PATTERN-MISS` rather than `killed`. Following the precedent
phase 4 set for phase 2, it is replaced in `phase4_mutation_sweep.py` by a comment saying so and
pointing at this phase's equivalent, so a re-run is **19/19 killed** instead of a false alarm in a
committed artifact. `phase_4.md`'s own "20 mutations" claim carries the same note, since that is
where a reader meets the number.

### Check status

`uv run ./checks.sh --agent-mode` reports two failures, both pre-existing and both recorded
identically by phases 3 and 4:

- **openapi schema** — `check_schema.sh` imports `desktop_server`, which imports `tkinter`, which
  isn't installed in this container. The check cannot run at all here; it is not reporting a stale
  schema. See below.
- **python tests** — `7290 passed, 0 failed`, plus the same five collection errors from the same
  missing `tkinter` (`test_desktop.py`, `test_server.py`, `test_import_api.py`,
  `test_start_background_syncs.py`, `git_sync/test_sse_invariants.py`).

Everything else — `ruff check`, `ruff format`, `ty check`, and all five web checks — passes.

Unlike phase 4, this phase **does** change a request model, so `api_schema.d.ts` had to move with
it. It was regenerated with `tkinter` and `tkinter.filedialog` stubbed — they are imported at module
scope only for the tray window and the native file-open dialog, neither of which contributes to the
OpenAPI document.

**Why that substitution is trustworthy rather than a workaround:** it was verified *before* any
change. On the unmodified tree, the stub-generated `api_schema.d.ts` is **byte-identical** to the
committed one — so the stub reproduces exactly what CI produces, and the regenerated file is the
real artifact. The resulting diff is five lines, the new `split` parameter and nothing else, and
regenerating again after the last source edit still matches the committed file.

---

## Judgment calls made during implementation

Recorded for disagreement; not derived from `architecture.md`.

1. **`_resolve_split` takes `(eval, task, params)`, not `(task, eval, params)`.** That is
   architecture §5.1's signature verbatim, and it is the *opposite* argument order from
   `resolve_split(task, eval, split)` one line below it. Both are `Eval`/`Task`, so a swap is a type
   error rather than a silent bug, and matching the spec exactly is worth more than internal
   symmetry. Flagged because it will read as a typo to anyone who doesn't have §5.1 open.
2. **The `jobs/api.py` pre-check is guarded on `params.split is not None`.** Argued in full at step
   5. The short version: `Eval` cannot validate without a test split, so the only split that can be
   absent is one the caller named, and resolving unconditionally would enumerate the dataset off
   disk on every job creation to refuse nothing. Architecture §7's "unreachable — the pre-check
   fires first" still holds.
3. **The pre-check discards the `ResolvedSplit` it built rather than threading it into the job.**
   Threading it would make the request-time resolution authoritative for a job that may start
   minutes later, over a dataset that has since changed. A job runs the items as they are when it
   runs. The cost is one duplicated enumeration on the split-named path, which the comment says.
4. **`run()` still resolves the split twice per job** — once via `compute_state` for the baseline,
   once via `_build_eval_runner`. Not collapsed: `compute_state` is also called independently by the
   registry (launch reconcile, `GET /api/jobs/{id}`), so it has to resolve on its own, and caching
   it on the worker instance would make a long-lived job's progress answer from a stale universe.
   The property that matters — both answers describing the *same split* — is what `_resolve_split`
   guarantees, and is what the mutation sweep tests.
5. **Comments and docstrings that said "eval set" now say "split".** `run()`'s two arithmetic
   comments and the `EvalJobWorker` docstring described a universe that no longer exists as a
   concept in this file. Left uncorrected they would be the only remaining place that implies the
   test split is special to this worker.

## Known limitations, for phase 6 or later

### The jobs UI does not show which split a job ran


`EvalJobProperties` carries the eval, run config and judge, but not the split. Two jobs over the
same eval and run config — one train, one test — render identically in the jobs list, and their
differing item counts look like a bug rather than a difference in scope. Not fixed here because
`describe()` is the jobs UI's contract and the field would want rendering alongside it, which is
phase 6's web-UI work. Nothing is *wrong* today: no UI creates a non-test eval job yet
(functional spec §4.4 keeps `split` off the SSE endpoints deliberately), so the gap only opens for
programmatic callers, who read `job.params.split` directly.

### The two phase-4 carry-overs are still open, and phase 6 may not reach them either

Phase 4 attached both to "whichever of phases 5 and 6 next edits `run_job` /
`collect_tasks_for_eval_config_eval`". Phase 5 does not open `eval_runner.py` at all, and on
architecture §6 neither does phase 6 — it is `eval_api.py` endpoints, `compute_score_summary`, the
summary cache, and two Svelte pages.

- **`EvalJob` does not express which item types each run type can carry.** Unreachable, not
  unrepresentable. Unchanged by this phase.
- **Calibration dedupe ignores what a run was *for*.** `collect_tasks_for_eval_config_eval` builds
  `already_run` from every run on the eval config, including `task_run_eval` ones, so a golden
  `TaskRun` that has been scored for some run config is never calibrated. Unchanged by this phase.

Both are recorded here rather than silently re-deferred: if phase 6 confirms it does not touch that
file, they belong in the eb-v2 alignment overview (phase 7) or a follow-up issue, not in a phase
plan that will not reach them.

## Deliberately not done

- **The API endpoints' `split` parameters, the val count on progress, and the summary readers**
  (architecture §6). Phase 6's. This phase's `resolved_split_or_422` reuse in `jobs/api.py` is
  because the helper already existed, not a down payment on that work.
- **Anything in `eval_runner.py`.** Phase 4 finished the runner; this phase only changes what it is
  handed.

---

## Changes from code review

Five items, all taken.

1. **The carry-over deferral moved to `implementation_plan.md`** (`## Notes`, "Two `eval_runner.py`
   fixes are homeless"). The reasoning was right but recorded where the next phase's agent would
   never see it: phase plans are not part of a coding agent's context loading, which is exactly how
   phase 4's version of this note went unread. Both items are now named in the plan itself, with a
   pointer back to the two phase plans for the full write-ups.

2. **`_EVAL_JOB_APPROVAL` no longer says "the eval set".** This phase swept that phrase out of the
   worker's comments and docstring but missed the one string a *human* reads — the approval prompt
   for an agent-initiated job, which would have described a train-split run as running the eval set.
   Now "across the eval's dataset split". It is an `x-` extension in the OpenAPI document, so
   `api_schema.d.ts` is unaffected (re-verified).

3. **The Overview's "resolves its split once" is reworded**, and so is `_resolve_split`'s docstring,
   which had the same overstatement. The code resolves twice through one shared *rule* — judgment
   call #4 says so plainly, and the Overview contradicted it. The property that actually holds is
   that the two answers cannot describe different splits.

4. **The error log gains `item_source`.** `_EvalErrorLogObserver` writes `dataset_id=job.item.id`,
   and this phase is what first makes `EvalInput` ids reachable there — a bare, source-blind id
   under a TaskRun-shaped name, in the one place in this project not keyed on `ItemKey`. The key is
   kept rather than renamed (the sibling judge-feedback worker writes the same one, and it has no
   in-repo reader to migrate); the source is logged beside it. `_item_source` uses `isinstance`
   rather than the split's `source` — documented in place, because the observer is handed only the
   item and threading the split down to it would add plumbing whose sole consumer is a log string.

5. **`split_eval` now creates the eval config and run config its params name.** The tests passed
   while `describe()` raised inside `registry.create`, which swallows and logs it — right
   assertions, half-failing create path, and a traceback in the output for the next person to chase.
   Fixed with real entities rather than a comment, and
   `test_run_eval_job_with_a_split_the_eval_has_creates_the_job` now asserts `job.properties` is
   populated, so the fix is load-bearing instead of invisible.

All four sweeps re-run clean after these changes: **13/13**, **30/30**, **23/23**, **19/19**.
