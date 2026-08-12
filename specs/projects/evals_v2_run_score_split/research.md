---
status: draft
---

# Research: EvalRun / EvalScore split

Pre-spec research. Verifies the premise against the code, then challenges the
assumptions. No design committed here — this feeds the functional spec.

Code read: `libs/core/kiln_ai/datamodel/eval.py`,
`libs/core/kiln_ai/adapters/eval/eval_runner.py`,
`app/desktop/studio_server/eval_api.py`,
`libs/core/kiln_ai/datamodel/basemodel.py`, `datamodel/task.py`,
`specs/projects/evals_v2/components/{10_data_model,45_runner_architecture,90_open_risks}.md`.

---

## 1. Premise verification — the flaw is real

| Claim | Verdict | Evidence |
|---|---|---|
| `EvalRun` is a child of `EvalConfig` | Confirmed | `eval.py:819` — `EvalConfig(..., parent_of={"runs": EvalRun})`. Disk: `evals/{eval}/configs/{config}/runs/{run}/eval_run.kiln` |
| `EvalRun` conflates trace and score | Confirmed | Trace-side: `input`, `output`, `task_run_trace`, `task_run_usage`, `dataset_id`/`eval_input_id`, `task_run_config_id`. Score-side: `scores`, `intermediate_outputs` (judge thinking), part of `skipped_reason`/`skipped_detail` |
| A new judge forces full regeneration | Confirmed | The "already run" dedupe key includes `eval_config.id` (`eval_runner.py:165-196`, `236-262`). A new EvalConfig starts with an empty set, so every job re-executes `evaluator.run_task(...)` (`eval_runner.py:464`, `493`) |
| Scoring is often free | Confirmed | 7 of 8 V2 types are local compute (`exact_match`, `pattern_match`, `contains`, `set_check`, `tool_call_check`, `step_count_check`, `code_eval`). Only `llm_judge` costs money |

**The logic is sound.** The trace is a function of `(input, task_run_config)`. The
score is a function of `(trace, eval_config)`. Storing them in one record keyed on
`eval_config` makes the expensive half a captive of the cheap half.

---

## 2. Three arguments for the split the overview doesn't make

These strengthen the case and should shape scope.

### 2.1 It removes a statistical confound, not just cost

Today, two eval configs scoring the same run config score **different generations**.
"Judge A says 0.7, judge B says 0.6" conflates judge disagreement with generation
noise. With a shared trace, judge comparison becomes *paired* — the generation is
held constant and the delta is attributable to the judge. For a product whose core
loop is "is my judge any good?", this is arguably a bigger win than the token
savings.

### 2.2 It closes a hole V2 currently ships with

> **Amended — see §4c.** The original claim here (that this unblocks EvalInput-backed
> *golden sets*) was imprecise and is withdrawn. Golden sets stay TaskRun-only, because
> the blocker is human ratings, not stored output. What remains true is below.

Scoring an EvalInput-sourced item without re-running the task is **not possible today**
— it persists a skip: `"EvalInput source has no stored output; eval_config_eval over
EvalInput is deferred in V2.0"` (`eval_runner.py:444-462`). The reason is exactly the
flaw under discussion: there is no place to store an EvalInput's generated output
independent of a judge. The split removes that skip by making the output exist. Under
the split this stops being a *mode* at all — it is simply what happens when the trace
lookup hits.

### 2.3 The cost is about to get much worse

Multi-turn synthetic-user runs are skipped in V2.0
(`incompatible_input_shape`, `eval_runner.py:417-442`) but are coming. A synthetic
user conversation is orders of magnitude more expensive than a single generation.
Fixing the structure before that lands is much cheaper than after.

---

## 2.4 Second goal: persist the trace before scoring (added by scosman)

**Goal:** save the EvalRun as soon as generation completes. A failing judge must not
destroy the trace. Re-running finds the existing EvalRun and jumps straight to
judging — the same lookup that makes a new eval config fast.

**The failure mode is real and worse than "data lost".** `_run_v2_job` awaits
`run_task(...)`, then `evaluate(...)`, then writes a single EvalRun
(`eval_runner.py:464-490`, `492-522`). If `evaluate()` raises:

- Nothing is persisted — the generation is gone.
- `run_job` classifies the error and, if retryable (rate limit, 5xx, connection),
  raises `RetryableError` (`eval_runner.py:295-308`), and `AsyncJobRunner` retries
  **the whole job** up to `max_retries=2` (`async_job_runner.py:152-164`,
  `eval_runner.py:284`). So a rate-limited *judge* triggers up to two full
  *regenerations*.
- If not retryable, the job fails and the trace is lost outright.

So today one flaky judge call can cost three generations. This goal is a bug fix, not
just an optimization.

**It fits the same mechanism as the main split** — that's the point. Once EvalRun and
EvalScore are separate records, the runner's per-job flow becomes:

1. Look up an existing EvalRun for `(input, run_config)`. Reuse it if found.
2. Otherwise generate and **persist the EvalRun immediately**.
3. Look up an existing EvalScore for `(eval_run, eval_config)`. Skip if found.
4. Otherwise score and persist the EvalScore.

Steps 1 and 3 are the same two-lookup planner C4 already requires. "Trace saved but
not yet scored" is a natural, valid state under the split, and retry becomes a
step-4-only retry. This goal costs almost nothing *given* the split — but it is
impossible without it, since today `validate_scores` (`eval.py:772-796`) forbids
saving an EvalRun with no scores at all.

**Consequences to carry into the spec:**

- **Progress accounting flips to the score side.** `percent_complete` can no longer
  be derived from EvalRun presence — an unscored EvalRun is *incomplete*. Completion
  is `EvalScore` presence per `(eval_config, run_config, input)`. Consistent with C6
  and with C3's denormalization recommendation.
- **Retry granularity narrows.** `RetryableError` should retry only the failed phase.
  A retryable *generation* error retries step 2; a retryable *scoring* error retries
  step 4 against the already-persisted trace.
- **Two saves per fresh job instead of one**, inside the git-sync `SaveContext`
  (`eval_runner.py:355`, `468`). Cheap, but the write-lock interaction is worth a
  look given the `git_sync_write_locks` work.
- **Open question — failed generations.** If `run_task` itself fails, do we persist a
  terminal "generation failed" EvalRun, or leave it absent so it retries next run?
  `KilnRunError` already carries a partial trace (`eval_runner.py:554-564`), so
  persisting one is possible. Absent-means-retry is the simpler default and matches
  today's "DB-level absence = not-yet-run" convention; persisting gives users
  visibility into *why* an item never scored. This sharpens the "generation_failed"
  question raised in C6.
- **Reuse must be observable.** If a re-run silently skips generation, users need to
  see it (C11) — otherwise "why was that so fast?" reads as a bug.

---

## 3. Challenges to the proposal

### C1. Half the judge-iteration loop already reuses stored data

The `eval_config_eval` mode (judge calibration against human-rated golden TaskRuns)
**already does not re-run the task** — it scores `job.item.output.output` directly
(`eval_runner.py:523-551`). So the Copilot's judge-vs-human correlation loop is
already cheap for TaskRun-sourced golden sets.

The expensive regeneration is confined to the **`task_run_eval`** path: running the
eval set against run configs. That is where the win lands. This doesn't invalidate
the proposal — but it means the value story is "production eval runs and
EvalInput-sourced golden sets", not "judge iteration generally".

**Implication for scope:** the split must cover both modes uniformly, or we end up
with two mechanisms. Recommend modelling `eval_config_eval` as "an EvalRun whose
trace is a pointer to an existing TaskRun" so there is one scoring path.

### C2. "Under the Eval" is not obviously the right level — the trace doesn't depend on the Eval

The overview asks whether EvalRun should move under `Eval`. But a trace is a function
of `(EvalInput, TaskRunConfig)` — nothing in it references the Eval or its judges. If
EvalRun sits under `Eval`, two Evals over the same EvalInputs and run configs still
duplicate every expensive generation. Given C1/2.3 (synthetic users), that's the
exact duplication we're trying to kill.

| Option | Reuse scope | Cost |
|---|---|---|
| **A. EvalRun under `Eval`** | Within one eval | Simple; matches instinct; deleting an eval cleanly deletes its traces; progress/`percent_complete` stays a local question |
| **B. EvalRun under `Task`** (sibling of `eval_inputs/`) | Across all evals | Max reuse, but "which runs belong to this eval" becomes a query; eval deletion no longer cascades; needs an explicit membership/provenance notion |

Note that option B's entity is *"a run of a task run config over an EvalInput"* —
which is nearly `TaskRun`. Reusing `TaskRun` should be explicitly considered and
(probably) rejected: it would pollute the human-review dataset corpus, which has a
different lifecycle and different filters.

**Recommendation:** ship **A**, but keep `EvalRun` a *pure trace record* with no
eval-specific fields, so moving to B later is a relocation rather than a redesign.
This is a decision the spec must make explicitly.

### C2b. Cross-eval reuse — the four options aren't parallel, and two of them collapse

scosman raised cross-eval reuse with a concrete use case: a "tool calling error rate"
eval that reuses another eval's EvalRuns and just produces a new score. Use cases
today skew to **high-level metrics** (tokens used, turn count, tool call errors)
rather than LLM-as-judge. Four options were proposed: punt / pointer EvalInput /
move to task level / new Metrics concept.

Three code facts reframe the choice.

#### Fact 1 — most of "move to task level" is already built

| Premise of Option 3 | Actual state |
|---|---|
| "Move EvalInput up to task level" | **Already there.** `Task(parent_of={..., "eval_inputs": EvalInput})` (`task.py:137`). EvalInput has never been owned by an Eval |
| "Use tags to link to evals" | **Already the mechanism.** `EvalInputFilterId` accepts `tag::<name>` → `TagEvalInputFilter` matching `eval_input.tags` (`dataset_filters.py:205-257`). Evals never owned inputs; they select them |
| "Would need to remove SU config from eval and put it on eval input" | **Already on the EvalInput.** `MultiTurnSyntheticEvalInputData.synthetic_user_info` (`eval.py:519`). There is no eval-level synthetic-user config to move. (Multi-turn *execution* is still deferred — `eval_runner.py:417-442` — but the schema slot is on the right entity) |

So Option 3 does not mean "move EvalInput and EvalRun up and invent a tag link". It
means **move only EvalRun**. The complexity priced into that option is largely
already paid.

#### Fact 2 — that collapses the pointer option into it

The pointer EvalInput exists to express "this eval's input *is* that eval's input".
But `EvalInput.tags` is a list, and evals select by tag filter. Two evals share an
input by both selecting it: `tags: ["quality_eval", "tool_error_rate"]`.

Every pro listed for the pointer option is delivered by task-level EvalRun with zero
new concepts:

| Pointer-option pro | Delivered by task-level runs? |
|---|---|
| Full reuse of eval runs | Yes — reuse is just "the trace lookup found one" |
| Fixed set of eval inputs on the new eval → consistent score | Yes — that is exactly what the tag filter already is |
| EvalRun lives in one place for deletion | Yes, more so — owned by the Task, not by whichever eval happened to create it |
| Child eval keeps complete control over what it's judged on | Yes — it picks its own filter |

The pointer type is tag membership, re-implemented as a schema feature. Recommend
dropping it.

#### Fact 3 — the Metrics option is on a different axis, and the stated use case never generates

There are two independent questions here:

- **Storage:** where do traces live? (Eval vs Task)
- **Consumption:** how does a score get computed over a trace someone else generated?

The Metrics option is purely consumption. And the use case that motivates it —
tokens used, turn count, tool call error rate — is inherently **read-only**. You
would never want a "tool call error rate eval" to generate its own traces: it would
then be measuring a different population than the eval you actually care about, which
is worse than measuring nothing. So a metric reads what exists and never runs a task.

That means Metrics works regardless of where traces are stored. It is additive and
orthogonal to the storage decision, not a competing answer to it.

**Its stated con is fixable.** "Can't define exact dataset — a bunch of simple 1-turn
tasks might shift it." Scope a metric with an `EvalInputFilterId`, the same tag filter
evals already use. You get dataset control; you just *measure what's available within
scope* rather than generating to fill it. The con becomes "coverage may be partial",
which is honest and displayable (`n_used` already exists), not "population is
uncontrolled".

#### The argument for task-level that wasn't listed: orphaning

If a metric's scores live under Eval B while the traces live under Eval A, deleting
Eval A punches holes in Eval B's metric history. For a metric tracked over time (tool
call error rate across releases) that is a bad failure mode. Under task-level storage
it cannot happen — traces are owned by the Task and evals are lenses over them.

#### Pre-ship asymmetry

V2 hasn't shipped. Moving EvalRun to task level is free today (dev data only) and a
user-data migration later. Choosing Eval-level now and needing task-level later is
the expensive direction; choosing task-level now and never needing reuse costs a
bigger flat directory and an eval-deletion GC question. Asymmetric.

#### What task-level actually costs, given C3

If `EvalScore` lives under `EvalConfig` and denormalizes `eval_input_id` +
`task_run_config_id` (needed for dedupe anyway), then **every aggregate read path
never touches EvalRuns at all** — `compute_score_summary`, the compare view, and the
correlation endpoint each stay a single flat scan per config, exactly as today. Only
two consumers read EvalRuns: the job planner (`(eval_input_id, run_config_id) →
EvalRun`) and the single-item run-detail view.

Residual real costs:

- **One large flat `eval_runs/` directory.** 10 evals × 500 inputs × 4 run configs ≈
  20k records, scanned by the job planner on every "run eval". Precedent exists —
  `runs/` (TaskRun) already has this shape and `ModelCache` backs it — but this is
  the one genuine risk and deserves a benchmark spike before committing.
- **Eval deletion no longer GCs traces.** Policy needed: keep them (they're reusable)
  plus an explicit cleanup action.
- **Packaging.** `_ignore_eval_config_runs` (`package_project.py:904`) keys on the
  `configs/*/runs/` path and needs updating under any option.

#### Recommendation

1. **Store EvalRun at Task level** — sibling of `eval_inputs/`. Correct
   normalization, two-thirds already built, only option that can't orphan, free
   pre-ship. Gate on the directory-scan benchmark.
2. **Drop the pointer EvalInput option** — it re-implements tag membership.
3. **Punt Metrics as a feature, not as a shape.** Ship the split now; add metrics
   later as a read-side concept. Commit now only to the one thing that keeps it
   cheap: metrics are scoped by an `EvalInputFilterId`.

The strongest counter to (1): "which runs are mine" becomes a query in the job
planner's hot path instead of a directory listing. That is what the benchmark should
settle.

### C2c. Checked against `claude/eval-splits-evals-v2` — plan holds, with three refinements

That branch replaces the flat `eval_set_filter_id` / `eval_input_filter_id` fields with
named splits. Checked at `origin/claude/eval-splits-evals-v2` (`ef8d80e`).

```python
class TaskRunSplit(BaseModel):   source: Literal["task_run"];   filter_id: DatasetFilterId
class EvalInputSplit(BaseModel): source: Literal["eval_input"]; filter_id: EvalInputFilterId
SplitRef = Annotated[Union[TaskRunSplit, EvalInputSplit], Discriminator("source")]

class Eval(...):
    splits: Dict[str, SplitRef]   # keyed "train" | "val" | "test"
```

**"Use tags to link to evals" holds, and gets stronger.** An eval still never *owns*
its items — it names a filter per split, and `EvalInputFilterId` is still `tag::<name>`
or `all` (`dataset_filters.py:226-257`, unchanged on the branch). Task-level EvalRun
storage is compatible: evals remain lenses over a task-level item store, now with a
named-split lens per purpose. Two evals still share items by both selecting them.

Three things the branch changes for this project:

#### R1. The join key is `ItemKey`, not a bare id — this is a correctness trap

```python
ItemKey = Tuple[ItemSource, ID_TYPE]
"""Never a bare id: ids are drawn from one 12-digit generator shared by every model
type, so a TaskRun and an EvalInput can collide."""
```

A split can be TaskRun-backed or EvalInput-backed, so ids are only unique *within* a
store. Therefore:

- The trace reuse lookup keys on **`(ItemSource, item_id, task_run_config_id)`** — a
  bare `(item_id, run_config_id)` can collide across stores and hand back the wrong
  trace. This is exactly the kind of silent wrong-answer bug reuse introduces.
- `EvalScore` must denormalize the **full ItemKey** (source + id), not just an id.
- `eval_splits.eval_run_item_key(eval_run)` already derives this from an EvalRun's
  `dataset_id`/`eval_input_id`. Reuse it rather than re-deriving.

#### R2. `resolve_split()` is the single seam — the trace store must go through it

The module docstring is explicit: it is "the one seam that knows a split can be backed
by either `TaskRun`s or `EvalInput`s… nothing outside this module decides which store
an eval's items come from". A task-level EvalRun store must resolve membership through
`resolve_split()`, never by re-implementing filter dispatch. Also note `ResolvedSplit`
carries `eval_id` so a consumer can verify a split belongs to the eval whose judges are
about to score it — the same check applies to scoring reused traces.

#### R3. The runner's dedupe is already most of the way there

Post-splits, `collect_tasks_for_task_run_eval` keys `already_run` on
`(eval_config_id, run_config_id, ItemKey)`, and the separate `collect_tasks_for_eval_input`
collector is gone — one collector now serves both stores via the resolved split. So this
project's runner change is **a subtraction plus one addition**: drop `eval_config_id`
from the trace lookup, add a second score-level lookup on `(eval_run_id, eval_config_id)`.
Materially smaller diff than against pre-splits `main`.

#### Conflict to resolve: golden sets are deliberately TaskRun-only on that branch

`eval_splits.py` deliberately routes the golden set (`eval_configs_filter_id`) *around*
`resolve_split`: "Golden is TaskRun-only by definition, and routing it through here would
imply it could be EvalInput-backed, which is precisely what this project says it cannot
be." That directly contradicts §2.2 of this research, which treats unblocking
EvalInput-sourced `eval_config_eval` as a win the split delivers.

Both positions are coherent; they can't both stand. **Needs a decision** — see §5 Q11.

#### Back-compat precedents worth copying

The branch establishes patterns that support the C8 recommendation:

- **Two-homed storage.** `LEGACY_SPLIT_FIELDS` projects TaskRun-backed splits back into
  the flat legacy fields so older builds still read them — preserve, don't break.
- **`extra="allow"`** on `TaskRunSplit`/`EvalInputSplit` so fields from a future build
  survive a round-trip through an older one.
- **Lazy fold for internal-only data.** `migrate_eval_input_filter_id` is a
  `mode="before"` validator with `TODO: Remove before shipping. Only internal projects
  contain this key`. Confirms internal projects carry V2 data — and that a load-time
  fold is the house style for it. That style does *not* extend to this project's
  migration: relocating EvalRun files between directories cannot happen lazily on load,
  so a script is required (see the migration phase).

#### Note only, not actioned: generation provenance and `multi_turn_drive_config`

`multi_turn_drive_config` lives on `Eval` on an unmerged branch and is part of the
synthetic-user config. That means a multi-turn trace is a function of
`(item, task_run_config, drive_config)` — the Eval contributes to generation, so trace
reuse across evals is only valid when drive configs match.

The general principle this implies holds under every option and should be designed in
now: **an EvalRun must record a complete description of what produced it, and the reuse
lookup must key on that description.** Otherwise reuse silently returns traces produced
under different conditions — a wrong-answer bug, not a cache miss. Practically: a
generation-provenance fingerprint on EvalRun, joined into the lookup key.

Relocating `multi_turn_drive_config` off `Eval` (onto the run-config side, or its own
addressable entity) would make that fingerprint simpler. **Flagged for the plan, not
actioned here** — it's owned by the in-flight multi-turn branch and can be fixed before
ship.

Related, and independent of multi-turn: `UpdateRunConfigRequest` allows editing
`prompt_name` on an existing run config (`eval_api.py:317-327`, `1009-1017`), which
mutates the frozen prompt while the id stays the same. So `task_run_config_id` alone is
already not a complete description of how a trace was generated. The fingerprint needs
to cover this too.

### C3. Childing EvalScore to EvalRun is the intuitive answer and probably the wrong one

The overview floats "maybe even child them". Every aggregate read in the API is
*"give me all scores for this eval config"*:

- `compute_score_summary` — `eval_config.runs(readonly=True)` (`eval_api.py:648`)
- `get_eval_run_results` — same (`eval_api.py:1391`)
- `get_eval_configs_score_summary` — same, per config (`eval_api.py:1646`)
- run-config summary — same (`eval_api.py:1844`)

Today each of those is **one flat directory scan per config**.

- **EvalScore as a child of EvalRun:** answering "scores for config X" means walking
  every EvalRun directory (inputs × run configs) and loading *every* config's scores,
  then filtering. For 500 inputs × 4 run configs × 5 judges that's ~10,000 files
  walked to answer a question about 2,000.
- **EvalScore as a child of EvalConfig** (with an `eval_run_id` pointer): the read
  stays one flat scan per config — identical to today. And if EvalScore denormalizes
  `task_run_config_id` + `eval_input_id`/`dataset_id` (which it needs anyway for
  dedupe), then `compute_score_summary` needs **no join at all** and the aggregation
  code barely changes.

Trade-off: deleting an EvalRun can orphan scores (needs cleanup or tolerance), and
"show me every judge's verdict on this one trace" requires a scan across configs —
but that's a single-item detail view, and the rarer query.

**Recommendation:** `EvalScore` as a child of `EvalConfig`, pointing at `eval_run_id`.

### C4. Dropping `eval_config_id` from the dedupe key forces an unasked question: how many traces per (input, run_config)?

Trace dedupe becomes `(eval_input_id | dataset_id, task_run_config_id)`. If that is
unique, we can never store repeat samples — but non-determinism means users will
eventually want *k* runs per input to measure variance. If it is not unique, scoring
has to choose which trace(s) to score, and `percent_complete` gets more complicated.

**Recommendation:** allow many EvalRuns per key at the schema level, define V2.0
behavior as "one, reuse the latest", and note the extension path. Deciding "exactly
one" now is a one-way door.

### C5. Reference data belongs on the score side, not the trace side

`EvalRun.reference_data` is a snapshot of `EvalInput.reference`. But reference data is
*never used to generate the trace* — it's purely a scoring input. Under the split it
should live on `EvalScore` (a record of what the scorer actually saw), not on
`EvalRun`.

This also answers a staleness question the overview doesn't raise: if a user edits
`EvalInput.reference` and re-scores, the new score reflects the new reference data,
and the old score's snapshot records the old one. Clean.

### C6. `SkippedReason` splits across the two entities

The six values partition:

| Value | Lands on |
|---|---|
| `incompatible_input_shape` | EvalRun (can't generate for this input) |
| `missing_reference_key`, `extraction_failed`, `missing_trace`, `code_eval_not_trusted`, `type_not_available` | EvalScore |

Consequence: the on-read aggregation contract (`n_used`, `n_excluded`,
`percent_complete`, `eval_api.py:648-700`, `1844-1940`) has to be re-derived over two
records. C3's denormalization is what keeps this from getting expensive.

Also likely needed: a *new* trace-level terminal state for "generation failed", which
today just surfaces ephemerally and leaves a hole in the dataset.

### C7. Field placement details the overview doesn't cover

- `intermediate_outputs` (judge thinking) is **score-side**. It's currently on
  EvalRun and is the subject of active work — D31 in `evals_v2_cleanup` is about
  surfacing it in the run-result page. Coordinate.
- `task_run_usage` is **trace-side** and stays.
- Judge/LLM usage is **not recorded anywhere today**. The split is the natural moment
  to add `usage` to `EvalScore` so judge cost is finally visible. Small addition,
  real user value, and it is much cheaper to add now than later.

### C8. V1 back-compat is the largest cost, and "delete the scores field" is not available

Kiln 1.0.4 is shipped. V1 EvalRuns exist on users' disks at
`evals/{id}/configs/{id}/runs/*` with `scores` inline. Those are local-first,
often git-synced, project directories — we cannot rewrite them. The CLI's
`_ignore_eval_config_runs` (`package_project.py:904`) is also keyed on that path.

So the overview's "delete the scores" is not literally achievable. Options:

1. **Deprecate, don't delete.** Keep `scores` on `EvalRun` as a legacy-only field
   with a validator forbidding it on V2-shaped runs. Cost: the ugliness the project
   exists to remove partially survives in the schema.
2. **New entity names.** V1 `EvalRun` stays exactly where and what it is (legacy,
   read-only). V2's trace record gets a new class/folder under `Eval`. Cost: two
   entity names; benefit: neither is compromised, and V1 code paths are untouched.
3. **On-read adapter.** Present legacy EvalRuns as synthesized `(trace, score)` pairs
   at the read boundary. Cost: a translation layer forever; benefit: one shape above
   the datamodel.

**Recommendation:** option 2, possibly combined with 3 at the API layer only.
Naming needs care — see C10.

V2 dogfood data on disk is dev-only (V2 hasn't shipped), so a throwaway migration
script or "delete your dev eval runs" is acceptable there. **Needs confirming.**

### C9. Contain the blast radius at the API boundary

`EvalRunResult.results` is `List[EvalRun]` with scores inline, and the frontend
(`run_result/+page.svelte`, `run_eval.svelte`, compare views) reads
`results[].scores`. If the API keeps returning a **joined read model** (EvalRun +
its EvalScore flattened), storage splits while the frontend barely moves.
`api_schema.d.ts` regeneration is required either way.

Recommend explicitly: split the storage, keep a joined view model at the API.

### C10. Naming collision

`EvalScores` is already a type alias for `Dict[str, float]` (`eval.py:44`) used
throughout the codebase. A new model named `EvalScore` sitting beside it is a
permanent readability trap. Either rename the alias (`ScoreDict`) or pick a
different model name.

### C11. The data model alone doesn't deliver the win — there's a product surface

Once traces are reusable, users need a way to *ask for* re-scoring: a "score existing
runs with this judge" action distinct from "run eval". Plus decisions on:

- Does "Run eval" silently reuse traces? (Probably yes, with a visible "reused N
  existing runs" affordance.)
- Is there a "force fresh generation" escape hatch?
- What happens when a user **edits** an eval config in place — every EvalScore under
  it is now stale. (This problem exists today too, but reuse makes it more visible.)

If this project ships storage-only, the user-facing benefit is zero. Scope must
include the surface.

---

## 4. Non-issues checked

- **Nesting depth.** `KilnParentModel` handles arbitrary nesting; `Task > Eval >
  EvalConfig > EvalRun` is already 4 levels, and `Task` already hosts `eval_inputs`
  as a first-class child. No framework work needed for either placement.
- **Total file count.** The multi-judge case gets *fewer* files, not more: traces
  dedupe across configs (2k traces + 10k scores vs 10k fat records today). Per-write
  it's 2 files instead of 1 during a fresh run. Likely a wash or better, including
  for git sync.

---

## 4b. Generation provenance — the reuse key

**Proposed (scosman):** provenance is `(item, run_config)` — `(eval_input, run_config)`
for V2, `(task_run, run_config)` for legacy. Per R1 the item half is an `ItemKey`
(source + id), so the key is `(ItemSource, item_id, task_run_config_id)`.

**This is right, and it is not a new invention** — it is the invariant the datamodel
already claims. `TaskRunConfig` (`task.py:65-71`) and `KilnAgentRunConfigProperties`
(`run_config.py:48-50`) both state: *"includes everything needed to run a task, except
the input. Running the same RunConfig with the same input should make identical calls to
the model."* Reuse just cashes that in. No hash or fingerprint needed — two ids.

**The prompt-name concern is correctly dismissed.** `TaskRunConfig.prompt: BasePrompt`
is the frozen prompt, and the PATCH only rewrites `prompt.name`
(`eval_api.py:1009-1017`). The model never sees the name.

### The one gap — resolved

**`multi_turn_drive_config` on `Eval`** would be a generation input living on the very
entity the key drops: Eval B would reuse Eval A's multi-turn trace even when they drive
the synthetic user differently. A wrong answer, not a stale one.

**Confirmed absent from every branch this project builds on.** No code defines it in
`HEAD`, `origin/scosman/evals_v2`, or `origin/claude/eval-splits-evals-v2` — the only
hits are prose. It exists on the unmerged eb-v2 branch, and **scosman confirms it moves
onto `EvalInput` before ship**.

That closes the gap completely: once the drive config is on the EvalInput, it *is* part
of the item, so `(ItemSource, item_id, task_run_config_id)` covers it with no extra
term. The key is complete as proposed.

Two notes for the eb-v2 handoff, not work for this project:

- `specs/projects/eb_v2_splits_alignment/project_overview.md` §9 independently raises
  the same question and leans the other way — *"eval-level is probably right — the drive
  config exists to hold the synthetic user constant across run configs so a comparison
  varies only the agent."* Moving it to `EvalInput` **preserves** that property (the
  item is shared across run configs in a comparison) and additionally holds it constant
  across evals, which is what reuse needs. Worth saying explicitly so the two projects
  don't reach opposite conclusions.
- That branch also has `validate_multi_turn_drive_readiness` (`eval_runner.py:341`) and
  `SkippedReason.missing_drive_config`. Per-input placement turns readiness into a
  per-item check, which fits the existing per-item skip model.

### Three pre-existing holes — accepted, no action

Reuse extends the exposure window on three existing gaps in the "identical calls"
invariant. **scosman accepted all three; no work here.**

| Hole | Why the key doesn't cover it | Why accepted |
|---|---|---|
| **Unfrozen dynamic prompts** | Freezing is optional (`prompt: BasePrompt \| None`); a dataset-derived `prompt_id` drifts as runs accumulate (`prompt_builders.py:206`) with no id change | Unfrozen prompts aren't used in measured experiments |
| **Tools referenced by id** | `ToolsRunConfig.tools: List[ToolId]` stores ids only; definitions are separately mutable | Tools are immutable in practice |
| **`task.instruction`** | Mutable, sits above the run config | Baked into the frozen prompt |

Trace age is still visible for free — `created_at` is on the base model and the reuse
indicator (C11) is already in scope.

## 4c. Golden-set conflict — resolved

**The conflict.** §2.2 of this research treats "unblock EvalInput-sourced
`eval_config_eval`" as a win the split delivers. `eval_splits.py` holds the opposite
deliberately: golden is TaskRun-only *by definition*, routed around `resolve_split` on
purpose, because "routing it through here would imply it could be EvalInput-backed,
which is precisely what this project says it cannot be."

**The splits branch is right, and §2.2 was imprecise.** The blocker is not stored
output — it is human ratings.

- Golden sets exist to answer *"how well does this judge correlate with a human?"*
  `Eval.eval_configs_filter_id` says so in its own field description: *"Should consist
  of dataset items with ratings."*
- Human ratings live in exactly one place: `TaskRun.output.rating`
  (`human_score_from_task_run`, `eval_api.py:562-587` — overall rating, requirement
  ratings, named ratings, all off the TaskRun).
- `EvalInput` has no `output` and no `rating`. It is an input, not a judged item. So an
  EvalInput-backed golden set has nothing to correlate against, split or no split.

**What §2.2 actually got right, and why it stops being a mode.** `eval_config_eval`
today does double duty:

| Capability | Needs | Status under the split |
|---|---|---|
| Correlate judge scores against human ratings (calibration) | Human ratings → TaskRun | Unchanged. Still TaskRun-only |
| Score a stored output without re-running the task | A persisted output | **Stops being a mode at all** |

The second is the entire point of this project. Once a trace is a first-class record,
"score without generating" is not a special mode — it is simply what happens when the
trace lookup hits. So the thing §2.2 wanted does arrive; it arrives as the normal path
rather than as an EvalInput-backed golden set.

That is a real simplification worth taking deliberately: `eval_config_eval` narrows
from "two capabilities behind one flag" to just the calibration capability.

**Resolution:**

1. **Golden sets stay TaskRun-only.** Agree with the splits branch; keep the golden
   filter routed around `resolve_split`. §2.2's framing is withdrawn.
2. **Amend §2.2's claim** to what is actually true: the split removes the
   `"EvalInput source has no stored output"` skip (`eval_runner.py:444-462`) by making
   the output exist — not by making EvalInput golden sets work.
3. **Follow-up, post-ship, not this project:** the honest V2 question is *where do human
   ratings live in an EvalInput world?* The natural answer is a rating on the `EvalRun`
   — which only becomes possible because this project makes EvalRun a first-class
   record. Worth recording as an unlock, not scheduling.

## 4d. Does EvalRun collapse into TaskRun? (scosman)

**Proposal:** kill the new EvalRun entity. Eval traces *are* TaskRuns. Add a source
pointer (`ItemSource` + `EvalInput.id` / `TaskRun.id`) and a flag/tag so they filter out
of the dataset UI by default.

### Both premises verified

| Claim | Verdict |
|---|---|
| TaskRun already stores the trace | Yes — `trace: list[ChatCompletionMessageParam] \| None` (`task_run.py:74`) |
| TaskRun already stores the run config | Yes, **twice** — `output.source.run_config_id` *and* `output.source.run_config: RunConfigProperties`, the full frozen properties (`task_output.py:208-215`) |

### It carries three more things we need, which strengthens the case

- **`output.rating`** — human ratings. This directly reopens the §4c follow-up: golden
  sets are TaskRun-only *because ratings live on TaskRuns*. If eval traces **are**
  TaskRuns, they are natively rateable, and a V2 EvalInput-backed golden set becomes
  possible with nothing new invented. The "post-ship unlock" recorded in §4c becomes
  free.
- **`parent_task_run_id`** (`task_run.py:78`) — multi-turn chaining already modelled.
  The synthetic-user conversation has a home that a fresh EvalRun entity would have had
  to reinvent.
- **`feedback` children + `repair_instructions` / `repaired_output`** — curating a bad
  eval output into a training example becomes a first-class flow instead of an
  export/reimport. Adjacent to the "bridge between data guide examples and eval
  datasets — promotion mechanism" item parked in `evals_v2/components/90_open_risks.md`.

Also note `usage` **and** `cumulative_usage` (sum across a whole trace including seeded
prior trace) — better than the single `task_run_usage` field EvalRun has today, and
exactly right for multi-turn cost accounting.

### Two hard constraints to design around

**1. Sharing the class forces sharing the directory.** `KilnParentModel.__init_subclass__`
rejects registering one child class under two relationships — *"A child class can only
appear once - it holds a single `relationship_name()` / `parent_type()` pair"*
(`basemodel.py`). So there is no "same class, separate `eval_runs/` folder" option. Eval
traces land in `runs/` alongside the dataset, or they are a different class.

*(A `class EvalTaskRun(TaskRun)` subclass would be a distinct class and so get its own
folder — but then `isinstance(x, TaskRun)` is True for eval traces, so every filter and
consumer written against TaskRun silently accepts them. That trades a visible problem
for an invisible one. Listed for completeness, not recommended.)*

**2. `output: TaskOutput` is required** (`task_run.py:44`) — a TaskRun cannot exist
without an output. A failed generation therefore has no representation. That is fine,
and it **settles open question "failed generations"**: leave absent, matching today's
"absence = not-yet-run" convention. One fewer decision.

### The real objection: pollution, and how to make it safe

Every `task.runs()` consumer would start seeing eval traces:

| Call site | Risk if polluted |
|---|---|
| `prompt_builders.py:206` (few-shot) | **Feedback loop** — model prompted with its own eval outputs. Partly self-limiting: the builder selects on `repaired_output` then on rating, and eval traces are unrated by default |
| `dataset_split.py:186,211` | Fine-tune train/val sets contaminated with eval traces |
| `finetune_api.py:234` | Fine-tune sample selection |
| `run_api.py:284,355,632` | Dataset browsing UI floods |
| `dataset_filter_from_id` → `AllDatasetFilter` | Any `all`-filtered consumer gets everything |

**Recommendation: invert the default rather than add an opt-out flag.** Make
`task.runs()` exclude eval traces unless explicitly asked for. Then forgetting to handle
this fails *visibly* (missing data) instead of *silently* (contaminated training data,
leaked feedback loop). A tag-based opt-out requires auditing every call site and getting
all of them right; a default-exclude requires the eval runner to opt in, in one place.

This is the crux of the decision and should be a spec-level invariant, not an
implementation detail.

### Volume

Merging eval traces into `runs/` makes the C2b directory-scan concern worse, not better
— the dataset directory now holds the user's corpus *and* every eval trace. The
benchmark spike gating D1 becomes more important, and should now measure `runs/` at
combined scale rather than a separate `eval_runs/`.

### What it kills

- **The new EvalRun entity, entirely.** No new tree, no new class, no migration target
  for it.
- **The naming problem (C10) dissolves** — V2 has no "EvalRun", so the legacy V1
  `EvalRun` keeps its name unambiguously.
- **V1 back-compat gets simpler** — legacy EvalRuns stay exactly where they are; there
  is no new entity competing for the name or the concept.
- D1 (task-level EvalRun) is subsumed: TaskRun is already task-level.

### One thing to revisit deliberately, not by accident

Today's runner comments that `run_task` **deliberately** does not persist its generation
(`eval_runner.py:498-499`). No rationale for that choice is recorded in the specs I read.
Worth asking whether it was a considered decision or just the path of least resistance,
before reversing it.

### Recommendation

**Pursue it.** It removes an entity rather than adding one, and it unlocks ratings,
multi-turn chaining, and repair/feedback on eval traces for free. Gate on two things:

1. Agreement that `task.runs()` becomes default-exclude (the safety property).
2. The directory-scan benchmark at combined dataset + eval-trace scale.

## 5. Decision status

### Settled

| # | Decision | Outcome |
|---|---|---|
| D1 | Where EvalRun lives | **Task level**, sibling of `eval_inputs/`. Gated on a directory-scan benchmark as a phase-1 spike (C2b) |
| D7 | Where EvalScore lives | **Child of `EvalConfig`**, with an `eval_run_id` pointer and a denormalized `ItemKey` + `task_run_config_id`. Scores are tied to the config (C3, R1) |
| D8 | Traces per `(ItemKey, run_config)` | **Many possible, first wins.** Sync means uniqueness can never be guaranteed; the system is already robust to duplicates and selects the first found. Never intentionally create more than one. Leaves the door open to N-sampling later (C4) |
| D9 | Generation provenance key | **`(ItemSource, item_id, task_run_config_id)`** — no hash; the datamodel already asserts this invariant. Complete as proposed: `multi_turn_drive_config` is absent from every branch here and moves onto `EvalInput` before ship (4b) |
| D10 | Pre-existing drift holes | **Accepted, no action** — unfrozen dynamic prompts, tools-by-id, `task.instruction` (4b) |
| D11 | Golden sets | **Stay TaskRun-only.** Human ratings live only on `TaskRun.output.rating`; EvalInput has no output or rating. §2.2 withdrawn. "Score without re-running" stops being a mode and becomes the normal trace-lookup path (4c) |
| D2 | Cross-eval reuse mechanism | Pointer-EvalInput option **dropped** — it re-implements tag membership (C2b) |
| D3 | Metrics concept | **Deferred**, as a read-side concept. Commit now only to scoping it by a split ref so adding it later stays cheap (C2b, R2) |
| D4 | Internal V2 data | **Migration script**, sequenced as the final phase. A lazy load-time fold is not available for file relocation (C2c) |
| D5 | `multi_turn_drive_config` placement | **Moves onto `EvalInput` before ship**, owned by the eb-v2 branch. Confirmed absent from all branches here. Not actioned by this project; flag the conflicting lean in eb-v2 §9 (4b) |
| D6 | Splits-branch compatibility | Confirmed. Tag-filter linkage survives; runner dedupe already keys on `(eval_config, run_config, ItemKey)` (C2c) |

### Open

**Blocking the functional spec:**

1. **V1 back-compat approach** — deprecate `scores` in place, new entity names for
   V2's trace record, or an on-read adapter (C8). The splits branch's two-homed /
   `extra="allow"` / lazy-fold precedents lean toward preserve-don't-break.
2. **Is the re-score product surface in scope** for this project, or a follow-up?
   Storage-only ships zero user-visible benefit (C11).

**Design detail, low risk, needs ratification:**

4. **Field placement** — `reference_data` → score side (C5); `intermediate_outputs` →
   score side, coordinate with D31 in `evals_v2_cleanup` (C7); judge `usage` → new on
   EvalScore (C7); `SkippedReason` partition across the two entities (C6).
5. **Failed generations** — persist a terminal "generation failed" EvalRun, or leave
   absent so it retries? (2.4)
6. **Retry granularity** — confirm `RetryableError` retries only the failed phase
   rather than the whole job (2.4).
7. **Naming** — `EvalScore` collides with the existing `EvalScores` alias (C10).
