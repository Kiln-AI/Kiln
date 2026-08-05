---
status: draft
---

# Functional Spec: Train/val/test splits across V1 and V2 eval datasets

## 1. What this is

An eval carries three named dataset **splits** — `train`, `val`, `test` — plus a separate
`golden` set. Today only the TaskRun data source has all three, and only the test split can be
backed by `EvalInput`. This project makes **every split independently backable by either data
source**, addressable through one API surface, so no caller branches on where an eval's items
live.

This unblocks the EvalInput-based projects downstream. It ships before them; they align to the
model it lands, not the other way round.

### The core model (decided)

- There are three splits: **test**, **train**, **val**.
- Each split is backed by exactly **one** data source — `TaskRun` or `EvalInput`. Never both,
  never neither-when-required.
- An eval **may mix** backings across its splits. An eval with a TaskRun test and train set may
  gain an `EvalInput`-backed val set. This is a requirement, not an accident: it's how someone
  adds a val set to an existing eval using the new tooling.
- **Golden is not a split.** It stays exactly as it is — `eval_configs_filter_id`, TaskRun-only,
  and expected to be unpopulated in V2 as the product backs away from human-alignment scoring.
  It is not touched by this project.

### The design goal

The splits × sources matrix is 3 × 2. Handled naively it produces a source branch at every call
site, and every new reader adds another. The whole point of this project is that it doesn't: the
model and its accessors resolve "which items are in split X" and "which item did this EvalRun
score" once, and callers stay source-agnostic. Chasing `if eval_set_filter_id is not None: ...
elif eval_input_filter_id is not None: ...` around the codebase is the failure mode this exists
to prevent.

---

## 2. Terms

| Term | Meaning |
|---|---|
| **Split** | A named subset of an eval's items: `test`, `train`, or `val`. |
| **Backing / source** | Which store a split's items come from: `TaskRun` (V1) or `EvalInput` (V2). |
| **Filter id** | The stored selector for a split. `DatasetFilterId` for TaskRun backing, `EvalInputFilterId` for EvalInput backing. Not interchangeable — see §7. |
| **Golden set** | `eval_configs_filter_id`. Human-rated TaskRuns used to score *judges*, not models. Out of scope. |
| **Judge axis (V1/V2)** | `EvalConfig.config_type`. Independent of the data-source axis; untouched here. |

"Eval set" in existing field names and copy means the **test** split. The name is legacy.

---

## 3. Split semantics

### 3.1 Which splits exist

- **test** is required. Every eval has one, with one backing.
- **train** and **val** are optional. An eval may have neither, either, or both.
- Splits are disjoint by convention (tagging discipline), not enforced. Nothing in this project
  validates or requires disjointness.

### 3.2 Default behavior for existing evals

TaskRun-backed evals keep the lazy migration they have today: an eval loaded without a train or
val filter gets `tag::train_{name_slug}` / `tag::val_{name_slug}`, TaskRun-backed. These resolve
against the task's runs and are commonly empty. That behavior is correct and stays.

The migration mints **TaskRun-backed** splits. It must not mint a split for a source that
doesn't apply, and it must not overwrite a split that already exists with either backing.

### 3.3 Naming

`eval_input_filter_id` is renamed so it names the split it defines rather than the source. A
temporary load-time shim carries the old value across, marked with a `TODO` to be removed before
this ships — no public projects contain the key, only internal ones.

The corresponding V1 field (`eval_set_filter_id`) is in shipped public projects and cannot be
renamed casually; whether it survives, and in what form, is part of the storage-shape decision
in §10.

---

## 4. Running an eval against a split

### 4.1 Entry point

`POST /api/jobs/evals/run` takes an optional `split` parameter: `"train" | "val" | "test" | null`.

| `split` | Behavior |
|---|---|
| `null` (omitted) | Runs the eval's test split. **Byte-identical to today's behavior** — see §8. |
| `"test"` | Same item set as omitting the param. |
| `"train"` / `"val"` | Runs that split, if the eval has one. |

The split's backing determines which store is iterated. A caller does not know or care: the same
request shape runs a TaskRun-backed val set and an EvalInput-backed one.

### 4.2 The split must actually reach the runner

The requested split replaces the eval's default item selection **for both backings**. A split
request that is silently ignored — succeeding with a 200 while running the full test set — is
the single worst outcome in this project and must be impossible by construction, not by
convention. The runner must not have a path where an override is accepted and then dropped.

### 4.3 Progress and resumption

A running job's progress total is computed against **the split's** item universe, in the split's
own store. A partial run of one split, resumed, must not short-circuit against a different
split's or a different store's item count.

Already-scored items are reused at item granularity, so running overlapping splits does not
re-score shared items. This holds per-source: an item's identity for caching is (source, item
id), never the id alone.

### 4.4 Unsupported combinations

`split` is not offered on the SSE run endpoints (`run_comparison`, `run_calibration`). The UI
runs the test split only; train and val are deliberately not surfaced there — they exist for
auto-research and programmatic callers, which use the jobs API.

---

## 5. Reading results by split

`GET .../eval_config/{eval_config_id}/run_config/{run_config_id}/results` takes an optional
`split` query parameter with the same values.

| `split` | Behavior |
|---|---|
| `null` (omitted) | All results for the run config. Today's behavior, unchanged. |
| set | Only results whose scored item is a member of that split. |

Filtering happens at query time against stored `EvalRun`s. There is no `EvalRun` schema change,
so it works retroactively on results recorded before this project.

**Membership must be source-aware.** An `EvalRun` records either `dataset_id` (TaskRun-backed)
or `eval_input_id` (EvalInput-backed), never both. Comparing a run's item id against a split's
id set is only meaningful when both are from the same store. An `EvalRun` from one source can
never be a member of a split backed by the other, regardless of id values.

This is not merely defensive. Filter ids share the `tag::` grammar across both stores, so
`tag::val_x` is a valid selector in either — the id alone does not identify which store it
addresses. Any cache, lookup, or comparison keyed on a filter id or an item id must carry the
source alongside it.

---

## 6. Endpoint behavior by data source

### 6.1 Things that work for both backings

Any surface whose question is *"how many items are in this split"* or *"which item did this
EvalRun score"* works for both backings, because both resolve through the shared accessor. That
covers:

- `GET .../evals/{eval_id}/progress` — test-split size, train size, val size
- `GET .../eval_config/{eval_config_id}/score_summary`
- `GET .../eval_results_summary`
- `GET .../run_config/{run_config_id}/results` (with or without `split`)
- run-config comparison / the compare page

> **Revision flagged for sign-off.** An earlier round settled on "4xx for now" for these
> endpoints when an eval is EvalInput-backed, deferring real support to the downstream branch.
> That call was made against the current code, where each endpoint hard-codes the TaskRun store.
> Once the accessor exists, supporting both backings on these endpoints is *less* code than
> refusing — the refusal needs a guard the accessor otherwise makes unnecessary. Their existing
> 400s are triggered by the **test split being EvalInput-backed**, which has nothing to do with
> golden; golden counts simply come out zero when `eval_configs_filter_id` is unset, which is the
> expected V2 state anyway. Recommendation: drop those guards rather than restate them. If you'd
> rather hold the line and 4xx here, say so and I'll spec the guards instead — but it is the more
> expensive option and it regresses behavior the downstream branch will want back.

### 6.2 Things that genuinely cannot work, and must fail loudly

**Judge evaluation over EvalInput items** (`eval_config_eval` mode, `run_calibration`). This
scores a judge by re-using a dataset item's *stored output* without re-running the task, and
compares it against a *human rating*. `EvalInput` has neither an output nor rating storage. It
is not a gap to be filled later by better plumbing; the data isn't there.

Required behavior: refuse up front, with a message that names the eval, the operation, and the
reason. Specifically it must **not** proceed to manufacture a persisted `EvalRun` per item marked
skipped — that turns an unsupported operation into durable junk records that every downstream
reader then has to reason about. The refusal happens before any item is processed or written.

**Golden set over EvalInput.** `eval_configs_filter_id` remains TaskRun-typed and is never
populated from EvalInput items. Not an error condition — just a thing that doesn't exist. No new
validator restricts golden based on an eval's split backings.

### 6.3 Prompt optimization

Prompt optimization is the only consumer of the train split outside evals. It packages the
project and hands it to the closed-source remote Kiln service, which resolves the train filter
against the project zip's `runs/` directory. That zip does not contain `eval_inputs/`, and the
resolver is in another repo.

So: **prompt optimization supports TaskRun-backed train splits only.**

- Its "does this eval have a usable train set" check reports true only when the eval has a train
  split **and** that split is TaskRun-backed.
- Starting a job against an eval whose train split is EvalInput-backed fails with a 4xx naming
  the reason, rather than optimizing against an empty set.

Teaching the remote service EvalInput is a separate project in a separate repo. It is not
blocked by this one — this one just has to be honest about the boundary.

---

## 7. Filter id types

`DatasetFilterId` admits `all`, `high_rating`, `thinking_model`, `thinking_model_high_rated`,
`tag::<x>`, and `multi_filter::<...>`. `EvalInputFilterId` admits only `all` and `tag::<x>`,
because the others read TaskRun ratings and thinking data that `EvalInput` does not have.

A TaskRun-only filter form must never be storable on an EvalInput-backed split. Enforcement
should come from the model's shape wherever possible rather than a hand-maintained validator,
since a validator is another thing that can be forgotten when a fourth split or a third source
appears.

Conversely, a filter id string alone never identifies its source. `tag::val_x` is valid for both.
See §5.

---

## 8. Compatibility requirements

1. **The no-split path does not move.** Omitting `split` on either endpoint produces exactly
   today's behavior for TaskRun-backed evals: same items run, same results returned, same
   progress totals. The parameter is opt-in and existing callers are unaffected.
2. **Stored results stay readable.** No `EvalRun` schema change. Results recorded before this
   project filter correctly by split afterwards.
3. **Existing project files keep working.** TaskRun-backed evals in shipped public projects load,
   run, and save without user-visible change. A load/save round trip neither drops a field nor
   invents one.
4. **The internal-only rename is a throwaway.** The `eval_input_filter_id` shim exists to carry
   internal projects across and is removed before ship, tracked by a `TODO`.
5. Whether new-format files remain readable by **older Kiln builds** is an open constraint that
   feeds the storage decision — see §10.

---

## 9. Error behavior

Errors name the split, the eval, and the actual reason. In particular:

- A request for a split the eval does not have must not report a missing field that has never
  existed under that name. Diagnostics are written in terms the caller used (`train`, `val`,
  `test`), not internal field names.
- A bad split on a run request fails at request time, not as a background job that starts and
  then dies.
- Unsupported operations (§6.2) fail before any work is done or any record is written.

| Condition | Result |
|---|---|
| `split` names a split the eval doesn't have | 422, naming the split and the eval |
| `split` value isn't one of train/val/test | 422 from request validation |
| Eval or task not found | 404 |
| Judge evaluation requested over an EvalInput-backed set | 4xx, naming operation and reason; nothing written |
| Prompt optimization against an EvalInput-backed train split | 4xx, naming the reason |

---

## 10. Deferred to architecture

These are design decisions, not functional ones, and each deserves a real proposal rather than a
snap call:

1. **Storage shape on `Eval`.** How three splits × two backings are represented. The candidates
   range from flat per-(split, source) fields to a discriminated splits structure. The choice
   should be driven by which representation makes §7's type safety and §5's source-awareness
   structural rather than validator-enforced.
2. **File compatibility**, which is an *input* to (1), not a separate decision. `eval_set_filter_id`
   and `train_set_filter_id` exist in shipped public projects; whether the new shape reads legacy
   fields only, dual-writes during a deprecation window, or keeps them canonical materially
   changes what shapes are viable — including whether older Kiln builds can still open a migrated
   project, and whether they'd fail loudly or quietly misread it.
3. **The accessor surface.** What "resolve a split to its items" and "identify an EvalRun's item"
   look like as a single well-typed seam, such that adding a source or a split later touches one
   place. This is the anti-if-branch requirement from §1 made concrete.
4. **How the judge-evaluation refusal is implemented** (§6.2) — where the check lives so it can't
   be reached with items already partially processed.
5. **Lazy-migration behavior** for train/val across backings (§3.2): what runs, when, and what it
   must not overwrite.

## 11. Explicitly out of scope

- **Golden sets and judge/human alignment.** Unchanged, TaskRun-only, expected unpopulated in V2.
- **Data-creation paths.** Populating `EvalInput`s and tagging items into splits at creation time
  belongs to the incoming copilot project. Nothing here builds it, and nothing here is designed
  around a guess at what it will do.
- **EvalInput support in the remote prompt-optimization service** (§6.3) — different repo.
- **UI work** beyond adding the val count to eval progress. Train and val stay unsurfaced as run
  targets by design.
