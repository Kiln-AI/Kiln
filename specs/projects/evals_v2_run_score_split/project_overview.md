---
status: draft
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

## Known open issue

This likely shifts our whole data structure. `EvalRun` is currently a child of
`EvalConfig`. In the new model it should be under the `Eval`? And `EvalScore` also
under the `Eval`, but with IDs mapping to both `EvalConfig` and `EvalRun`?

## Approach

Research first. Confirm the logic is sound and challenge the assumptions before
committing to a design.
