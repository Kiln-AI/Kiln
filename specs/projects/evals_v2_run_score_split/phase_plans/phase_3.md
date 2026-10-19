---
status: complete
---

# Phase 3: Runner

## Overview

Where the behavior change lands. Phases 1 and 2 built the datamodel and the lookup;
this phase makes the runner *use* them, and it is the first phase whose output on disk
looks different.

After this phase:

- A V2 job asks `TraceIndex` for its trace instead of generating one unconditionally.
  A second eval config over the same `(item, run_config)` reuses the first's generation —
  goal 1 of the functional spec.
- Generated traces are persisted as `TaskRun`s stamped with `eval_source`, before scoring
  is attempted — goal 2. Phase 1's default-exclude keeps them off every dataset surface.
- `EvalRun` becomes a pure score record: `scored_run_id` points at the trace, and no new
  record sets any deprecated inline field.
- The judge's own token cost is recorded, in `eval_usage`.

`_run_legacy_job` (V1 configs) is untouched and keeps writing inline-mode records.

### Two things the architecture did not know

Architecture §3.2 says of the run `run_task` returns: *"the run's
`output.source.run_config_id` is already set by the adapter"*, and treats persisting it
as a plain `save_to_file()`. Neither holds, and both are load-bearing. The cause is the
same line in both cases — `BaseEval.run_task` builds its adapter with
`AdapterConfig(allow_saving=False, ...)`.

**1. The run config id is not set.** `base_adapter.generate_run` reads
`output.source.run_config_id` from `AdapterConfig.task_run_config_id`, which `run_task`
never passed. That is half the trace key: a trace persisted without it can never be
found by a later index (`_stored_trace_key` returns None), which is exactly the silent,
permanent regeneration Phase 2's `_generated_path` postcondition exists to catch — so
with no change here every generated trace would raise instead. `run_task` therefore
takes the id and passes it down.

**2. The run has no id at all.** `allow_saving=False` makes every adapter take the
`else` branch that sets **`run.id = None`** ("Clear the ID to indicate it's not
persisted", `base_adapter.py:346`, mirrored in `mcp_adapter.py:209`). `save_to_file()`
on such a run raises `ValueError("ID is not set - can not save or build path")`, so
*every* V2 `task_run_eval` job would fail — and `_is_retryable_error` doesn't match that
ValueError, so `AsyncJobRunner` would report each one as a hard error. The runner mints
an id before saving, which is what `data_gen_api.py:474` already does with an unsaved
adapter run.

Flipping `allow_saving=True` would be the wrong fix: the adapter would persist the run
*before* `eval_source` is stamped on it, so a crash in that window leaves an eval trace
permanently indistinguishable from a curated dataset row — the contamination Phase 1's
default-exclude exists to prevent.

## Steps

1. **`libs/core/kiln_ai/datamodel/eval_splits.py` — `item_key()`**

   ```python
   def item_key(item: TaskRun | EvalInput) -> ItemKey: ...
   ```

   The counterpart to `eval_run_item_key()` for the item itself, so the runner has one
   place to turn a job's item into the shared vocabulary. Derived from the item's type
   rather than from `ResolvedSplit.source`, which is equivalent: `__post_init__` already
   refuses a split whose declared source disagrees with its items.

2. **`libs/core/kiln_ai/adapters/eval/base_eval.py` — `run_task` stamps the run config**

   ```python
   async def run_task(
       self, eval_job_item: TaskRun | EvalInput, run_config_id: str | None = None
   ) -> TaskRun:
   ```

   Passed through as `AdapterConfig(task_run_config_id=run_config_id)`. Defaulted rather
   than required so `run_task_and_eval` (the V1 path, which never persists) is unchanged.
   The reason it matters is the trace key, so the comment says that.

3. **`libs/core/kiln_ai/datamodel/eval.py` — `EvalTaskInput.from_trace`**

   ```python
   @classmethod
   def from_trace(cls, trace: TaskRun, source: TaskRun | EvalInput) -> "EvalTaskInput"
   ```

   The trace supplies `final_message` and `trace`; the source item supplies
   `reference_data`, and `task_input` when it is an `EvalInput` (its user message is the
   canonical item text). For a `TaskRun` source, `task_input` is the trace's own input —
   which is what both existing constructors already use.

   `from_task_run(run)` becomes `from_trace(run, run)` and
   `from_eval_input(ei, run_output)` becomes `from_trace(run_output, ei)`, so their
   current callers (`BaseV2EvalBridge.run_eval`, and Phase 4-era code) keep working with
   byte-identical results.

4. **`eval.py` — `V2EvalResult.usage`**

   ```python
   usage: Usage | None = None
   ```

   The judge's own usage, which the runner copies to `EvalRun.eval_usage`. None for the
   seven deterministic V2 types, which make no LLM call.

5. **`libs/core/kiln_ai/adapters/eval/v2_eval_llm_judge.py` — report usage**

   `invoke_returning_run_output` already returns the judge's `TaskRun` as its first
   element, and the runner discards it today. Keep it, and pass `usage=judge_run.usage`
   into the `V2EvalResult`. `TaskRun.usage`, not `cumulative_usage`, for the reason
   functional spec §5.1 gives: it already accumulates across every call the judgment made,
   and it carries latency.

6. **`libs/core/kiln_ai/adapters/eval/eval_runner.py` — construction**

   `EvalRunner.__init__` builds `self._trace_index = TraceIndex(self.task)`. Built for
   both modes even though calibration never consults it: the seed is the same
   `task.runs()` scan `collect_tasks` does, and a mode-conditional index is a second
   thing to get wrong.

7. **`eval_runner.py` — `_run_v2_job` restructured**

   Five inline `EvalRun(...)` constructions collapse to one path and two persisters:

   ```python
   async def _run_v2_job(self, job: EvalJob) -> bool:
       try:
           evaluator = v2_eval_adapter_from_config(job.eval_config, rc_props, self._skills)
       except NotImplementedError:
           return await self._persist_skip(job, SkippedReason.type_not_available, ...)

       if _is_multi_turn(job.item):
           return await self._persist_skip(job, SkippedReason.incompatible_input_shape, ...)

       trace, _ = await self._resolve_trace(job, evaluator)
       result = await evaluator.evaluate(EvalTaskInput.from_trace(trace, job.item))
       return await self._persist_eval_run(job, trace, result)
   ```

   Both skips happen before any generation, so a job that cannot be scored costs nothing.

8. **`eval_runner.py` — `_resolve_trace` and `_generate_and_persist`**

   ```python
   async def _resolve_trace(self, job, evaluator) -> tuple[TaskRun, bool]:
       if job.type == "eval_config_eval":
           # Calibration: the scored run IS the human-rated golden item. Nothing is
           # generated, so nothing is flagged, indexed or delete-protected (§4.5).
           return job.item, False
       key = trace_key(item_key(job.item), job.task_run_config.id)
       return await self._trace_index.get_or_create(
           key, lambda: self._generate_and_persist(job, evaluator, key)
       )
   ```

   `_generate_and_persist` takes the key rather than re-deriving the item's identity, so
   the `eval_source` it stamps agrees with the key it was filed under *by construction* —
   the disagreement Phase 2's postcondition checks becomes unrepresentable here rather
   than merely caught. It mints an id for the adapter's unsaved run (see above), then
   saves inside `self._save_context()` before returning, so the trace is durable before
   scoring (functional spec §4.1).

   `_resolve_trace` returns just the trace: `TraceIndex` already logs both outcomes
   itself (architecture §8), so the `was_generated` bool has no reader here.

   Which TaskRun a *calibration* job scores is known before the job starts and doesn't
   depend on reaching the judge, so `_calibration_item(job)` answers it once for both
   the scoring path and the skip path.

9. **`eval_runner.py` — `_persist_skip` and `_persist_judgment`**

   Both are thin wrappers over one `_persist_score`, which is the only place the
   item-identity fields (`dataset_id` / `eval_input_id`, `task_run_config_id`,
   `eval_config_eval`) are filled in — `collect_tasks` dedupes on exactly those, so a
   skip record and a score record that disagreed would be two identities for one job.

   Neither sets any deprecated inline field. `_persist_skip` writes no `input` — today's
   pre-generation skips do, and functional spec §3.3 says new records must not. A skip
   returned by `evaluate()` goes through `_persist_judgment` instead, carrying the
   `scored_run_id` of the trace it could not score (functional spec §4.6, row 2).

   **A calibration skip carries `scored_run_id` too**, even from the early path. The
   golden item *is* the trace: it is on disk before the job starts, so functional spec
   §4.6 row 2 applies wherever the failure happened, and a skip one step later — inside
   `evaluate()` — already records it. Without this, two calibration skips differing only
   in *where* they failed would get different record shapes, and Phase 5 (architecture
   §7) would migrate old calibration skips to a shape strictly more complete than the one
   Phase 3 writes live. A *scoring* skip still points at nothing: giving it a trace would
   mean generating one for a job that can never be scored, which is the spend the early
   skip exists to avoid.

   A skip record therefore has neither an `input` nor a `scored_run_id` to join through,
   so `implementation_plan.md` carries a note for Phase 4: `EvalRunWithTrace` must
   resolve those rows' `input` from the source item, or the results view renders an empty
   input for them forever.

   `reference_data` is read off the `EvalTaskInput` that was handed to the judge, rather
   than re-derived from the item, so the field means what `EvalRun` says it means: what
   the scorer actually saw.

10. **Deleted:** `early_input_str`, the five inline `EvalRun(...)` blocks, and the
    branch-per-(item type, job type) structure.

## Tests

`libs/core/kiln_ai/adapters/eval/test_eval_runner.py` — the existing V2 tests move to
pointer-mode expectations (`output is None`, `scored_run_id` set), plus:

**Reuse (architecture §9.3, the headline)**

- Run a V2 eval, add a second eval config, run again: `run_task` is called zero times on
  the second run, both configs have a full set of `EvalRun`s, and both point at the *same*
  `scored_run_id`. This is the project.
- Two eval configs in *one* run over the same item generate once, not twice — the
  concurrent case, which the precomputed `already_run` set could never have caught.
- A second run config generates its own trace: reuse is keyed on the run config, not
  around it.
- A second *Eval* over the same items and run config reuses the traces too — the
  cross-eval reuse functional spec §10 lists as falling out of task-level trace storage.
  It is the one reuse axis a change to the key could break without breaking anything
  else.
- A reused trace still carries its `trace` messages and `usage` after the disk
  round-trip: the two fields the split moved off `EvalRun`, and the ones a `full_trace`
  eval and Phase 4's rollup read.
- Re-running the same eval config generates nothing and writes nothing (`collect_tasks`
  already excluded it) — the guard that reuse did not come at the cost of re-scoring.

**Trace persistence**

- A generated trace is saved, carries `eval_source` equal to the item's `ItemKey`, and
  carries `output.source.run_config_id` equal to the run config — the two halves of the
  key a later index reads.
- The runner persists a run the adapter left unsaved: the generated trace lands on disk
  with a minted id, while the score still records the *source* item as `dataset_id`.
  This is the coverage that catches the `allow_saving=False` id clearing, so the test
  asserts the double's own `id is None` first — a double that drifts back to a
  default-factory id would make the whole class vacuous.
- The trace is excluded from `task.runs()` and visible with `include_eval_generated=True`.
- Scoring failure leaves the trace persisted, and the retry regenerates nothing and
  scores (functional spec §4.3). Asserted through `run_job` twice, as `AsyncJobRunner`
  would.
- Generation failure persists nothing at all — no trace, no `EvalRun` (D14).

**Record shape**

- A scored record is pointer mode: `scored_run_id` set, `input`/`output`/`task_run_trace`/
  `task_run_usage`/`reference_answer` all None, `dataset_id`/`eval_input_id` still the
  *source item* (so `collect_tasks`'s dedupe keeps working), `reference_data` preserved
  for EvalInput items.
- Calibration: `scored_run_id == dataset_id`, no TaskRun created, nothing indexed.
- A scoring skip carries `scored_run_id`. A pre-generation skip carries no `input`, and
  carries `scored_run_id` only for calibration — covered across the four existing skip
  tests, which between them span both skip reasons (unimplemented type, multi-turn) and
  both job types. Each also asserts nothing was generated, which is the claim the early
  skip exists to make and was otherwise only enforced incidentally.
- `eval_usage` round-trips from `V2EvalResult.usage`.

**Unchanged behavior**

- V1 legacy jobs still write inline records with `output` set and no `scored_run_id`
  (the existing `TestV1LegacyRunnerCoexistence` tests, unmodified).

The test double for generation, `TraceGenerator`, reproduces the shape production
returns: `id=None`, the run config on the output source, and a real `trace` and `usage`.
It yields before returning, since a generator that never suspends would let an unlocked
index look correct. The trace and usage matter because the reuse path hands back a run
*reloaded from disk* — with them None on the double, no runner test would notice if the
fields the split moved onto the TaskRun failed to survive persistence.

`libs/core/kiln_ai/datamodel/test_eval_model.py`

- `EvalTaskInput.from_trace` for both source types, and that the two existing
  constructors are equivalent to it.

`libs/core/kiln_ai/datamodel/test_eval_splits.py`

- `item_key()` agrees with `eval_run_item_key()` on the record that scores the item, and
  with the `ResolvedSplit` the item came from — the two other places the same identity is
  computed, and a disagreement writes results under one key and reads them under another.
- `item_key()` raises for anything from neither store, rather than falling through to
  `eval_input`.

`libs/core/kiln_ai/adapters/eval/test_base_eval.py`

- `run_task` passes `run_config_id` into `AdapterConfig.task_run_config_id`, and omitting
  it leaves the field None.

`libs/core/kiln_ai/adapters/eval/test_v2_eval_llm_judge.py`

- The judge's usage reaches `V2EvalResult.usage`.

Mutation-checked: removing the trace index from `_resolve_trace`, removing its per-key
lock, dropping `task_run_config_id` from `run_task`, dropping the minted id, dropping the
calibration skip's `scored_run_id`, and clearing `trace`/`usage` before persisting each
fail a test that claims the behavior (the minted id fails twelve).

`app/desktop/studio_server/test_eval_api.py` needed one mock corrected: two judge tests
returned `(None, run_output)` from `invoke_returning_run_output`, whose contract is
`Tuple[TaskRun, RunOutput]`. The first element is now read.
