---
status: complete
---

# Phase 4: `EvalRunner`

## Overview

The runner stops asking the eval which store backs it and starts being handed the items it is
supposed to work on. Three things change together (architecture §4):

1. `EvalRunner.__init__` takes `split: ResolvedSplit | None`. The eval-level `_source_mode` is
   deleted.
2. `collect_tasks` loses its source branch: `eval_config_eval` scopes by the golden filter (always
   `TaskRun`s), everything else iterates the resolved split's items, whichever store they came from.
   `collect_tasks_for_eval_input` is deleted.
3. The `EvalInput` + `eval_config_eval` branch of `_run_v2_job` — which persisted a deliberately
   empty `EvalRun` per item — is deleted, because `collect_tasks` can no longer produce that job.

The three construction sites must pass a split in the same commit or the tree lands red, so this
phase also touches `eval_api.py` (twice) and `jobs/workers/eval.py` (once), minimally. See
"Scope at the call sites".

Review added two things that belong to the same change: `ResolvedSplit` carries the eval it was
resolved from, so a split can't be handed to the wrong eval's runner; and calibration's "no golden
set" refusal moves to construction and gains a 422, because as a `collect_tasks` raise it arrived
after the SSE response had already returned 200.

## Steps

### 1. `libs/core/kiln_ai/adapters/eval/eval_runner.py` — the constructor

```python
def __init__(
    self,
    eval_configs: List[EvalConfig],
    run_configs: List[TaskRunConfig] | None,
    eval_run_type: Literal["eval_config_eval", "task_run_eval"],
    split: ResolvedSplit | None = None,
    save_context: SaveContext | None = None,
):
```

Validation, alongside the existing run-config checks:

- `task_run_eval` with `split is None` → `ValueError`.
- `task_run_eval` with a split whose `eval_id` isn't this eval's → `ValueError`. **Added in
  review.** The runner derives `self.eval` from the eval config's parent chain but accepts any
  `ResolvedSplit`, so `EvalRunner(eval_configs=[a_config], split=resolve_split(task, other_eval,
  "test"))` ran one eval's judges over another's items in silence. Before this phase the item set
  came from the eval and that was unconstructible; §4.2's standard is "impossible by construction,
  not by convention", so `ResolvedSplit` gains an `eval_id` (architecture §3.2, edited from this
  phase) and the runner checks it.
- `eval_config_eval` with a `split` → `ValueError` (it scopes by the golden filter).
- `eval_config_eval` on an eval with no golden set → `ValueError`. **Moved here in review**, from
  `collect_tasks`; see "The golden-set refusal" below.

`self._source_mode` is deleted. `self.split` holds the resolved split, and
`self.golden_filter_id` the golden filter for the other mode — both modes' item scope is settled at
construction rather than at collect time.

The parameter keeps a default so the two `eval_config_eval` call sites don't have to pass
`split=None` explicitly; the `task_run_eval` requirement is enforced in the body rather than by the
signature, which mirrors how `run_configs` is already handled (also `| None`, also required for one
mode only).

### 2. `collect_tasks` and `collect_tasks_for_task_run_eval`

```python
def collect_tasks(self) -> List[EvalJob]:
    if self.eval_run_type == "eval_config_eval":
        if self.golden_filter_id is None:
            raise ValueError(no_golden_set_message(self.eval))
        return self.collect_tasks_for_eval_config_eval(self.golden_filter_id)
    return self.collect_tasks_for_task_run_eval()
```

`collect_tasks_for_task_run_eval` iterates `self.split.items` and dedupes on
`(eval_config_id, run_config_id, ItemKey)`:

```python
already_run: Dict[ID_TYPE, Dict[ID_TYPE, Set[ItemKey]]] = {}
```

built from `eval_run_item_key(run)` for each of the eval config's runs that is both **not a
calibration record** (`task_run_config_id is not None`) and **for one of this runner's run configs**
(the membership test). The membership test scopes the dedupe to the run configs actually being
evaluated — an eval config accumulates runs for every run config ever compared against it.

An earlier version dropped the `is not None` half, reasoning that `None` is never a key so
calibration records fall out anyway. **Restored in review**, and the reasoning was wrong: `ID_TYPE`
is `str | None`, so a run config file carrying a null id loads with `id=None`, `None` becomes a real
key, and every calibration record on the eval config folds into that run config's already-run set —
silently skipping items that were never scored for it. A silently-short run is the failure class
§4.2 exists to remove.

An item's key is `(self.split.source, item.id)`. The runner does not `isinstance`-test items to
find their source: the split it was handed already says, which is the point of resolving at the
seam. `ItemKey` rather than a bare id is functional spec §5.3 — one id generator across model types
means a `TaskRun` and an `EvalInput` can collide, and a bare-id dedupe would silently drop the
second one's job.

`TaskRunSplit`, `EvalInputSplit` and `eval_input_filter_from_id` leave this module's imports.
`dataset_filter_from_id` stays: `eval_config_eval` still resolves the golden filter itself, which
is TaskRun-only by definition (architecture §3.4).

### 3. `collect_tasks_for_eval_input` is deleted

Nothing dispatches to it. Its whole job was re-implementing both run types for the EvalInput store,
which is now the same code path as the TaskRun store.

### 4. The `EvalInput` + `eval_config_eval` branch of `_run_v2_job` is deleted

Architecture §4.3. Judge calibration is scoped by `eval_configs_filter_id`, which is
`DatasetFilterId`-typed, so its items are always `TaskRun`s; the branch that handled an `EvalInput`
arriving there has nothing left to handle. The skipped-record write goes with it.

`SkippedReason` is still imported — the two remaining skip writers (`type_not_available` and
multi-turn `incompatible_input_shape`) use it.

### Scope at the call sites

Passing a `ResolvedSplit` is a constructor change, so every construction site has to move now.
Phases 5 and 6 own those files' real reshaping; this phase does the minimum that keeps the tree
green and does not pre-empt them.

- **`eval_api.py` `run_eval_config`** (the SSE run-comparison endpoint) — resolves the eval's
  `test` split through a new module-level helper:

  ```python
  def resolved_split_or_422(task: Task, eval: Eval, split: EvalSplitName) -> ResolvedSplit:
      """The split's items, or a 422 naming the split and the eval (architecture §7)."""
  ```

  Phase 6 adds the `split` query parameter and reuses this helper for `get_eval_run_results`; the
  message shape is architecture §7's, so it does not need re-deciding then.
- **`eval_api.py` `run_eval_config_eval`** (calibration) — passes no split, and guards with
  `require_golden_set_or_422(eval)`. See below.
- **`jobs/workers/eval.py` `_build_eval_runner`** — resolves `test` and raises on `None`. Phase 5
  replaces this with a single resolution shared with `compute_state`'s progress universe and adds
  `EvalJobParams.split`; nothing here is designed to survive that, it just has to be correct now.

### The golden-set refusal, and why it has to happen at construction

**Reworked in review.** The first version left calibration's "no golden set" failure where it was,
in `collect_tasks`, and the plan claimed the endpoint "raises the honest error rather than
returning 200". It does not. Both eval endpoints return a `StreamingResponse` wrapping an async
generator, so `collect_tasks()` runs only after the 200 headers are on the wire: the observed
result is **status 200 with an empty body**, then a dead SSE stream. The web client's `onerror`
turns a bare SSE `Event` into a `KilnError` with no reason in it. Functional spec §9 requires a 4xx
naming the operation and the reason, and architecture §4.3 asserts the surviving failure surfaces
"as a 4xx" — neither held.

The mechanism predates this phase (the same raise fired the same way for a TaskRun-backed eval with
no golden set), but this phase is what newly routes EvalInput-backed evals into it, so it is fixed
here. Two changes:

- `EvalRunner.__init__` raises for `eval_config_eval` with no golden set, so **every** caller fails
  before it can start a response, not just this endpoint.
- `run_eval_config_eval` calls `require_golden_set_or_422(eval)` before constructing the runner,
  which is what makes it a 4xx rather than the fallback handler's 500. This mirrors
  `run_eval_config`, whose 422 is real for exactly the same reason — it resolves before building
  the response.

The message is shared by both raisers through `no_golden_set_message(eval)` in `eval_runner.py`, so
the 4xx a user sees and the `ValueError` a library caller sees say the same thing. It names the eval
and the reason, replacing `"Eval configs filter ID is required for eval runs of type
'eval_config_eval'"` — an internal field name with no eval id.

## Tests

`libs/core/kiln_ai/adapters/eval/test_eval_runner.py`.

**A resolved split is a snapshot, and the tests have to say so.** The runner's item set is now fixed
at construction, so the existing tests that construct a runner and *then* create task runs or narrow
`eval.splits["test"]` no longer describe anything. They are rebuilt around a module-level helper:

```python
def build_task_run_eval_runner(eval_configs, run_configs, *, split_name="test", **kwargs) -> EvalRunner:
    """A task_run_eval runner over the named split, resolved from disk as of now."""
```

which resolves via `resolve_split` and asserts the split exists. Tests that used to mutate a split
mid-test now build a second runner, which is what a caller would have to do.

Rewritten (mechanical — same assertions, runner built after the data):
`test_collect_tasks_filtering`, `test_collect_tasks_excludes_already_run_task_run_eval`,
`test_collect_tasks_multiple_run_configs`, `test_collect_tasks_empty_cases`,
`TestCollectTasksEvalInputTaskRunEval`'s four tests.

Rewritten (the behavior itself changed):

- `TestEvalRunnerV2Init` → `TestEvalRunnerSplitArgument`. `_source_mode` is gone; the class becomes
  the §4.2 validation pair `test_task_run_eval_requires_a_split` and
  `test_eval_config_eval_rejects_a_split`, plus
  `test_task_run_eval_accepts_an_eval_input_backed_split` and (from review)
  `test_rejects_a_split_resolved_from_a_different_eval`.
- `TestCollectTasksForEvalInput` → `TestCollectTasksEvalConfigEval`. Was "eval_config_eval on an
  EvalInput-backed eval collects EvalInputs"; is now §9.3's
  `test_collects_only_task_runs_on_an_eval_input_backed_eval` — the golden filter selects `TaskRun`s
  and no `EvalInput` appears, with `EvalInput`s present to be wrongly collected. The class also
  keeps `test_no_golden_filter_raises`, which is §4.3's "honest failure that remains": an
  EvalInput-backed eval with no golden set now raises "no golden set configured" instead of faking
  a successful calibration.
- `test_eval_input_eval_config_eval_clean_skip` — deleted with the branch it covered, replaced by
  `test_writes_no_skipped_runs_for_an_eval_input_backed_eval` (§9.3's second clause): run the whole
  runner over such an eval and assert `eval_config.runs()` is empty. A status assertion cannot catch
  this — the old behavior was a *successful* run.
- `test_type_not_available_skip_eval_input` and `test_multi_turn_eval_input_skipped` — both used an
  `EvalInput` + `eval_config_eval` job, which is now unexpressible. Re-typed to `task_run_eval` with
  a run config; they still cover the two skip writers that remain.
- `test_no_golden_filter_raises` → `test_no_golden_set_raises_at_construction`, asserting the raise
  happens at construction and that the message names the eval. Its docstring carries the
  StreamingResponse reason, because the "raises at construction" half looks like a stylistic
  preference until you know why it is load-bearing.

New — `TestCollectTasksOverArbitrarySplits`:

- `test_eval_input_backed_split_collects_exactly_the_matching_inputs` — asserts **which** items, per
  §9.3. Two `EvalInput`s, a tag filter selecting one.
- `test_a_non_test_split_is_collected_the_same_way` — a TaskRun-backed `val` split, built with
  `split_name="val"`, collects the val items and not the test ones. Nothing about the runner should
  name "test" any more.
- `test_dedupe_keys_on_the_item_source_not_the_bare_id` — an `EvalInput` and a `TaskRun` sharing an
  id, an existing `EvalRun` for the `TaskRun`, and a run over the EvalInput-backed split. The
  `EvalInput` still gets a job. This is the §3.1 collision the `ItemKey` exists for; a bare-id
  dedupe passes every other test in this file.
- `test_overlapping_splits_reuse_already_scored_items` — §9.3's cache clause. An item in both `test`
  and `val` scored under one split is skipped when the other split is run, because dedupe keys on
  the item, not the split.

New — module level, one from the sweep and one from review (see below):

- `test_collect_tasks_ignores_runs_from_run_configs_not_being_evaluated`.
- `test_collect_tasks_ignores_calibration_runs_when_a_run_config_has_no_id` — a `TaskRunConfig` with
  `id=None`, a calibration record on the eval config, and an unscored item that must still get a
  job. Pathological-looking, but it is precisely the state that makes `None` a live dedupe key, and
  it is what turns the restored `is not None` from an untestable belt-and-braces line into a
  covered one.

`app/desktop/studio_server/test_eval_api.py`:

- `TestResolvedSplitOr422` — the helper's two outcomes, unit-tested directly rather than through
  the endpoint. **Written this way deliberately**: the plan first called for
  `test_run_eval_config_422s_when_the_eval_has_no_test_split`, and building the fixture proved it
  couldn't exist — `validate_splits` rejects an eval with no test split at construction *and* at
  load, so `eval_from_id` can never hand this endpoint one. A test that has to corrupt a model
  after construction to reach a branch is testing the branch's unreachability, not its behavior.
  The 422 is real for phase 6, whose endpoints take a caller-supplied split name (`train` on an
  eval that has none), and that is the case asserted.
- `test_run_eval_config` gains an assertion on the `split` handed to the runner — the endpoint
  patches `EvalRunner` wholesale, so without it the endpoint could pass any split and pass.
- `test_run_eval_config_eval_422s_without_a_golden_set` (from review) — the calibration refusal,
  asserted on **status and body**. Status alone would not discriminate: the broken version returns
  200, but so would a refusal that arrives with the wrong message, and §9's requirement is that the
  reason reaches the user.

`app/desktop/studio_server/jobs/workers/test_eval.py`:

- `test_build_eval_runner_passes_the_evals_resolved_test_split` and
  `..._resolves_an_eval_input_backed_test_split` — same substitution, same reason: the worker's
  `raise` on an absent test split is unreachable for the same `validate_splits` reason, so what is
  tested is what the runner actually receives, including the EvalInput-backed case that used to
  reach it as an empty TaskRun filter. (`compute_state` still refuses that eval — phase 5's.)

### Mutation sweep

`specs/projects/eval_splits_v1_v2/phase4_mutation_sweep.py`, the phase 2/3 harness with one
addition: a mutation may apply several edits at once. See the deletion entry below for why.

Mutations cover: all four constructor guards; `collect_tasks`'s dispatch and the golden filter;
`self.split.items` being replaced by `task.runs()`; the dedupe key in five failure shapes (bare id
instead of `ItemKey`, source hardcoded to `task_run`, dropped, crossing run configs, admitting other
run configs') plus the `is not None` half on its own; the split-to-eval binding and both branches of
`resolve_split` recording it; the golden-set refusal in both places it now lives; the run endpoint
resolving the wrong split and `resolved_split_or_422` degrading to an empty split instead of a 422;
and the worker building its runner over an empty split.

**The deleted `EvalInput`/`eval_config_eval` branch needs two edits, not one.** Re-inserting it
alone mutates unreachable code — nothing routes an `EvalInput` to calibration any more — so it
could not be killed by any test, and listing it as a single-edit mutation would have been a
mutation that passes vacuously. The entry restores the mis-routing *and* the branch together, which
is exactly the pair architecture §4.3 claims is gone, and is killed by
`test_writes_no_skipped_runs_for_an_eval_input_backed_eval`.

**20 mutations, all killed** (14 before review, 6 added with the review fixes). *Rebuild note: one
of the 20 — "worker: builds the runner over an empty split" — targeted `jobs/workers/eval.py`, which
does not exist on `scosman/evals_v2`. It is removed, with the reason recorded in
`phase4_mutation_sweep.py`'s docstring, so a re-run reports **19/19 killed** rather than a
PATTERN-MISS that reads as a regression.* One survived the
first run and was fixed rather than explained away: *dedupe: includes runs from other run configs* —
dropping the `task_run_config_id in already_run` membership test. Every dedupe test used only run
configs the runner was given, so nothing covered the common real case: an eval config accumulates
`EvalRun`s for every run config ever compared, and most of what `collect_tasks` reads belongs to run
configs this runner was not handed. Fixed with
`test_collect_tasks_ignores_runs_from_run_configs_not_being_evaluated`.

Phase 3's sweep is re-run against this tree: **23/23 still killed.**

Phase 2's sweep had two entries whose target lines this phase deleted — `runner: source mode never
eval_input` and `runner: task_run_eval ignores the split's filter` — which reported `PATTERN-MISS`
rather than `killed`. They are replaced in `phase2_mutation_sweep.py` by a comment saying so and
pointing at this phase's equivalents, so a re-run is **30/30 killed** instead of two false alarms in
a committed artifact. `phase_2.md`'s own "all 32 killed" claim now carries a note saying the same
thing, since that is where a reader meets the number. *(On the evals_v2 rebuild two further entries
go for the same reason, so phase 2's sweep holds 28 and re-runs **28/28**.)*

### Check status

`uv run ./checks.sh --agent-mode` reports two failures, both pre-existing and both recorded by
phase 3 against the clean phase-2 tree:

- **openapi schema** — `check_schema.sh` imports `desktop_server`, which imports `tkinter`, which
  isn't installed in this container. This phase changes no request or response model, adds no
  parameter and touches no endpoint signature, so `api_schema.d.ts` needs no regeneration.
- **python tests** — `7276 passed, 0 failed`, plus five collection errors from the same missing
  `tkinter` (`test_desktop.py`, `test_server.py`, `test_import_api.py`,
  `test_start_background_syncs.py`, `git_sync/test_sse_invariants.py`).

Everything else — `ruff check`, `ruff format`, `ty check`, and all five web checks — passes.

## Judgment calls made during implementation

Recorded for disagreement; not derived from `architecture.md`.

1. **The runner takes the item's source from `self.split.source` rather than `isinstance`.** Both
   work today. The split is the authority on what its items are, and an `isinstance` ladder would be
   a second place that has to agree with `resolve_split`.
2. **`resolved_split_or_422` lands in `eval_api.py` now**, one phase before the endpoints that
   motivate it. The alternative was an inline `if ... raise HTTPException` in `run_eval_config` that
   phase 6 would immediately refactor.
3. **The job worker's resolution stays inline in `_build_eval_runner`.** Architecture §5.1 specifies
   a `_resolve_split` method shared with the progress universe; writing that now would be phase 5's
   design with phase 5's second caller missing, and `compute_state` still reads
   `eval_set_filter_id`. Doing half of it would look finished.
4. **The runner still raises on `self.split is None` inside `collect_tasks_for_task_run_eval`,**
   after `__init__` has already guaranteed it isn't — and the same for `self.golden_filter_id` in
   `collect_tasks`. Both methods are public and both attributes are `| None`, so these are what make
   the bodies type-check without a cast. Replacing them with `assert` would be the same line with
   less information in the failure.
5. **The golden-set condition is stated in two places** — `EvalRunner.__init__` and
   `require_golden_set_or_422`. Same shape as `split`: the library raises, the API layer maps it to
   a status code before a response exists. They cannot drift on wording, because both go through
   `no_golden_set_message`.

## Known limitations, for phase 5 or 6

Three things this phase deliberately leaves standing. None is a regression; each is recorded so it
is found by reading rather than rediscovered.

### An SSE refusal is invisible to the web UI

The golden-set 422 above, and `resolved_split_or_422`'s 422 on the run endpoint, are real for the
HTTP contract, for the tests, and for any client that reads the response. They are **not** yet
visible to the app: `run_eval.svelte:88` opens these endpoints with a browser `EventSource`, which
cannot read the status or body of a non-200 response — it fires `onerror` with a bare `Event`, and
`createKilnError` falls through to `"Unknown error"`. So the user's screen is unchanged before and
after this fix.

The fix still earns its place — functional spec §9's "4xx, naming operation and reason" is now true
of the API, where it wasn't, and a 200-with-empty-body is a worse contract for every consumer — but
the last hop needs the client to stop using `EventSource` for these endpoints (fetch + a streaming
reader, or a non-streaming start/poll split). That is web-UI work, which is phase 6's. Both
docstrings claim the contract rather than the screen, so the code doesn't overstate it either.

### Calibration dedupe ignores what a run was *for*

`collect_tasks_for_eval_config_eval` builds its `already_run` set from `run.dataset_id` over **every**
run on the eval config, including `task_run_eval` runs. So a `TaskRun` that sits in both the golden
set and a split, and has been scored for some run config, is treated as already-calibrated and
silently skipped — no calibration record is ever written for it.

**Pre-existing and byte-identical to `HEAD`**, so this phase does not touch it. But it is the same
silently-short-run class §4.2 exists to remove, and the sibling path's dedupe now has a comment
explaining why the run-config scoping there is load-bearing — this is that reasoning's other half,
missing. The fix is the same shape: filter on `run.eval_config_eval` (or `task_run_config_id is
None`) before adding to the set. Left alone here because it is out of scope and its own test surface;
whichever of phases 5 and 6 next edits this method should take it.

### `EvalJob` does not express which item types each run type can carry

`item: TaskRun | EvalInput`
and `type: Literal["task_run_eval", "eval_config_eval"]` are independent fields, so
`EvalJob(item=some_eval_input, type="eval_config_eval")` still type-checks — the combination
architecture §4.3 is about. This phase makes it *unreachable* (nothing constructs it: calibration
collects from the golden filter, which is `DatasetFilterId`-typed) but not *unrepresentable*, and
`_run_v2_job` would take the `EvalInput` branch and write a record with `eval_config_eval=False` if
it ever were constructed.

Raised in review and deliberately not fixed here: splitting `EvalJob` into two dataclasses or
parametrising it would touch every construction and every `isinstance` in `run_job`, for a state
this phase already removed the only route to. Recorded so whichever of phases 5 and 6 next edits
`run_job` can take it as part of work already in that file, rather than as a standalone refactor.

## Deliberately not done

- **`EvalJobParams.split` and the `jobs/api.py` pre-resolution** (architecture §5). Phase 5's, and
  the worker's inline `resolve_split("test")` here is written to be replaced by it.
- **`compute_state`'s `eval_set_filter_id` read.** Still refuses an EvalInput-backed eval, so such
  an eval reaches the runner correctly but the job still fails at the baseline step. Phase 5 is
  where the two resolutions become one; splitting the fix would have meant writing §5.1's
  `_resolve_split` with only one of its two callers.
- **The API endpoints' `split` parameters and the summary/progress readers** (architecture §6).
  Phase 6's. `resolved_split_or_422` is here because this phase needed it, not as a down payment on
  that work.
