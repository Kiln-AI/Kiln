---
status: complete
---

# Phase 6: API endpoints and web UI

## Overview

Phases 2–5 made the *write* side split-aware: an eval carries `splits`, the runner takes a
`ResolvedSplit`, and the jobs API can run train, val, or an EvalInput-backed test set end to end.
The **read** side is still test-only and still TaskRun-shaped: every summary, count and result list
in `eval_api.py` reads `eval.eval_set_filter_id` and matches `EvalRun.dataset_id` against bare
`TaskRun` ids. For an EvalInput-backed eval that means a 400 ("This endpoint isn't supported for
this eval type") or a silent skip. This phase moves those readers onto `resolve_split` /
`eval_run_item_key`, adds the required `split` parameter to the results endpoint, and adds
`val_dataset_size` to progress. Architecture §6, functional spec §5 and §6.1.

The web UI is the other half, and it is not small. Nine `eval_set_filter_id` reads and four
`train_set_filter_id` reads across five Svelte pages currently work only because phases 2 and 3
kept those legacy fields populated on disk for TaskRun-backed test and train splits. They are
wrong for a V2 eval today (`"null (30 items)"` on the eval detail page) and wrong for any split
this project newly makes possible.

### The web client has to fold, exactly like the datamodel does

The one thing a reader of the API response must understand: `Eval.serialize_preserving_split_format`
writes a legacy-homed split to its legacy flat field and **omits it from the serialized `splits`
dict**. So a legacy eval's JSON is `{eval_set_filter_id: "tag::x", splits: {}}` and a native one is
`{eval_set_filter_id: null, splits: {test: {...}}}`. A UI that reads only `splits` breaks on every
existing eval; one that reads only the legacy fields breaks on every new one. `$lib/utils/eval_splits.ts`
is the TS mirror of `Eval.fold_legacy_filter_fields`, with the same precedence (legacy field wins),
and every UI read goes through it.

It draws one distinction the legacy fields could not: a **dataset tag** and a **dataset link**
address `task.runs()`, so they are only meaningful for a TaskRun-backed split.
`task_run_split_filter_id` returns a filter id only for that backing, and callers that build
`/dataset/...?tags=` links or synthetic-data-generation splits use it. Callers that merely *display*
the filter id use `eval_split_filter_id`, which is backing-agnostic.

### Closing the SSE refusal

Phase 4 recorded that `require_golden_set_or_422` and `resolved_split_or_422` produce correct 4xx
responses the browser never sees, because `run_eval.svelte` opens the SSE endpoints with
`EventSource` — which cannot read the status or body of a non-200 and fires `onerror` with a bare
`Event`, rendered as "Unknown error". Both phases 4 and 5 assigned the fix to "phase 6's web-UI
work".

**This phase takes it.** It is a real user-visible bug today, not a hypothetical: running
calibration on a V2 eval with no golden set produces "Eval Errors / Unknown error" with no
indication of what is wrong. Nothing later in the project owns the web UI — phase 7 is
overview-only — so declining it would make it homeless the way the two `eval_runner.py` items are.
The fix is contained to one component plus a tested helper: `$lib/utils/sse_stream.ts` reads the
stream with `fetch` + a `ReadableStream` reader, so a non-2xx response is read as a normal
`{message}` error body and handed to `createKilnError`. `AbortController` replaces
`EventSource.close()`, which `CancellableStreamingResponse` already handles identically (it cancels
the body iterator on client disconnect).

Scope guard: only `run_eval.svelte` moves. `jobs_store.ts` and `rag_progress_store.ts` also use
`EventSource`, but neither has a 4xx-refusal path to surface, and both have reconnect/backoff
semantics that `EventSource` provides for free.

### The two `eval_runner.py` carry-overs

This phase does not open `eval_runner.py`. Architecture §6 is `eval_api.py` and the web UI; nothing
here reads or writes `run_job` or `collect_tasks_for_eval_config_eval`. Both items stay recorded in
`implementation_plan.md`'s `## Notes` for phase 7 or a follow-up.

---

## Steps

### 1. `eval_api.py` — `get_eval_run_results` takes a required `split`

Add the query parameter and filter on membership:

```python
        split: Annotated[
            EvalSplitName,
            Query(
                description="Which of the eval's dataset splits to return results for. "
                "Required: every response about eval results is scoped to exactly one "
                "split, and reading has no obvious default the way running does."
            ),
        ],
    ) -> EvalRunResult:
        task = task_from_id(project_id, task_id)
        eval = eval_from_id(project_id, task_id, eval_id)
        ...
        resolved_split = resolved_split_or_422(task, eval, split)
        results = [
            run_result
            for run_result in eval_config.runs(readonly=True)
            if run_result.task_run_config_id == run_config_id
            and eval_run_item_key(run_result) in resolved_split
        ]
```

Required rather than defaulted so the regenerated OpenAPI client types it as required and a missed
caller is a build failure (functional spec §5).

### 2. `eval_api.py` — `compute_score_summary` over a `ResolvedSplit`

Signature changes from `expected_dataset_ids: set[ID_TYPE]` to `split: ResolvedSplit`, and the
`remaining_expected_dataset_ids` bookkeeping keys on `ItemKey`:

```python
def compute_score_summary(
    eval: Eval,
    eval_config: EvalConfig,
    task_run_configs: list[TaskRunConfig],
    split: ResolvedSplit,
) -> EvalResultSummary:
```

`eval_run.dataset_id` membership becomes `eval_run_item_key(eval_run)`. Same for
`get_run_config_eval_scores`'s inline copy of the same loop.

### 3. `eval_api.py` — `get_eval_progress`

- `EvalProgress` gains `val_dataset_size: int`.
- The `eval_set_filter_id is None` 400 is deleted.
- All three sizes come from the accessor, but **not all three map `None` the same way**: train and
  val go through a `split_size` helper (`None → 0`), while test goes through `resolved_split_or_422`.
  Architecture §7's table said `0` for every split here; that is right for train and val — an eval
  with no val split has a val size, and it is zero — and wrong for test, where `0` would report an
  empty eval set for what is really a malformed eval, the failure §6.1 calls worse than an error.
  §7's row is amended to match; this is the one place phase 6 diverges from it.
- `ResolvedSplit` defines `__len__`, so an empty split is falsy — every absence check in this phase
  is `is None`, never truthiness.

### 4. `eval_api.py` — `get_eval_config_score_summary`

The `eval_set_filter_id is None` 400 becomes `resolved_split_or_422(task, eval, "test")`. The
existing empty-split 400 is retained verbatim: it is about emptiness, not backing.

### 5. `eval_api.py` — `get_eval_results_summary`, source-aware cache

The `if filter_id is None: continue` becomes a `resolve_split(task, eval, "test")`, and the per-eval
cache keys on `(source, filter_id)` — the `tag::` grammar is shared across both stores, so the
filter id alone does not identify which one it addresses (functional spec §5.3). A cache hit
re-stamps `ResolvedSplit.eval_id` with `dataclasses.replace`, so a split value cannot outlive the
eval it claims to describe.

### 6. `eval_api.py` — `get_run_config_eval_scores`

`eval.eval_set_filter_id is None → continue` becomes `resolve_split(task, eval, "test") is None →
continue`, and its `remaining_expected_dataset_ids` set becomes `ItemKey`-keyed.

### 7. `eval_api.py` — delete `dataset_ids_in_filter`

Nothing calls it once steps 3–6 land. `runs_in_filter` stays: the golden set is TaskRun-typed by
definition (functional spec §6.2).

### 8. `$lib/utils/eval_splits.ts` — the TS fold

```ts
export type EvalSplitName = "train" | "val" | "test"
export type EvalSplitRef = { source: "task_run" | "eval_input"; filter_id: string }

export function eval_split(evaluator, name): EvalSplitRef | undefined
export function eval_split_filter_id(evaluator, name): string | undefined
export function task_run_split_filter_id(evaluator, name): string | undefined
```

### 9. Web UI readers

| File | Change |
|---|---|
| `[eval_id]/+page.svelte` | Eval / Training dataset rows through the helper; new Validation Dataset row; `add_eval_data`'s tag from `task_run_split_filter_id` |
| `[spec_id]/+page.svelte` | Eval Dataset link from `task_run_split_filter_id` |
| `compare/+page.svelte` | `navigateToAddData`'s eval tag from `task_run_split_filter_id`, plus the two refusals the eval detail page already had |
| `run_result/+page.svelte` | passes `split: "test"`; "Task Inputs From Dataset" from `eval_split_filter_id` |
| `data_gen_intro.svelte` | `select_eval_by_id`'s filter id from `task_run_split_filter_id` |
| `create_prompt_optimization_job/+page.svelte` | three `train_set_filter_id` reads → `task_run_split_filter_id(eval, "train")` |

Fixtures move with them: `create_eval_config/page.test.ts`, `page.reference_data.test.ts`,
`eval_detail.test.ts`, `generate/.../eval_options.test.ts`.

### 10. `$lib/utils/sse_stream.ts` and `run_eval.svelte`

`stream_sse(url, {on_message, on_error, subject})` returning a `close()`. Non-2xx → parse the JSON
body and hand it to `on_error`, so `createKilnError` renders the server's `message`. The module is
domain-neutral, so the one message it composes itself — a body that ends early — takes its noun from
`subject` rather than naming evals.

### 11. Phase 5's five deferred cosmetic items

- `jobs/test_api.py`'s `split_eval` fixture drops its unused `monkeypatch` parameter.
- `jobs/workers/eval.py`'s `_item_source` moves above `_EvalErrorLogObserver`, its only caller.
- `phase5_mutation_sweep.py` gains an `item_source` mutation.
- `jobs/api.py`'s endpoint comment says that entity existence is checked only on the split-named
  path.
- `_resolve_split`'s "contract, not a reachable state" is qualified: it is exact at request time,
  and a split deleted between creation and execution does reach it.

### 12. Regenerate `app/web_ui/src/lib/api_schema.d.ts`

---

## Tests

### `app/desktop/studio_server/test_eval_api.py`

`stub_split` / `patch_resolve_split` / `patch_resolve_split_by_ref` replace the
`dataset_ids_in_filter` patching the file used throughout. The by-ref variant answers from each
eval's own `splits`, keyed on `(source, filter_id)`, which is what lets the cache tests give one
filter id different items in each store.

`TestGetEvalRunResultsSplits`:

- `test_requires_a_split` — omitting it is a 422.
- `test_unknown_split_name_is_rejected_before_anything_loads` — `split=holdout` is a request
  validation 422.
- `test_422s_for_a_split_this_eval_does_not_have` — naming the split and the eval id.
- `test_returns_only_the_requested_splits_results` — test and train requests over the same run
  config return disjoint result sets, and an untagged item's run appears in neither.
- `test_returns_eval_input_backed_results` — runs carrying `eval_input_id`.
- `test_does_not_credit_a_task_run_to_an_eval_inputs_id` — a `TaskRun` and an `EvalInput`
  constructed with the *same* id; the TaskRun-sourced run must not appear.

`TestEvalProgressSplitSizes`: each split's own size; absent splits report 0 rather than being
absent from the response; an EvalInput-backed eval is counted rather than 400'd, with golden 0.

`TestSplitSize`: absent and empty both answer 0, stated as separate cases because only the `is None`
check distinguishes them.

`TestScoreSummarySplits`: an EvalInput-backed test split is summarized; the empty-split 400 still
fires; a colliding-id TaskRun score is not averaged into an EvalInput-backed split.

`TestRunConfigEvalScoresSplits`: an EvalInput-backed eval is scored with the right universe and
percent complete; the colliding-id case again, this endpoint's own copy of the loop. The second was
added because the mutation sweep found the first version of this phase had no test that caught bare-id
membership *here* — only in `compute_score_summary`.

`TestCachedTestSplit`: one resolution per `(source, filter_id)`; a cache hit re-stamped with the
asking eval's id; the same filter over a different store as a separate entry; `None` for an eval
with no test split.

`test_eval_results_summary_dataset_ids_cached_per_filter` gains the source-aware third case.

### `libs/core/kiln_ai/datamodel/test_eval_splits.py`

Two cases for `__len__`'s new definition: that it equals `len(item_keys())` — the invariant every
progress calculation depends on — and that duplicate items collapse to one.

### `app/web_ui/src/lib/utils/eval_splits.test.ts`

Legacy-only, `splits`-only, EvalInput-backed, both-present (legacy wins), absent split, absent eval,
and an eval with no `splits` key. Plus the distinction that motivates the two accessors: an
EvalInput-backed split has a filter id to display but none to build a dataset link from.

### `app/web_ui/src/lib/utils/sse_stream.test.ts`

Framing: dispatch in order; reassembly across a chunk boundary; several events in one chunk; a
multi-line `data:` field joined into one payload; non-`data:` lines ignored; a partial event held
back. `subject` both ways — interpolated when given, neutral by default — asserted on the whole
composed sentence, since a fragment would pass a hardcoded noun too.

Termination: a 422 body's `message` reaching `createKilnError`; a non-JSON error body falling back
to the status; a transport failure; a body that ends without `data: complete` reported rather than
swallowed, paired with the happy path where the caller closed on the terminal message and *nothing*
is reported; `close()` stopping dispatch without reporting; and abort on both terminal paths — after
`close()` and after a handler throws — so the server always sees the disconnect.

### `app/web_ui/src/routes/.../eval_detail.test.ts`

The page's fixtures became settable so two new cases can drive it: a legacy eval renders its rows
from the flat fields, and a `splits`-only eval renders all three — including the val row and an
EvalInput-backed test filter id, which the old code rendered as `"null (30 items)"`. The
`property_list` stub now serializes its props into a data attribute; that is the only way to assert
on rows the real component is mocked out of.

Both cases also assert each row's `link`, which is what pins the two accessors apart: the
EvalInput-backed test row shows its filter id but has **no** `/dataset` link, while the
TaskRun-backed train and val rows do. That needed the `linkFromFilterId` stub to stop returning
`undefined` unconditionally — a stub that always returns nothing cannot tell "the TaskRun-only
accessor correctly returned nothing" from "the wrong accessor was used". Verified by swapping the
two accessors on the page: the splits-only case fails.

### Mutation sweep

`specs/projects/eval_splits_v1_v2/phase6_mutation_sweep.py`, same harness as phases 2–5.
**15 mutations, all killed**, covering: the results endpoint's split parameter made optional again,
returning an unscoped set, reading `"test"` regardless of what was asked, and bare-id membership;
progress reporting val as train, treating an absent split as non-zero, and re-introducing the
deleted 400; `compute_score_summary`'s bare-id membership and its no-double-count bookkeeping;
the deleted 400 re-introduced in both remaining summary readers; `get_run_config_eval_scores`'s
bare-id membership; and all three properties of `_cached_test_split` (source in the key, the
eval-id re-stamp, and the cache actually being used).

The sweep earned its place here: *get_run_config_eval_scores: membership keyed on the bare id*
SURVIVED on the first run, and the test that kills it was written in response.

Web-side behavior is covered by vitest rather than pytest, so it is not in this harness.

Phases 2–5's sweeps re-run clean against this tree: **30/30**, **23/23**, **19/19**, and — with
this phase's added `item_source` entry — **14/14**.

---

## Judgment calls made during implementation

Recorded for disagreement; not derived from `architecture.md`.

1. **The web client folds legacy fields into `splits`, rather than the API being changed to always
   emit `splits`.** Three options, not two:

   - *Change the serializer to always emit `splits`.* Rejected: it breaks architecture §2.6's
     byte-identical round trip, the project's highest-risk property and the one thing phase 2 was
     told to stop for.
   - *Add an API-only computed field* — say `resolved_splits`, derived from `Eval.splits` after the
     fold and excluded from the on-disk dump — so the client reads one shape and `eval_splits.ts`
     disappears. This does **not** carry the round-trip risk, so the plan should not lean on that
     argument to dismiss it. Rejected on narrower grounds: `Eval` is serialized by a `model_serializer`
     that already had to be taught not to erase the model from the OpenAPI schema
     (`__get_pydantic_json_schema__`), and a field present in the API dump but absent from the file
     dump means the two differ by more than provenance — every `model_dump` call site would need to
     know which one it is doing. That is a second, subtler duplication in the riskiest file in the
     project, traded for deleting a 75-line pure function with 9 tests.
   - *Mirror the fold in TS* — taken. The mirror is now named in `LEGACY_SPLIT_FIELDS`' and
     `fold_legacy_filter_fields`' docstrings, so an edit on the Python side has a signal pointing at
     the second implementation. That back-reference is the whole guard; there is no test that
     catches a one-sided change, and that is the real cost of this option.

2. **Two accessors (`eval_split_filter_id` and `task_run_split_filter_id`) rather than one.** A
   single accessor would have every caller either build broken `/dataset` links for EvalInput-backed
   splits or repeat the `source === "task_run"` check. Which of the two a call site wants is a real
   question about what it does with the answer, so the type system asks it.

3. **`_cached_test_split` re-stamps `eval_id` on a cache hit instead of caching only the item set.**
   Architecture §6.3 says `compute_score_summary` takes a `ResolvedSplit`; caching bare item sets
   would mean resolving per eval anyway, which is the cost the cache exists to avoid. `eval_id` is
   documented as "carried so a consumer handed a split can check it belongs to the eval it is
   working on", so a cached value naming the wrong eval would silently break that check for a future
   consumer. `dataclasses.replace` recomputes only the key set, which is cheap next to the disk walk.

4. **`get_eval_results_summary` and `get_run_config_eval_scores` skip an eval whose test split does
   not resolve; `get_eval_config_score_summary` 422s.** Architecture §7's table assigns 422 to the
   single-eval endpoint only. The two aggregate-over-all-evals endpoints would empty a whole page for
   one corrupt file. `Eval.validate_splits` makes both branches unreachable for anything that loads;
   the comments say so rather than implying a live case.

5. **The `no_golden_set` and `no such split` refusals are now visible, so their docstrings changed.**
   `require_golden_set_or_422` claimed the contract but explicitly not the screen. That caveat is
   false after step 10, and left standing it would send the next reader looking for a gap that has
   been closed. The same sweep updated the two `# JS SSE client (EventSource) doesn't work with
   POST` comments, which described a client these very endpoints no longer have; GET is retained
   per `.agents/api_code_review.md`'s SSE exception, and the comments now say that instead.

6. **`ResolvedSplit.__len__` became the item-key count, a deliberate touch outside `eval_api.py`.**
   Review caught `get_run_config_eval_scores` deriving `dataset_size` from `len(test_split)` (items)
   while its bookkeeping used `item_keys()` (distinct keys) — a denominator its numerator could
   never reach. Fixing the call site would have left `get_eval_progress` and `compute_score_summary`
   still reporting two different `dataset_size` values for one eval. Making `__len__` the key count
   gives "how big is this split" one answer everywhere, and incidentally aligns the jobs worker's
   `total=len(split)` with its key-based `success`. Only observable if one store ever held two items
   with the same id, which is why it is a consistency fix rather than a bug fix.

## Two other bare-id membership loops exist, and are correct

`get_eval_configs_score_summary` (`eval_api.py`) and `collect_tasks_for_eval_config_eval`
(`eval_runner.py`) both still key membership on a bare `eval_run.dataset_id`. **Neither is a missed
migration.** Both iterate the *golden* set, which is `eval_configs_filter_id` — `DatasetFilterId`-typed,
resolved over `task.runs()`, and never populated from EvalInputs (functional spec §6.2). There is one
store in play, so `(source, id)` adds nothing there. Recorded so a later reader doing the same grep
this phase did doesn't "fix" them into needless churn.

## The "add data" refusal is now consistent across all three entry points

Three places navigate a user toward adding eval data, and each had to learn that an EvalInput-backed
test split can't receive TaskRuns: the eval detail page, the data-gen dialog, and the compare page.
The compare page also gained the *second* guard the eval detail page already had — refusing when
there is no golden tag on a non-rag eval — because without it the function fell through to a
navigation with no `splits` param at all, and the user added rows that silently never joined the
eval's set. That branch is reachable in ordinary use, not just in the EvalInput case: a non-rag eval
with no golden set is the expected V2 state (functional spec §6.1), and the button appears precisely
when the eval's test split is empty.

Both messages diagnose and stop. Neither says "add eval inputs instead" — nothing in this repo
creates `EvalInput` records, so that would point at a button that does not exist.

## Known limitations

### `stream_sse` is not a general SSE client

It parses `data:` lines and nothing else — no `event:`, no `id:`, no retry, no reconnection. That is
exactly what these two endpoints send and exactly what `run_eval.svelte` consumed from
`EventSource`, and inventing the rest would be unexercised code. `jobs_store.ts` and
`rag_progress_store.ts` still use `EventSource`; both want its automatic reconnection, and neither
has a 4xx refusal to surface, so moving them would be cost without benefit.

### The jobs UI still does not show which split a job ran

Phase 5 recorded this. Unchanged: `EvalJobProperties` carries the eval, run config and judge but not
the split, so two jobs over the same eval and run config render identically. Still only reachable
programmatically — functional spec §4.4 keeps `split` off the SSE endpoints, and this phase did not
add a UI that creates a non-test eval job.

### The two `eval_runner.py` carry-overs are still open

This phase does not open `eval_runner.py`, as phase 5 predicted. `EvalJob` still does not express
which item types each run type can carry, and calibration dedupe still ignores what a run was *for*.
Both remain in `implementation_plan.md`'s `## Notes` for phase 7 or a follow-up.

## Deliberately not done

- **`split` on the SSE run endpoints.** Functional spec §4.4 keeps train and val off them.
- **A per-split view in the results UI.** The page passes `"test"` because that is what it renders,
  and functional spec §5.2 is explicit that results carry no split label. Offering a split picker
  would be new product surface, not a migration.
- **Changing `runs_in_filter` or the golden-set reader.** Golden is TaskRun-typed by definition
  (functional spec §6.2); no validator restricts it based on an eval's split backings.

---

## Check status

`uv run ./checks.sh --agent-mode` reports two failures, both pre-existing and both recorded
identically by phases 3–5:

- **openapi schema** — `check_schema.sh` imports `desktop_server`, which imports `tkinter`, which
  isn't installed in this container. The check cannot run here; it is not reporting a stale schema.
- **python tests** — `7311 passed, 0 failed`, plus the same five collection errors from the same
  missing `tkinter` (`test_desktop.py`, `test_server.py`, `test_import_api.py`,
  `test_start_background_syncs.py`, `git_sync/test_sse_invariants.py`).

Everything else — `ruff check`, `ruff format`, `ty check`, and all five web checks (2196 tests) —
passes.

`api_schema.d.ts` was regenerated with `tkinter` stubbed, using phase 5's procedure and re-verifying
its premise first: on the tree at `HEAD`, the stub-generated file is **byte-identical** to the
committed one, so the stub reproduces what CI produces. The resulting diff is 14 lines — the
required `split` query parameter, `val_dataset_size`, and two description changes.
