---
status: draft
---

# Eval Score Direction

Evals have several score types where the direction of desired change is obvious:

- **pass/fail** → more passes please (higher is better)
- **1–5 star** → higher please (higher is better)

But we also support **"custom"** scores, where direction is _not_ obvious. A custom
score could be:

- "total tool failures" → **lower is better**
- "total tool calls" → **informational** (no target, just information)

## Request

Add an enum field on the `eval.py` data model, in the score list (`EvalOutputScore`),
that — for score type `custom` — declares whether the score is `higher_is_better`,
`lower_is_better`, or `informational`.

## Validation

- **Required** on new evals (must be specified when a custom score is created).
- **Relaxed** when loading old evals from file (existing custom scores that predate
  this field must still load).
