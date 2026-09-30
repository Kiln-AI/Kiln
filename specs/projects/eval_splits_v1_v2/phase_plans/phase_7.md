---
status: complete
---

# Phase 7: eb-v2 alignment project overview

## Overview

Documentation only. This phase writes no code and adds no tests.

Functional spec §11 requires this project to hand the eb-v2 line an honest, current description of
what aligning to the shipped splits model costs — as a `project_overview.md` under
`specs/projects/eb_v2_splits_alignment/`, playing the same role this project's own
`project_overview.md` plays: the *what*, not a functional spec, architecture, or plan.

It runs last because the conflict surface is only knowable once the model has landed. Phases 1–6
are committed, so the merged tree can be read as it actually is rather than as it was designed.

## Steps

1. **Read the shipped model from the tree, not the specs.** `libs/core/kiln_ai/datamodel/eval.py`
   (`TaskRunSplit`, `EvalInputSplit`, `SplitRef`, `EvalSplitName`, `LEGACY_SPLIT_FIELDS`,
   `Eval.splits`, `migrate_eval_input_filter_id`, `fold_legacy_filter_fields`, `validate_splits`,
   `set_split`, `serialize_preserving_split_format`), `libs/core/kiln_ai/datamodel/eval_splits.py`,
   `libs/core/kiln_ai/adapters/eval/eval_runner.py`, `app/desktop/studio_server/eval_api.py`,
   `app/desktop/studio_server/jobs/workers/eval.py`, `app/desktop/studio_server/jobs/api.py`,
   `libs/server/kiln_server/utils/spec_utils.py`, `app/web_ui/src/lib/utils/eval_splits.ts`.

2. **Read eb-v2 as it actually is.** `origin/dchiang/eb-v2-merge` is the integration ref; the three
   `review/eb-v2/*` branches are its inputs. Record which ref was read and at which commit, since
   they are still moving.

3. **Derive the real conflict surface** rather than restating §11's starting points: compute the
   files both lines changed since their common ancestor `0b34c87`, then read each splits-relevant
   one on both sides. Record what alignment requires, with file/line anchors on both sides.

4. **Find what §11's starting points miss.** §11 names three (per-call-site source branching, the
   eval-creation path, the removed lazy migration). Everything beyond those is this phase's job to
   find — in particular the surfaces eb-v2 has never seen at all, and the eb-v2 features whose
   *own* bookkeeping the new model invalidates.

5. **Decide where the two homeless `eval_runner.py` items go** (`implementation_plan.md` `## Notes`:
   the `EvalJob` type-level constraint, and the `collect_tasks_for_eval_config_eval` dedupe bug) —
   alignment project or separate follow-up — and say which, with reasoning.

6. **Write `specs/projects/eb_v2_splits_alignment/project_overview.md`.** Overview only. Mirror the
   shape of this project's overview: summary, a note to the spec author, scope, workflow,
   background, problems detected as observations rather than instructions, verification notes, open
   questions.

## Tests

None. This phase produces one Markdown file and changes no code, so there is nothing to lint,
type-check, or execute. Correctness here means the file/line anchors and behavioral claims are
accurate against both trees at the commits named in the document — verified by reading, which is
what step 3 is.
