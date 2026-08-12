---
status: draft
---

# Functional Spec: Split eval traces from eval scores

Decisions D1–D21 in [`research.md`](research.md) §5 are the inputs to this spec. Where a
behavior traces to a decision, it is cited.

## 1. Problem and goals

`EvalRun` currently stores both the **trace** (what the model produced) and the
**scores** (what a judge said about it), as a child of a single `EvalConfig`. Because
the "already run" dedupe key includes `eval_config.id`, adding a judge to an existing
eval re-generates every output from scratch — even though scoring is free for 7 of the
8 V2 eval types.

**Goals**

1. Adding a judge to an existing eval reuses existing traces and only re-scores.
2. A trace survives a judge failure. Generation is persisted the moment it completes;
   a later scoring failure never destroys it.
3. Judge comparison becomes *paired* — two judges score the same generation, so the
   delta is attributable to the judge rather than to generation noise.

**Non-goal:** changing what any eval measures. Scores produced for a given
(item, run config, eval config) are unchanged.

## 2. The shape

Eval traces are **TaskRuns** (D12). There is no new trace entity.

```
Task
├── runs/                     TaskRun — dataset corpus AND eval-generated traces
├── eval_inputs/              EvalInput (unchanged)
└── evals/
    └── {eval}/
        └── configs/
            └── {config}/
                └── runs/     EvalRun — now purely a score record (D15)
```

`TaskRun` already carries everything a trace needs: `trace`, `output`, and the run
config both as `output.source.run_config_id` and as frozen
`output.source.run_config` properties. It additionally gives eval traces `output.rating`
(human ratings), `feedback` children, and `repaired_output` for free.

An `EvalRun` is *"a run of the eval over one item, producing scores."* The trace is a
TaskRun; the EvalRun is the eval being run.

### 2.1 Reuse key

A trace is identified by **`(source_type, source_id, task_run_config_id)`** (D9) —
no hash, no fingerprint. This is the invariant `TaskRunConfig` already asserts:
*"Running the same RunConfig with the same input should make identical calls to the
model."*

`source_type` is required because ids are only unique within a store — a `TaskRun` and
an `EvalInput` id can collide (`eval_splits.ItemKey`).

## 3. Data model

### 3.1 `TaskRun` — new field

```python
class EvalItemSource(BaseModel):
    """The eval *dataset item* this run was generated for.

    Not the run config — that already lives on this TaskRun at
    `output.source.run_config_id`.
    """
    source_type: Literal["eval_input", "task_run"]
    source_id: ID_TYPE

class TaskRun(...):
    eval_source: EvalItemSource | None = None
```

The two source types are the two kinds of dataset item a split can be backed by:

| `source_type` | `source_id` points at | When |
|---|---|---|
| `"eval_input"` | `EvalInput.id` | V2 EvalInput-backed split |
| `"task_run"` | `TaskRun.id` — the dataset item | V1 TaskRun-backed split |

So a legacy-sourced eval trace is a TaskRun whose `eval_source` points at *another*
TaskRun: the generated trace pointing back at the dataset item it was generated from.
The two are always distinct records.

This mirrors the splits branch's `ItemKey = Tuple[ItemSource, ID_TYPE]` exactly — same
two source types, same meaning.

- **Presence of `eval_source` is the eval-generated flag.** No separate boolean —
  an eval-generated run always has a source item, and an ordinary dataset run never
  does. The two cannot disagree.
- It must be convertible to the splits branch's `ItemKey` so the runner and
  `resolve_split` speak one vocabulary.
- **It deliberately does not name an Eval.** Traces are eval-independent; that is what
  makes them reusable across evals (D1, D12).
- All other TaskRun fields and validators are unchanged.

### 3.2 `EvalRun` — one new field, five deprecated

New:

```python
scored_run_id: ID_TYPE | None = None   # the TaskRun this score was computed over
```

Retained and meaningful:

| Field | Role |
|---|---|
| parent `EvalConfig` | which judge produced this score |
| `scores` | the scores |
| `task_run_config_id` | denormalized run config, for join-free aggregation |
| `dataset_id` / `eval_input_id` | the dataset item — **this is the `ItemKey`** |
| `intermediate_outputs` | judge thinking |
| `skipped_reason` / `skipped_detail` | scoring skips |
| `reference_data` | what the scorer actually saw |
| `eval_config_eval` | unchanged; shipped V1 field (D18) |

**Deprecated** — kept declared and loadable forever, never set on new records (D15):
`input`, `output`, `task_run_trace`, `task_run_usage`, `reference_answer`.
`input` changes from required to optional.

Nothing is deleted and no existing file is rewritten.

### 3.3 `EvalRun` record states

Exactly one applies. Enforced by validator (D17).

| State | Discriminator | `scored_run_id` | `scores` | `input` + trace fields |
|---|---|---|---|---|
| **Pointer** (new, scored) | `scored_run_id` set, no skip | required | non-empty | **must be None** |
| **Skipped** | `skipped_reason` set | optional — set if the trace existed, None if skipped before generation | empty | **must be None** |
| **Legacy inline** | `scored_run_id` None, no skip | None | non-empty | `input` **required**, trace fields allowed |

The *forbidding* half of the pointer rule is the one that earns its keep: a pointer-mode
record must never carry a stale second copy of what it scored.

`validate_scores` is unchanged — non-empty scores are still required unless skipped.
There is no "EvalRun with no scores" state, because "generated but not yet scored" is
represented as *a TaskRun with no EvalRun pointing at it*.

### 3.4 Accessor changes

```python
Task.runs(readonly=False,
          include_intermediate_runs=False,
          include_eval_generated=False)     # NEW
```

**Eval-generated runs are excluded by default** (D12), in the datamodel and therefore in
every API and UI surface above it. This mirrors the existing
`include_intermediate_runs` pattern on the same method.

Default-exclude rather than an opt-out filter is deliberate: forgetting to handle this
then fails *visibly* (missing data) instead of *silently* (contaminated fine-tune sets,
eval outputs leaking into few-shot prompts).

Only the eval runner passes `include_eval_generated=True`.

## 4. Runner behavior

### 4.1 Per-job flow

For each `(item, run_config, eval_config)` job:

1. **Trace lookup** — find a TaskRun with `eval_source == (source_type, source_id)` and
   `output.source.run_config_id == task_run_config_id`.
   - **Hit:** reuse it. No generation.
   - **Miss:** generate, then **persist the TaskRun immediately**, before scoring.
2. **Score lookup** — find an EvalRun under this `EvalConfig` with
   `scored_run_id == <that TaskRun>`.
   - **Hit:** nothing to do.
   - **Miss:** score, persist the EvalRun.

### 4.2 The trace lookup must be live

The lookup in step 1 is evaluated **at job-execution time**, not precomputed during
`collect_tasks()`.

This is a deliberate departure from the existing `already_run` pattern, which builds its
set up front. A precomputed set cannot see a trace persisted earlier in the *same* run,
which would cause both concurrent duplicate generation and regeneration on retry.

### 4.3 Retry

No change to the retry mechanism. `AsyncJobRunner` continues to retry the whole
`run_job` on `RetryableError`. Because the trace lookup is live, a retry after a scoring
failure finds the persisted TaskRun, skips generation, and re-scores only. The idempotent
lookup *is* the phase-scoping.

### 4.4 Duplicate traces

More than one TaskRun may match a trace key — sync means uniqueness can never be
guaranteed (two people run, then sync). The system already tolerates this. **First match
wins** (D8). Nothing intentionally creates a second.

### 4.5 Calibration

In calibration (`eval_config_eval=True`), no generation happens: the scored TaskRun *is*
the human-rated golden dataset item. `scored_run_id` points straight at it, and no
eval-generated TaskRun is created — so golden items are never flagged, never excluded,
and never delete-protected.

### 4.6 Skips

| Condition | Record |
|---|---|
| Cannot generate for this item (e.g. `incompatible_input_shape`) | EvalRun, `skipped_reason` set, no `scored_run_id` |
| Trace exists but this judge cannot score it (`missing_reference_key`, `extraction_failed`, `missing_trace`, `code_eval_not_trusted`, `type_not_available`) | EvalRun, `skipped_reason` set, `scored_run_id` set |
| Generation itself failed | **Nothing persisted** (D14) — `TaskRun.output` is required, so a failed generation has no representation. The item reads as incomplete and retries on the next run, matching today's "absence = not-yet-run" |

## 5. Read paths

### 5.1 Aggregation is unchanged

`compute_score_summary`, the eval-config compare summary, and the per-run-config summary
all read `eval_config.runs()` and bucket by `task_run_config_id` and item key. Every
field they touch stays on `EvalRun`. **This project changes none of that code.**

Completeness is still `EvalRun` presence per `(eval_config, run_config, item)`: an
unscored trace is incomplete, which is correct.

### 5.2 The run-results view joins

`get_eval_run_results` returns `List[EvalRun]` with `input`/`output` inline, and the
frontend reads them. In pointer mode those fields are None.

The endpoint returns a **joined view model** — EvalRun fields plus `input`, `output` and
trace pulled from the referenced TaskRun — so the frontend contract is preserved. Content
is **not** denormalized onto the EvalRun; a stored copy would go stale.

`api_schema.d.ts` regenerates.

**Display rule:** show `TaskRun.output`, never `repaired_output`, when displaying what a
score was computed over. Repair can happen after scoring.

### 5.3 Dangling references degrade gracefully

If `scored_run_id` points at a missing TaskRun, the score still displays with its value
and aggregation still counts it. Only the trace drill-through is unavailable. Do not
cascade-delete scores and do not raise on a dangling id.

## 6. Delete protection

Deleting a TaskRun with `eval_source` set is **refused**, with: *"This is needed for an
eval."* (D16)

This needs no reverse reference scan — the flag on the TaskRun is sufficient, and it
holds whether or not an EvalRun currently points at the run.

This is the only new user-facing surface in the project.

## 7. Legacy coexistence

- **V1 EvalRuns** (under `g_eval` / `llm_as_judge` configs) load and render exactly as
  today, in legacy-inline mode. They are never migrated and never rewritten.
- **EvalConfigs are immutable by construction** (D21) — `eval_api` exposes only
  create/get/list, with no PATCH or DELETE. So a score can never go stale relative to its
  config. Combined with the reuse key, every EvalRun is described by three immutable
  things: the item, the run config, and the eval config.
- No V1 file format changes. No field is removed from any schema.

## 8. Migration (internal V2 data only)

V2 has not shipped, but internal projects carry V2 eval data. A migration script is a
required deliverable, run as the final phase. A lazy load-time fold is not available,
because records move between directories.

For each V2 `EvalRun` (parent `EvalConfig.config_type == "v2"`):

1. **Group** by `(item key, task_run_config_id)` *first*. Several EvalRuns from different
   eval configs describe the same generation; they must collapse to **one** TaskRun.
   Collapsing is the point of the project — a migration that creates one TaskRun per
   EvalRun would preserve the duplication it exists to remove.
2. For each group, create one TaskRun from the inline trace fields (`input`, `output`,
   `task_run_trace`, `task_run_usage`), setting `eval_source` from the
   `dataset_id`/`eval_input_id` pair and the run config from `task_run_config_id`.
3. Rewrite each EvalRun in the group to pointer mode: set `scored_run_id`, clear the
   inline fields.
4. **Calibration EvalRuns** (`eval_config_eval=True`) already reference a real TaskRun
   via `dataset_id` — set `scored_run_id = dataset_id` and create nothing.
5. **Skipped EvalRuns with no trace** — clear inline fields, leave `scored_run_id` unset.
6. **V1 EvalRuns are skipped entirely.**

The script is idempotent: an EvalRun already in pointer mode is left alone.

## 9. Vocabulary (D19)

Adopt in new code, comments, docs and UI — the stored `eval_config_eval` field keeps its
name:

| Concept | Term |
|---|---|
| Evaluating a task run config: generate, then judge. *"Is model A better than B?"* | **scoring** |
| Evaluating an eval config: judge human-rated items and correlate. *"Is my judge any good?"* | **calibration** |

"Trace" means the TaskRun. "Score" means the EvalRun.

## 10. Out of scope

| Item | Why |
|---|---|
| "Score existing runs with this judge" action | The existing Run button already does it once traces are reusable |
| Reuse visibility / progress counts | Fast is fine; a quick run does not read as a bug |
| Force-fresh generation | Scope creep, and not a regression — there is no force-fresh today either |
| Stale-on-config-edit handling | Not a thing; EvalConfigs are immutable (D21) |
| Cross-eval reuse as a *feature* | Falls out of task-level trace storage. No pointer-EvalInput type (D2) |
| Metrics / observational evals | Deferred as a read-side concept, scoped by a split ref (D3) |
| EvalInput-backed golden sets | Human ratings live on `TaskRun.output.rating`; golden stays TaskRun-only (D11) |
| Removing `eval_config_eval` | Provably redundant, but shipped V1 — unrelated churn (D18) |
| Moving `multi_turn_drive_config` onto `EvalInput` | Owned by the eb-v2 branch; a prerequisite for multi-turn cross-eval reuse, not work here (D5) |
| Pre-existing generation-drift holes | Accepted: unfrozen dynamic prompts, tools-by-id, `task.instruction` (D10) |

## 11. Dependencies

- **`claude/eval-splits-evals-v2`** — this project builds on it. `Eval.splits`,
  `resolve_split()`, `ItemKey`, and `eval_run_item_key()` are reused, not reimplemented.
  Membership always resolves through `resolve_split()`.
- **eb-v2 / multi-turn branch** — `multi_turn_drive_config` moves onto `EvalInput`
  before ship. Until it does, multi-turn traces must not be reused across evals. Note:
  `eb_v2_splits_alignment` §9 currently leans toward keeping it eval-level; the two
  projects need to agree.

## 12. Constraints

- **Back-compat is absolute.** Every V1 record on disk loads and renders unchanged. No
  field is removed from any schema.
- **Directory scale.** `runs/` now holds the dataset corpus and every eval trace.
  Benchmarked separately and accepted.
- **No new dependencies.**
- **Two saves per fresh job** instead of one, inside the git-sync `SaveContext`.

## 13. Open — confirm or cut

One discretionary addition, called out rather than assumed:

**Judge usage on `EvalRun`.** LLM-judge token cost is currently recorded nowhere —
`task_run_usage` is the *task's* usage, not the judge's. Splitting the records is the
natural moment to add a `usage: Usage | None` for the scoring call. Small, real user
value, cheaper now than later. Cut it if scope discipline wins.
