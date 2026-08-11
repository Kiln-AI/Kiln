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

`eval_config_eval` over an EvalInput-sourced dataset is **not supported today** — it
persists a skip: `"EvalInput source has no stored output; eval_config_eval over
EvalInput is deferred in V2.0"` (`eval_runner.py:444-462`). The reason is exactly the
flaw under discussion: there is no place to store an EvalInput's generated output
independent of a judge. The split fixes this as a side effect. That converts this
project from "optimization" to "unblocks a shipped-as-broken path".

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

## 5. Decisions the functional spec must make

1. **Where does EvalRun live** — under `Eval` (C2-A) or under `Task` (C2-B)?
   Recommendation: Task, gated on a directory-scan benchmark (C2b). Settling this
   also settles cross-eval reuse: the pointer-EvalInput option is dropped, and
   Metrics is deferred as a read-side concept scoped by an `EvalInputFilterId`.
2. **Where does EvalScore live** — child of `EvalConfig` with an `eval_run_id`
   pointer (recommended, C3), or child of `EvalRun`?
3. **How is V1 back-compat handled** — deprecate-in-place, new entity names, or
   on-read adapter (C8)?
4. **One trace per (input, run_config), or many?** (C4)
5. **Is `eval_config_eval` unified into the same trace+score model** (C1), and does
   an EvalInput-sourced golden set become supported (2.2)?
6. **Field placement:** `reference_data` (C5), `intermediate_outputs` (C7),
   judge `usage` (C7), `SkippedReason` partition (C6).
7. **Product surface:** re-score action, reuse indicator, force-fresh escape hatch,
   stale-on-config-edit behavior (C11).
8. **Naming** (C10).
9. **Failed generations:** persist a terminal "generation failed" EvalRun, or leave
   absent so it retries? (2.4)
10. **Retry granularity:** confirm `RetryableError` retries only the failed phase
    rather than the whole job (2.4).
