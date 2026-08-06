---
status: complete
scope: Train/val/test dataset splits working across both V1 (TaskRun) and V2 (EvalInput) eval data sources
branch: scosman/eval-splits-v1-v2
supersedes: PR #1621, PR #1620
target_pr: scosman/eval-splits-v1-v2 → scosman/evals_v2
---

# Project: Train/val/test splits across V1 and V2 eval datasets

## Summary

The eval split work on `scosman/eval-api-improvements` (PR #1621) adds `Eval.val_set_filter_id`
and an optional `split` param to the eval run and results APIs. It was branched from `main`,
where `TaskRun` is the only eval data source — so all of it is TaskRun-only.

`scosman/evals_v2` introduces a second data source: `EvalInput`, selected by
`Eval.eval_input_filter_id`, which is **mutually exclusive** with `eval_set_filter_id`. That
source currently has exactly one filter slot — no train, no val.

**This project merges the two lines and makes train/val/test splits work for both data sources.**
EvalInput-backed evals must get the same three splits, through the same API surface, as
TaskRun-backed evals.

## A note to the spec author

This document is the **what**, not the **how**. The only thing genuinely fixed is the goal above
plus the scope decisions in the next section.

Everything under "Problems detected" is a set of observations from reading the two branches —
places the merge looked likely to break, and questions the design will have to answer. They are
**not a design, and not a checklist**. Where a note is marked *Rough guidance*, it reflects
something real we learned and is worth carrying forward, but the spec process should confirm
whether it's actually the best approach rather than inheriting it.

You are expected to think harder about this than this document does, to find problems it missed,
and to propose a better design than any sketched here. If a suggestion below turns out to be
wrong or beside the point, discard it — and treat that as a signal the rest deserves the same
scrutiny.

---

## Scope

**In scope**

- `EvalInput`-backed evals get working train / val / test splits.
- Splits are addressable through the same API surface as the TaskRun source, so callers don't
  branch on data source.
- Merge `scosman/evals_v2` into the #1621 line and resolve the resulting conflicts.
- `EvalProgress` reports a val count alongside the existing train count, for symmetry.

**Out of scope (decided)**

- **Golden sets for `EvalInput`.** `eval_configs_filter_id` and judge comparison stay
  TaskRun-only. This must fail *loudly* and comprehensibly — not silently produce empty or
  misleading results. See "Problems detected §6" for why the gap exists and what "loudly" has
  to cover.
- **Data-creation paths for EvalInput splits.** A new copilot is coming to populate
  `EvalInput`s; tagging items into splits at creation time is that project's problem, not this
  one. Don't build it here, and don't design around a guess at what it will do.
- Broader UI work beyond the `EvalProgress` val count.

---

## Git / PR workflow

1. **Branch from `scosman/eval-api-improvements`** (`45dd7b0`) as `scosman/eval-splits-v1-v2`.
2. **Merge `scosman/evals_v2` in** and resolve conflicts. The merge base of the two branches is
   `df0fd56`, so this is wide. Note #1621 is **already `dirty` against `main`** independently of
   evals_v2 — expect conflicts from more than one direction.
3. **Implement** the split support.
4. **Close PR #1621** (`scosman/eval-api-improvements` → `main`), pointing at the replacement.
5. **Close PR #1620** (`scosman/val-set` → `main`) — superseded; its single `val_set_filter_id`
   commit is carried by this branch.
6. **Open a new PR: `scosman/eval-splits-v1-v2` → `scosman/evals_v2`.** This one gets a real
   review.

*(A merge into `agi-anyting_goes_into` was originally step 4 here. Dropped — this branch goes
straight to its PR against `scosman/evals_v2`.)*

Nothing here needs to reach `main` on its own schedule; it lands on `main` when evals_v2 does.

---

## Background: two axes both called "v2"

Conflating these is what produced the original mismatch. They are independent:

| Axis | V1 | V2 |
|---|---|---|
| **Judge** — `EvalConfig.config_type` | `g_eval`, `llm_as_judge` | `v2` + `V2EvalType` (`llm_judge`, `exact_match`, `pattern_match`, `set_check`) |
| **Data source** — `Eval.*_filter_id` | `eval_set_filter_id` → `TaskRun` | `eval_input_filter_id` → `EvalInput` |

An eval can be v2-judge over v1-data — that's what every eval the UI creates today is. This
project concerns only the **data source** axis; the judge axis should need no changes.

### State on `scosman/evals_v2`

**TaskRun source** — four filter roles, all `DatasetFilterId`, all resolved through
`dataset_filter_from_id()` → `TagFilter(task_run.tags)` (`dataset_filters.py:54`):

- `eval_set_filter_id` — the **test** set (the "eval set" name is legacy)
- `eval_configs_filter_id` — the **golden** set (human-rated; scores judges, not models)
- `train_set_filter_id` — read by prompt optimization and a progress counter
- `val_set_filter_id` — added by the #1621 line; does not exist on evals_v2 yet

**EvalInput source** — one filter slot:

- `eval_input_filter_id` (`eval.py:846`), type `EvalInputFilterId`, resolved through
  `eval_input_filter_from_id()` → `TagEvalInputFilter(eval_input.tags)` (`dataset_filters.py:250`).
  Accepts only `all` and `tag::<x>` — no `multi_filter::`, no `high_rating` (those read TaskRun
  ratings).
- `EvalInput` (`eval.py:384`) carries `data`, `reference`, `tags`.
- `Eval.validate_filter_fields` (`eval.py:990`) enforces **exactly one** of
  `eval_set_filter_id` / `eval_input_filter_id`.

---

## Problems detected

Observations, not instructions. Line references were accurate at `8433300` (evals_v2) and
`45dd7b0` (#1621) and may have moved.

### 1. How an EvalInput-backed eval expresses its splits

One filter field has to become several, for a source whose filter-id type is narrower than the
TaskRun one. This is the central design question and everything else follows from it.

*Rough guidance, but spec process to confirm this is the best approach:* four directions we
considered, in no particular order —

- **(a) Parallel fields** per source (`train_eval_input_filter_id`, etc.). Explicit; ends at
  seven or eight filter fields on `Eval` plus a mutual-exclusion validator to maintain.
- **(b) A splits map** — `splits: dict[EvalSplitName, FilterId]`, filter-id type validated
  against the eval's source mode. Cleanest end state; largest migration surface, since every
  existing eval on disk and every reader is affected.
- **(c) Widen the existing fields** to hold either filter type, validated by source mode.
  Smallest diff; gives up the type-level guarantee that a `DatasetFilterId` is TaskRun-shaped,
  and `DatasetFilterId` admits forms `EvalInputFilterId` does not.
- **(d) Something else** — a better design proposed and agreed during speccing. Expected, not a
  fallback.

### 2. The split override doesn't reach the EvalInput path

`EvalRunner.eval_set_filter_id_override` (from #1621) only affects
`collect_tasks_for_task_run_eval`. On evals_v2, `collect_tasks()` short-circuits to
`collect_tasks_for_eval_input()` when `_source_mode == "eval_input"` (`eval_runner.py:107`), so
after a naive merge the override is **silently ignored** for EvalInput evals: the request
succeeds and runs the full set. Silent-wrong is the failure mode to design against here.

### 3. Job worker computes the wrong item universe

In `jobs/workers/eval.py`, `_dataset_filter_id()` falls back to `eval.eval_set_filter_id` —
non-optional on the #1621 branch, `| None` on evals_v2, so a type error after the merge. More
importantly the progress universe is built from `task.runs(readonly=True)`, which is empty for an
EvalInput eval; totals would read zero and resumes could short-circuit against the wrong set.
`task.eval_inputs(readonly=True)` (`task.py:234`) is the EvalInput equivalent.

`jobs/api.py` also pre-resolves the split before job creation so a bad split 422s instead of
becoming a doomed background job. Whatever that check becomes, it needs to hold for both sources.

### 4. "Test always resolves" is no longer true

`Eval.filter_id_for_split()` and `split_filter_id_from_eval()` (#1621) both assume
`eval_set_filter_id` is always set. On evals_v2 it's `None` for every EvalInput eval, so the 422
branch fires for `test` with the message *"no test_set_filter_id"* — naming a field that has
never existed. The assumption and the diagnostics both need revisiting.

### 5. Results filtering keys on the wrong id

The results endpoint filters `run_result.dataset_id in split_dataset_ids`. EvalInput-backed
`EvalRun`s carry `dataset_id=None` and `eval_input_id` set (`eval_runner.py:452`, `:474`), so
`?split=` would return **zero results** for every EvalInput eval. Another silent-wrong.

### 6. Golden is out of scope — but "loudly" has real requirements

Worth understanding why the gap exists, so the failure can be honest rather than incidental.

Golden items are TaskRuns matching `eval_configs_filter_id`, each carrying `output.rating` — a
human verdict. `human_score_from_task_run` (`eval_api.py:562`) maps each of the eval's
`output_scores` onto that rating, and judge comparison (`eval_api.py:1642`) correlates judge
score against human score per output score. That correlation is how a judge gets chosen —
it answers "is this judge any good?", where test/train/val answer "is this model any good?".

`EvalInput` can't feed it at three layers: golden runs use `eval_config_eval`, which reuses the
item's *stored* output without executing the task (`eval_runner.py:122`) and `EvalInput` has no
output; `EvalInput` has no rating storage; and the correlation path looks items up by
`eval_run.dataset_id` (`eval_api.py:1647`), which is `None` for EvalInput runs. The runner
already skips these with an explicit reason (`eval_runner.py:459`).

Note `EvalInput.reference` is *not* a substitute. It's data a judge compares an output against;
a human rating is a verdict on the judge. Reference answers let a judge score; they don't tell
you whether the judge scores well.

*Rough guidance, but spec process to confirm this is the best approach:* "loudly" should
plausibly cover the golden-set endpoints that currently 400 on a null `eval_set_filter_id`
(`get_eval_progress` `eval_api.py:1420`, `get_eval_config_score_summary` `:1491`) and the one
that silently skips such evals (`get_eval_results_summary` `:1537`). A silent skip and an
accurate 4xx are very different experiences for a caller. Whether each becomes an error, an
empty-with-reason, or gains EvalInput support is a design call.

### 7. Migrations mint TaskRun-typed filters unconditionally

`migrate_train_set_filter_id` (`eval.py:955`) and the new `migrate_val_set_filter_id` stamp
`tag::train_{slug}` / `tag::val_{slug}` as `DatasetFilterId` on every load — including
EvalInput-backed evals, whose data isn't TaskRuns. Also worth checking what
`generate_spec_eval_tags` / `generate_spec_eval_filter_ids` (`spec_utils.py`, widened to a
4-tuple by #1621) should do for each source.

### 8. Filter-id types aren't interchangeable

`DatasetFilterId` accepts `multi_filter::…`, `high_rating`, `thinking_model`;
`EvalInputFilterId` accepts only `all` and `tag::…` (`dataset_filters.py:226`). Any design that
shares a field or a helper across sources has to keep a TaskRun-only filter form from being
stored on an EvalInput split.

### 9. `EvalProgress` symmetry (in scope)

`EvalProgress` reports `train_dataset_size` (`eval_api.py:1462`) and renders it on the spec eval
page. With `val_set_filter_id` added, val should report a count too — otherwise train shows a
number and val silently doesn't exist.

---

## Verification notes

> **Not a test plan, and not comprehensive.** These came from reading the two branches, not from
> running them. The implementing agent owns producing a complete and correct plan: re-derive the
> affected surface from the merged tree. Treat anything below that proves stale as evidence the
> rest needs the same scrutiny — and expect to find failure modes not listed here.

Areas that looked most likely to break quietly:

- A split request that silently covers the full set instead of the split (§2) — succeeds with a
  200, so only an assertion on *which items ran* catches it.
- Results filtering returning empty for one source but not the other (§5).
- Progress totals and resume behavior against a partial split run, per source (§3).
- Incremental-cache reuse across overlapping splits — #1621 claims item-grained caching makes
  this safe; worth confirming it still holds once a second source exists.
- Migration behavior on both eval shapes, including a load/save round trip that neither drops
  nor invents fields (§7).
- The exactly-one-source invariant surviving whatever the new field set becomes, with a
  comprehensible error when violated (§1).
- Filter-id type confusion across sources (§8).
- Golden-path failures being loud and accurate rather than empty (§6).
- **The no-split path being byte-identical to today.** The whole param is opt-in; existing V1
  behavior must not move.

---

## Open questions

1. **Model shape** — §1, including option (d). Drives most of the rest.
2. **Which endpoints get taught the EvalInput path** vs. fail explicitly, given golden is out of
   scope — §6.
3. ~~**Intermediate branch** for the `agi-anyting_goes_into` merge~~ — moot; that merge was
   dropped from the workflow above.
