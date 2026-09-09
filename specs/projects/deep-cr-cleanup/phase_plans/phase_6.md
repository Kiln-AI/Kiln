---
status: complete
---

# Phase 6: Spec doc alignment (docs only)

## Overview

Align two evals_v2 spec documents to match the actual code behavior, where the implementation intentionally diverged from the original spec for good reasons. No code changes in this phase.

## Steps

1. **Edit `specs/projects/evals_v2/components/27_type_code_eval.md` section 2.2** — Replace the lenient score-validation rules (missing keys -> None, extra keys -> ignored) with documentation of the strict exact-key-match behavior actually implemented in `v2_eval_code_eval.py:_validate_scores`. The code raises `RuntimeError` on any mismatch between actual and expected score keys. Note this as the deliberate Kiln behavior choice.

2. **Edit `specs/projects/evals_v2/components/15_v1_v2_coexistence.md` section 4.1** — Change the spec's `evaluation_data_type: EvalDataType | None = None` to `EvalDataType | None = EvalDataType.final_answer` to match the actual code at `eval.py:793-796`. Add a rationale note explaining the back-compat benefit: a V1 Eval on disk that omits this field loads as `final_answer` (its true V1 behavior) rather than ambiguous `None`.

## Tests

N/A — docs-only phase.
