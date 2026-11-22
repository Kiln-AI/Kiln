---
name: run_an_experiment
description: How to measure a change to an agent, judge it and keep it - the choice between Kiln Harness Tuner and a one-off in the chat, then the by-hand procedure - before you start, the hypothesis, cost, build, measure on train, confirm on val, keep or discard, record and report, and comparisons the user asks for.
---

# Run an experiment

The one statement of how a change to an agent is measured, judged and
kept; other files name this path. What to try is in the playbooks, smells and techniques
(`references/improving_agents/index.md`); how to change each part of a run
config is in its lever (`references/levers/index.md`); the split rule and
the leak rules are in `references/knowledge/train_val_test.md`.

Endpoint docs (read each before its first call):

| Step | Endpoint doc |
|---|---|
| Create a run config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md` |
| Run the task once | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run.md` |
| Start an eval job; wait; read its errors | `references/knowledge/api_docs/post_api_jobs_evals_run.md`, `references/knowledge/api_docs/post_api_jobs_wait.md`, `references/knowledge/api_docs/get_api_jobs_id_errors.md` |
| Per-item results of one split | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_config_run_config_id_results.md` |
| Paired statistics | `references/knowledge/api_docs/post_api_statistics.md` |
| Memory records | `references/knowledge/memory.md` |

## Two paths

Choose the path before anything else.

- **Kiln Harness Tuner**, for experimentation at scale: many waves of
  experiments, managed automatically. It is Kiln's best method; it takes a
  while and can use many tokens. When the user wants an agent taken as far
  as it goes, many rounds, or a search over many ideas, recommend Kiln
  Harness Tuner and say what it does. Even in a chat, never take over the
  management of many waves of experiments yourself.
- **A one-off**, when the user wants to try one or two clear ideas. Do it
  in the chat, with the procedure of this file, and do not start Kiln
  Harness Tuner.

When it is unclear which the user wants, ask. The rest of this file is the
one-off path.

## Words

- **Baseline**: the run config that the experiment starts from, its parent.
  Its id is in the `baseline` record of `references/knowledge/memory.md`;
  on a first experiment, it is the task's default run config, else the
  newest; say which, and write the `baseline` record.
- **Candidate**: a new run config, the baseline with one change.
- **Target eval**: the eval that the change is built to move.
- **Guard eval**: every other eval of the task, which the change must not
  break.

## Before you start

- **The agent is known**: `references/knowledge/diagnose_an_agent.md` has
  the calls, and
  [know the agent before you plan](references/improving_agents/playbooks/know-the-agent-before-you-plan.md)
  what to look for.
- **An eval measures the problem**, with a default judge (the eval's
  `current_config_id`). When there is none, an eval comes first:
  `references/knowledge/create_spec.md`, and the user agrees to it.
- **The eval has a train and a val split.** With only a test split, the
  splits come first (`references/knowledge/train_val_test.md`, "An eval
  with only a test split"); do not go on with the test split.
- **The baseline run config is known**, and it has scores on train.
- **The user gave** the goal, the restrictions (providers, models, data),
  the models allowed, and a spend limit. Ask for what is missing; record
  each answer as a `constraint` (`references/knowledge/memory.md`).

The order is fixed: an eval with a judge, then a run on each split you
need, then a comparison.

## The hypothesis

Write it before you build, as an `experiment` memory ending `— RUNNING`:

- **One change**, through one lever.
- **The failure it fixes**: the issue, and the train items that show it.
- **The target eval**, and the guard evals.
- **The predicted effect** on the target eval, never larger than the room
  the baseline leaves on train (a pass/fail score cannot gain more than the
  baseline's failures). When it is smaller than what the eval can show, or
  than its noise, fix the measurement first:
  [spending the budget](references/improving_agents/playbooks/spending-the-budget.md)
  and [dealing with a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md).

## Cost before you spend

Estimate from this task, never from a list price (it misses cached
tokens, reasoning tokens and turns). Run the target eval on a few train
items first: the eval job with `"split": "train"` and `item_ids`. Read the
recorded usage on the result rows (`task_run_usage`, the judge's
`eval_usage`, and for a multi-turn eval the synthetic user's), and scale it
to the items and evals that the experiment runs on train and val. Tell the
user; above the spend limit, ask before you go on. A later full run reuses
the scores of these items.

## Build the candidate

- **New objects only.** Never change the baseline, or anything it uses, in
  place (`references/knowledge/working_with_project_files.md`).
- **Copy every property of the parent, and change one.** The lever of the
  change gives its rules (`references/levers/index.md`); the calls are in `references/knowledge/model_create_configs.md`,
  `references/knowledge/prompt_rewrite.md`,
  `references/knowledge/adding_skills.md` and
  `references/knowledge/code_tool_authoring.md`.
- **The hypothesis goes in the run config**: its name says the change, and
  its description and `provenance` give the hypothesis, with the parent in
  `derived_from_ids`.
- **Follow the leak rules** of `references/knowledge/train_val_test.md`
  before you measure: search the change for any value of a train item and
  any text of an eval, a judge or a spec.
- **Check that the change took effect**, with the check of its technique
  ("Check that it took effect"): run the candidate once or twice on train
  items that show the failure
  (`references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run.md`)
  and read the trace. A tool never called, a skill never read, an output
  the same as the parent's: the change did not reach the agent. Do not
  measure it; its verdict is "not applied". Fix the build or drop the
  idea.

## Measure on train, and judge

1. Start the eval job on the **train** split for the candidate, the target
   eval first (`"split": "train"`). Run the baseline on the same items when
   it has no scores on them. Wait for the jobs
   (`references/knowledge/api_docs/post_api_jobs_wait.md`).
2. Read the errors of each job
   (`references/knowledge/api_docs/get_api_jobs_id_errors.md`) and the
   coverage: items scored out of items in the split, for each side.
   - Below about 95%, adopt graded caution and check the missing items for
     skew: say which went dark and whether they share anything ("no
     pattern" is a finding too).
   - An eval with no results is missing evidence, never a zero. The same
     job again measures only the missing items; never fill a gap by
     estimate.
   - A guard eval with no results means the candidate usually cannot pass:
     you cannot show that it did not break it.
3. Compare the candidate with the baseline item by item, with the paired
   statistics call: the recipe of `references/knowledge/eval_scores.md`, on
   the train split.
4. Read the candidate's failing and broken items: output, judge's
   reasoning, trace.
5. When the target eval moved, measure the guard evals on train too.
6. Give the verdict:
   - **Candidate**: the target eval improved on train and no eval is
     clearly worse. A gain with low significance can be a candidate, with
     the caution said: the confirmation on val is the real test. When the
     target eval has no results, or too few to read, it is a candidate only
     with direct evidence that you cite (the traces you read) and a
     re-measure as the next step: never on absent numbers alone.
   - **At the ceiling**: when the baseline leaves room for only one or two
     items, a significant result is impossible. A candidate that passes
     every target item, breaks none, and fixes items the baseline always
     fails, with a mechanism you traced, is a candidate; say the caution.
   - **Refuted**: clearly past the noise, the change did not help, or it
     broke an eval.
   - **Inconclusive**: inside the noise; not refuted. The eval may be too
     small: say "enlarge the eval", not "it does not work".
   - **Not applied**: the change did not reach the agent (above).

A missed prediction is a caution, not a verdict. Judge the size of a gain
against the room that the baseline left, not against the prediction.

## Confirm on val

For a candidate only. Run the evals on the **val** split, for the candidate
and for the baseline (`"split": "val"`), and read the result by metrics
only: the summary numbers that `references/knowledge/train_val_test.md`
lists, coverage included, and nothing at item or trace level.

Missing val results are missing evidence, not zeros. When the target eval
has none on val, the candidate is not kept, unless all three hold: its
train evidence on that eval is overwhelming and significant; every guard
eval measured on val holds; and your report says that val is missing and
that the decision rests on train. A guard eval with no val results is
weighed as missing evidence. Never write "no regressions" for an eval that
was not measured. With low coverage on the eval that decides, prefer a
fully measured candidate close behind.

Before you decide, read the project's `OPEN: ` constraints
(`references/knowledge/memory.md`). When keeping the candidate would
settle, contradict or bet on the default assumed for an open question that
the user has not answered, ask the user first. Until the answer, keep no
winner and do not mark the candidate rejected: it waits unchanged. Record
the answer in the `OPEN: ` record, then decide on the numbers.

Then apply the keep rule:

- The target eval is clearly better on val.
- No eval is clearly worse. A higher-priority eval comes before a lower
  one: no number of small wins on low-priority evals makes up for a drop on
  a high-priority eval.
- Cost and latency are a separate axis, never folded into a score. When
  the user's goal is cost or speed, the candidate must be clearly cheaper or
  faster, and no worse on quality. Kiln Harness Tuner defines both halves
  exactly (a paired test of cost or latency, a pooled rule on quality);
  that exact rule applies when running it.
- One winner, or none. None is a valid outcome.

Confirm a candidate once, and keep exactly what was measured. Do not tune
on val: nothing that you see on val goes into a change. When val rejects a train win, read
[dealing with train wins rejected at validation](references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md).

The user may waive the confirmation on val. Then mark every result of the
work "train only".

## Keep or discard

- **Keep**: the candidate becomes the baseline of the next experiment.
  Update the `baseline` record, and the `val` record with the summary line
  (`references/knowledge/memory.md`). Close the target issue with
  `FIXED: ` and a line that names the fix, unless it did not really close
  (a partial win, or a gain from elsewhere): then say so in its content and
  leave it open. For a `FIXED: ` issue whose eval got worse on val, add a
  line, with no val number, that it repeats on the new baseline, and ask
  the user about reopening it. Never change the task's default run config:
  tell the user that they can set it.
- **Discard**: the objects stay, as the history of what was tried. Do not
  archive or delete them.
- **Next**: a refuted or inconclusive step goes back to its playbook; a
  rejection at val goes to
  [dealing with train wins rejected at validation](references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md);
  when the eval itself looks wrong, saturated, near zero or noisy, read the
  eval playbooks of `references/improving_agents/index.md`.

## Record and report

One record per experiment, written as you go (`references/knowledge/memory.md`):
the hypothesis, the run config ids, the train result, the outcome on val
in words (the suffix `— PROMOTED` or `— REJECTED AT VAL`, with the reason
of the rejection), the verdict and the next step. The val numbers go only
in the `val` record. A refuted approach is a `dead_end`.

To the user: the recommendation first; then a table per eval with both
scores, the coverage, the significance and the split of each number; then
the links to each run config, and the Compare page with the note that it
shows test scores. No number of the test split.

## Variants

- **A comparison of run configs that the user named** ("which model is
  best"): run each on the same train items, compare with the paired
  statistics call, then confirm the best one on val. Ask the user before you
  create 3 or more run configs.
- **Two candidates at once**: each is one change from the same parent.
  When both win, the two changes together are a new candidate, built and
  measured as one, and confirmed on val like any other.
- **No eval yet**: an eval comes first (`references/knowledge/create_spec.md`).
- **More than this** (many waves, many ideas, a search over models): the
  Kiln Harness Tuner path of "Two paths" above.
