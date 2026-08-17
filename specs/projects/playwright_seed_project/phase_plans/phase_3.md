---
status: draft
---

# Phase 3: The eval, its judge, and its results

## Overview

Phase 3 authors architecture.md's content group 4 into the committed fixture: one eval,
one judge (eval config), and eval results across two run configs on the structured task.
It carries **specs** with it — `POST /api/projects/{p}/tasks/{t}/specs` constructs the
`Eval` and the `Spec` together and stamps `spec.eval_id` with the eval's id, so the
create-eval flow is the only path that yields a `Spec` at all, and therefore the only
path where `Eval.associated_spec()` returns something rather than `None`.

Nothing in this phase is code. The diff should be JSON under
`.agents/playwright_project/` plus this plan. Everything is created by clicking through
the app at `http://localhost:6544` and captured with
`.agents/scripts/playwright_server.sh snapshot`.

Generation — both the task runs the eval executes and the judge's own calls — uses
`deepseek/deepseek-v4-flash-0731` through OpenRouter, connected through the UI so the key
lands in the sandbox's gitignored `settings.yaml`, which `snapshot` never reads.

### What the app needs before an eval has results

Read out of the code before planning, because every step below is one of these
preconditions:

| Precondition | Where it comes from |
|---|---|
| A `Spec` + `Eval` pair | `create_spec` in `libs/server/kiln_server/spec_api.py` builds both and links them |
| An eval set | Dataset runs tagged `eval_<name>`; the filter id is `tag::eval_<name>` |
| A golden set | Dataset runs tagged `eval_golden_<name>` (`eval_configs_filter_id`) |
| Human ratings on the golden set | A `named::<score name>` entry in each golden run's `requirement_ratings` |
| A judge | An `EvalConfig` under the eval, set as the eval's `current_config_id` |
| Results | An `EvalRun` per (dataset item × run config) under the judge |

The tag names are not free-form: `generate_spec_eval_tags` in
`libs/server/kiln_server/utils/spec_utils.py` derives all three from the eval's name by
lowercasing and replacing spaces with underscores. The eval name therefore fixes the tags,
and picking it is the only naming decision in this phase.

The named-score rating widget appears on a run's page only when the run carries the golden
tag — `get_rating_options` in `libs/server/kiln_server/task_api.py` returns each eval's
output scores with `show_for_tags=[golden_set_tag]`. So golden runs must be tagged
*before* they can be rated, and the tagging order matters.

## Steps

Each numbered group ends in a `snapshot` and a `git diff` review, per architecture.md's
resumability rule.

### 1. Connect OpenRouter through the UI

Settings → Providers → OpenRouter → paste key → Connect. Phase 2's sandbox no longer has
it — the sandbox's `settings.yaml` as found at the start of this phase held only
`projects`, `user_type` and `personal_use_contact`, i.e. exactly what `write_seed_settings`
writes — so the key is pasted again. Nothing here reaches the fixture.

### 2. Create the eval (and, with it, the spec)

Evals → Create Eval → **Create Manually** (the Kiln Eval Builder column needs a Kiln Pro
account, which the container cannot reach) → template **Desired Behaviour** under Task
Behaviour → the spec form.

- **Eval Name:** `Escalation Flagging`. Short, filename-safe, and it fixes the three tags
  to `eval_escalation_flagging`, `train_escalation_flagging`, and
  `eval_golden_escalation_flagging`.
- **Desired Behaviour Description:** the required field — that `needs_human_review` must be
  true for tickets involving security, data exposure, billing disputes or legal risk, and
  false for routine requests.
- **Correct / Incorrect Behaviour Examples:** both optional, both filled, so the fixture
  exercises a fully-populated `SpecProperties` rather than the minimum.
- Leave priority and "Evaluate Complete Agent History" alone; the structured task has no
  agent history to evaluate.

`Desired Behaviour` is chosen over the alternatives because it needs no external service:
`appropriate_tool_use` requires a tool, and `reference_answer_accuracy` maps to the `rag`
eval template, which replaces the golden-set/judge-comparison steps this phase is meant to
populate.

Snapshot and commit: the spec and the eval, both empty of data.

### 3. Eval data — tag existing runs

From the eval page, **Add Eval Data** → **Manually Tag Existing Data**, which is the
in-flow UI path for reusing a dataset that already exists. Then from the Dataset screen,
bulk-select and tag the 15 structured runs:

- **eval set** (`eval_escalation_flagging`) — the majority.
- **golden set** (`eval_golden_escalation_flagging`) — the rest, disjoint from the eval
  set, and chosen from the runs whose outputs make an unambiguous pass/fail call so the
  human ratings below are defensible.

The bulk tag menu is the one from phase 2's finding: `Add Tags` matches both the menu item
and the dialog's disabled submit, so `find` first and click the returned ref rather than
locating by label.

The eval page will still say more data is suggested — `MIN_DATASET_SIZE` is 25 in
`[eval_id]/+page.svelte` and the fixture has 15 structured runs. That is accepted, not
worked around: functional_spec.md fixes the fixture at 15–20 runs, and generating 50 more
to silence a suggestion would triple the fixture to satisfy a hint. Recorded as a
deviation.

Snapshot and commit.

### 4. Human ratings on the golden set

From the eval page, **Rate Golden Dataset**, which opens the dataset filtered to the golden
tag. Open each golden run and set the `Escalation Flagging` pass/fail rating, spread across
both values so the judge comparison has signal in both directions.

Every golden item must be rated, or `count_human_evals` counts it unrated and the eval page
stays on step 3. Some golden runs already carry a 1–5 overall rating from phase 2; the named
score is a separate control and the overall value must come out unchanged.

**Phase 2's rating-widget finding applies here.** The star widget toggles — clicking a set
star clears it — so any rating that has to be re-set takes two clicks, and the value must be
read back afterwards rather than assumed. Check each golden run's overall rating in the
snapshot diff against the table in phase 2's plan.

Snapshot and commit.

### 5. The judge

Compare Judges → **Add Judge**:

- Algorithm **LLM as Judge**, not G-Eval. G-Eval sets `requires_logprobs`, and whether
  OpenRouter returns logprobs for this model is unknown. If LLM as Judge works, that
  question is not worth a paid experiment; if it fails, say so rather than guessing why.
- Model `deepseek/deepseek-v4-flash-0731` through OpenRouter.
- Leave the generated evaluation instructions as the template produced them.

Then **Run All Evals** on the judge to score the golden set, and **Set as Default** so
`eval.current_config_id` points at it — without that the eval page never advances to the
run-config step and `associated_spec()`-driven screens show "Not Ready".

Snapshot and commit.

### 6. Results across both run configs

Compare Run Configurations → run the eval for the two structured run configs named in
phase 2:

- `177167545173` Zero Shot Baseline
- `293284619675` Chain of Thought

This executes each eval-set item under each run config and judges the output, producing
`EvalRun` records under the judge. Two configs is what functional_spec.md asks for and what
makes the comparison screen worth opening; the third structured config
(`140414461876` Playbook with Prose Input) is included only if the first two complete
cheaply, and its inclusion or exclusion is recorded below either way.

Snapshot and commit.

### 7. Final verification

`reset` to the committed fixture, land in the app, and walk the eval screens confirming
each renders what was authored. Then `grep -r sk-or-v1` the working tree, stop the server,
and run `uv run ./checks.sh --agent-mode`.

## Tests

No automated tests, and this is a decision rather than an omission: architecture.md's
"Testing strategy" rejects a pytest that loads the fixture, because `verify_seed_loaded`
catches the same rot at the moment an agent would be confused by it, without a test whose
failure mode is a red CI on an unrelated PR. Verification for this phase is:

- After each group, `snapshot` leaves a diff containing only files under
  `.agents/playwright_project/`, reviewed before moving on.
- `reset` from the committed fixture at the end, then confirm through the browser:
  - The Evals list shows `Escalation Flagging` with a judge and a dataset size.
  - The eval page sits on the final step, with no "Not Ready" and no unrated golden items.
  - Compare Judges shows the judge with a correlation score against the human ratings.
  - Compare Run Configurations shows a score for each run config.
  - The spec page shows its properties, its Eval ID, and `Eval Status: Ready`.
- `python -c` load of every golden run's `task_run.kiln` confirming the phase 2 overall
  ratings are unchanged and a `named::Escalation Flagging` rating was added.
- No occurrence of the OpenRouter key anywhere in the working tree.
- `uv run ./checks.sh --agent-mode` with the sandbox server stopped, because its vite and
  backend starve `app/web_ui/src/lib/stores/jobs_store.test.ts` past its 5s timeout.

## What was authored

_Filled in as the phase runs._
