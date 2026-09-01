---
status: complete
---

# Phase 1: Datamodel and default-exclude

## Overview

Lay the datamodel foundation for splitting eval traces (TaskRun) from eval scores
(EvalRun), and put the protective default in place *before* anything starts writing
eval-generated TaskRuns into `runs/`.

Everything here is additive or protective:

- `TaskRun` gains `eval_source`, the flag that marks a run as eval-generated.
- `Task.runs()` gains `include_eval_generated=False` — eval traces are excluded from
  every dataset surface by default. Architecture §10 makes this the hard ordering
  constraint: it must land before Phase 3 teaches `run_task` to persist.
- `EvalRun` gains `scored_run_id` (pointer mode) and `eval_usage` (judge cost), and its
  five inline trace fields are deprecated.
- A new `validate_record_mode` validator constrains an EvalRun to three legal shapes
  (pointer / skipped / legacy inline). What it makes exclusive is *where the trace
  lives* — on the record or on the TaskRun, never both — so a pointer record can never
  carry a stale second copy of what it scored. Pointer and skipped are not themselves
  exclusive: a record skipped at scoring time is both.

Nothing writes the new fields yet. Every V1 record on disk still loads unchanged.

## Steps

1. **`libs/core/kiln_ai/datamodel/task_run.py` — `EvalItemSource` + `eval_item_key()`**

   Defined here rather than in `eval.py`: `eval.py` imports `TaskRun` under
   `TYPE_CHECKING` only, so putting this type there and referencing it from `TaskRun`
   would create a real import cycle. `eval_splits.py` already imports from `task_run.py`,
   so the helper's `ItemKey` return type is a `TYPE_CHECKING`-only import in the
   other direction.

   ```python
   class EvalItemSource(BaseModel):
       source_type: Literal["eval_input", "task_run"]
       source_id: str = Field(min_length=1)


   def eval_item_key(source: EvalItemSource) -> "ItemKey":
       return (source.source_type, source.source_id)
   ```

   **Deviation from architecture §1.1:** `source_id` is `str`, not `ID_TYPE`. `ID_TYPE`
   is `Optional[str]`, so an id-less source would validate and `eval_item_key()` would
   yield `("eval_input", None)` — a trace-index key that collides with every other
   id-less source. Absence is already expressed by `TaskRun.eval_source` itself being
   None, so the inner id has no legitimate None state, and `ItemKey`'s own nullability
   is inherited from `KilnBaseModel.id` rather than chosen. Tuple covariance means
   `eval_item_key()` still returns a valid `ItemKey`. Settled in Phase 1 because Phase 2
   builds the trace index on this key, and it is a field written to disk forever.
   The cost is that Phase 3 call sites passing `item.id` (typed `ID_TYPE`) need an
   explicit None check.

   Also export `EvalItemSource` from `kiln_ai.datamodel` (`__init__.py` import and
   `__all__`), matching every other embedded public type (`Usage`, `DataSource`,
   `TaskOutput`, `Feedback`).

2. **`task_run.py` — `TaskRun.eval_source`**

   ```python
   eval_source: EvalItemSource | None = Field(default=None, description=...)
   ```

   No validators. Presence is the eval-generated flag (functional spec §3.1).

3. **`libs/core/kiln_ai/datamodel/task.py` — `Task.runs()` third filter**

   ```python
   def runs(self, readonly: bool = False,
            include_intermediate_runs: bool = False,
            include_eval_generated: bool = False) -> list[TaskRun]:
   ```

   Restructure the body so the leaf filter no longer early-returns, then apply
   `if not include_eval_generated: runs = [r for r in runs if r.eval_source is None]`.
   Both filters compose. Docstring explains why the default is exclude.

4. **`libs/core/kiln_ai/datamodel/eval.py` — `EvalRun` fields**

   - Add `scored_run_id: ID_TYPE | None = None`.
   - Add `eval_usage: Usage | None = None` (the judge's usage, counterpart to the
     deprecated `task_run_usage`).
   - `input: str` → `input: str | None = None`.
   - Deprecate `input`, `output`, `task_run_trace`, `task_run_usage`,
     `reference_answer` two ways: a `DEPRECATED:` prefix in the description (for a
     human reading the SDK docs) and `json_schema_extra={"deprecated": True}` (which
     `openapi-typescript` turns into a `/** @deprecated */` JSDoc tag, so the TS
     compiler strikes through every web call site). Fields stay declared and loadable
     forever. Deliberately **not** `Field(deprecated=True)`: same schema output, but
     pydantic also raises a `DeprecationWarning` on every attribute *read*, and reading
     these is the correct permanent way to render a legacy record. All three options
     are recorded on `LEGACY_TRACE_FIELDS` so the tradeoff isn't re-derived.

   Relaxing `input` to `str | None` is a breaking SDK/API change — see
   *For the PR description* at the end of this plan.

5. **`eval.py` — `LEGACY_TRACE_FIELDS` + `validate_record_mode`**

   ```python
   LEGACY_TRACE_FIELDS = ("output", "task_run_trace", "task_run_usage", "reference_answer")
   ```

   Pointer branch first (so a skipped-at-scoring-time record, which has a
   `scored_run_id`, still gets the no-inline-data check), then the skip early return,
   then the legacy `input`-required rule.

6. **`eval.py` — `validate_output_fields` early return for pointer records**

   The "V1 EvalRun requires output" rule must not fire for pointer-mode records; add
   `if self.scored_run_id is not None: return self` alongside the existing V2 bypass.
   Resolve `parent_eval_config()` before the bypass, so the pointer path can't skip the
   parent-type check.

7. **Regenerate `app/web_ui/src/lib/api_schema.d.ts`** via
   `app/web_ui/src/lib/generate_schema.sh` so `check_schema.sh` passes.

## Tests

`libs/core/kiln_ai/datamodel/test_eval_model.py`:

- `validate_record_mode` pointer + `input` set → raises.
- `validate_record_mode` pointer + each of the four legacy trace fields → raises
  (parametrized over `LEGACY_TRACE_FIELDS`).
- Pointer record with only scores → valid, and `scored_run_id` round-trips to disk.
- Legacy record without `input` and without a skip → raises.
- Legacy record with `input` → valid (existing behavior, guarded).
- Skipped record with no `scored_run_id` and no `input` → valid.
- Skipped record with `scored_run_id` and no inline data → valid.
- Skipped record with `scored_run_id` and inline data → raises.
- `validate_output_fields` no longer requires `output` for a pointer record under a V1
  (`g_eval`) config — the early return.
- `eval_usage` defaults to None and round-trips.
- A V1 EvalRun file written before this phase (fixture written to disk with the old
  field set) still loads unchanged — regression guard for D15.

`libs/core/kiln_ai/datamodel/test_example_models.py` (TaskRun tests):

- `EvalItemSource` round-trips on a TaskRun; `eval_source` defaults to None.
- `EvalItemSource` rejects an unknown `source_type`, and rejects a None or empty
  `source_id`.
- `EvalItemSource.source_type`'s literals match `eval_splits.ItemSource` — a drift
  guard, since the duplication is forced by the import direction.
- `eval_item_key()` produces the same shape as `eval_run_item_key()` for both source
  types.

`libs/core/kiln_ai/datamodel/test_task.py`:

- `Task.runs()` excludes eval-generated runs by default.
- `Task.runs(include_eval_generated=True)` includes them.
- The two filters compose: an eval-generated *intermediate* run is excluded unless both
  flags are set, and each flag alone is not enough.

## For the PR description

**Breaking SDK/API change**, called out per `.agents/code_review_guidelines.md`:

`EvalRun.input` goes from `str` to `str | None`.

- **Python SDK:** typed consumers lose `eval_run.input.strip()` without a None check.
- **Web / TS:** the generated type goes from required `input: string` to optional
  `input?: string | null`, and the field is now tagged `@deprecated`.

This is what functional spec §3.2 / D15 mandate — the field is deprecated, and
pointer-mode records must not set it — but it is a real break, not an absorbed detail.
Legacy records on disk are unaffected: they keep their `input`, and
`validate_record_mode` still requires it on any record that is neither a pointer nor a
skip.
