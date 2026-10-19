---
status: complete
---

# Project: Split EvalRun into EvalRun (trace) + EvalScore (scores)

## The problem

Evals V2 has a design flaw we want to fix before we ship.

`EvalRun` includes both the trace *and* the eval config results (scores) — and these
should be separate concepts.

Simplest case: I make a new judge for an eval. The trace for that
run-config/eval-input pair has already been run and saved, but to run the new judge
I currently need to re-run it, not reusing the expensive trace and synthetic user
run. I should be able to reuse the trace, and just score again. Scoring is often
free (code evals). This makes iteration on judges much cheaper.

## Proposed solve

Split `EvalRun` into two entities:

- **EvalRun** — the trace. Exists today; delete the scores and the connection to a
  singular `eval_config`.
- **EvalScore** — the scores. Links to an `EvalRun` id (maybe even childed to it),
  and links to an `eval_config` (key data).

## Second goal: don't lose expensive traces on judge failure

EvalRuns should be saved as soon as the run is done. A failing judge shouldn't cause
the data to be lost.

Re-running should find the existing EvalRun and jump straight to judging — the same
mechanism that makes new eval configs fast (try to find an existing run before
running a new one).

## Known open issue

This likely shifts our whole data structure. `EvalRun` is currently a child of
`EvalConfig`. In the new model it should be under the `Eval`? And `EvalScore` also
under the `Eval`, but with IDs mapping to both `EvalConfig` and `EvalRun`?

## Deliverable: migration script (final phase)

This branch hasn't shipped, but internal projects are already using it. A migration
script that relocates existing V2 EvalRun records into the new structure is a required
deliverable, sequenced as the final phase.

Note this cannot follow the house style of a lazy load-time fold (as
`migrate_eval_input_filter_id` does on the splits branch) — relocating files between
directories has to be an explicit script.

## Dependencies

- **`claude/eval-splits-evals-v2`** — replaces per-eval filter fields with named
  splits (`Eval.splits: Dict[str, SplitRef]`). This project builds on it. Checked:
  the tag-filter linkage this project depends on survives, and the runner's dedupe is
  already keyed on `(eval_config, run_config, ItemKey)`.
- **Multi-turn branch** — `multi_turn_drive_config` on `Eval` is part of the synthetic
  user config and is a generation input. Its placement should be fixed before ship.
  Noted in the plan; not actioned by this project.

## Approach

Research first. Confirm the logic is sound and challenge the assumptions before
committing to a design.
