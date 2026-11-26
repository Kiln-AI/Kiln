---
name: train_val_test
description: The split rule for improving an agent - tune on train, confirm on val by metrics only, never read test - which call and which app page reads which split, what to do when an eval has only a test split, and the leak rules for every change.
---

# Train, val and test

Each eval of a task can have three splits, `train`, `val` and `test`. A
split's items are EvalInputs, selected by an eval-input filter, or task runs,
selected by a dataset filter; the filter is most often a tag. The eval's
`splits` gives each split's `source` (`eval_input` or `task_run`) and
`filter_id`. The
splits must not share an item, and Kiln does not check that they do not: when you
see an item in two splits, tell the user. This file is the one statement of
how an improvement uses them. Other skill files name this path; they do not
state the rule again.

Kiln does not enforce the rule. Every endpoint answers for the split you ask
for, the test split included. You apply the rule.

## The rule

| Split | What reads it | What it may decide |
|---|---|---|
| `train` | Every design, screening and experiment measurement, and your judgement of it | Everything you learn: experiments, issues, lessons, verdicts |
| `val` | The confirmation of a winner, by metrics only | Which run config becomes the baseline |
| `test` | Nothing in the work, ever | Nothing |

- **Tune on train.** Design each change on train items and train results.
  Measure each experiment on train. Read train items, outputs, traces and
  judge reasoning as much as the work needs.
- **Confirm on val, by metrics only.** Val confirms a train winner before it
  becomes the baseline. On val, read summary numbers only, never item-level
  or trace-level val detail: no val input, output, trace or judge reasoning
  goes into what you read, write, record or report. The summary numbers are
  the scores of the candidate and of the baseline on each eval, the change
  between them and whether it is significant, the coverage, the cost and
  the latency. Do not tune on val: nothing that you learn on val goes into
  a change.
- **Never read test.** Do not run the test split, read its results, or
  compare or keep a candidate on a test number. The test split is the
  user's own final check, after the work. A number that the tuning never
  optimized against stays a true measure.

The reason is the flow of information. A record or a change made from val
items lets later work steer toward val, and val stops being a fair
confirmation. A test number that you read is a number that you optimize
against.

## Which call and which page reads which split

| Call or page | Split it reads | For train or val |
|---|---|---|
| Start an eval job: `references/knowledge/api_docs/post_api_jobs_evals_run.md` | The `split` you give. It is required | `"split": "train"` or `"split": "val"` |
| Results of one run config: `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_config_run_config_id_results.md` | The `split` query parameter. It is required | `query_params: {"split": "train"}`. On val, read summary numbers only: set `jq_filter` so that the answer holds them, not the rows |
| Paired statistics: `references/knowledge/api_docs/post_api_statistics.md` | The scores you send | On train, send the per-item scores of the results call |
| Score summary of a judge: `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_score_summary.md` | Test, with no `split` argument | Do not use it. Use the results call with `split` |
| Eval results summary of a task: `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_eval_results_summary.md` | Test, with no `split` argument | Do not use it for scores. Use the results call with `split`, for each eval |
| Eval scores of the run configs: `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_eval_scores.md` and `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md` | Test, with no `split` argument | Do not use them. Use the results call with `split`, for each eval |
| Run a comparison: `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_comparison.md` | Runs and scores the test split | Do not use it. Start an eval job with `split` |
| Eval progress: `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_progress.md` | Its `dataset_size` is the size of the test split | Read `train_dataset_size` and `val_dataset_size` |
| The Compare page: `http://localhost:8757/specs/{project_id}/{task_id}/compare` | Test scores, and it runs the test split | No page shows train or val scores. Read them with the results call |
| A spec page: `http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}`, its eval pages, and `http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}/{eval_id}/compare_run_configs` | Test scores, and the size of each split | The same |
| A legacy eval page: `http://localhost:8757/specs/{project_id}/{task_id}/legacy/{eval_id}` | The size of each split | The same |

When you give the user a link to one of these pages, say that its scores
are test scores, so the user does not take them as the result of your
experiment.

## An eval with only a test split

Add the train and val splits first, with the user. Do not go on with the
test split: no measurement, comparison or choice on it. Which items go in
which split is a decision about what the eval measures, so it is the
user's.

- `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_evals_eval_id.md`
  sets a train split on an eval that has none, once, with
  `train_set_filter_id` (a dataset filter, for example `tag::<tag>`). The
  split it adds holds task runs ("Which items each way of making an eval
  saves" below).
  Ask the user first, and name the items it selects.
- No endpoint and no app page adds a val split to an existing eval.

So tell the user that the eval has no val split, and offer the two choices.
The user chooses; do not choose for them:

- **Make the eval again with the Eval Builder**, at
  `http://localhost:8757/specs/{project_id}/{task_id}/builder`
  (`references/knowledge/create_eval.md`). An eval that the Eval Builder
  makes has a train, a val and a test split, unless the user picks its
  test-only size.
- **Add a train split only, and waive the confirmation on val.** Add the
  train split with the call above. Mark every result of the work "train
  only".

## Which items each way of making an eval saves

- The guided Eval Builder (Kiln Pro) saves eval-input splits: the split's
  `source` is `eval_input`.
- The form for a template, the form for a check and the API
  (`references/knowledge/create_eval.md`) save task-run splits: the split's
  `source` is `task_run`, and a dataset filter selects the items.
- The `train_set_filter_id` of
  `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_evals_eval_id.md`
  adds a task-run split, even when the test split holds EvalInputs.

Read each split by its `source` and `filter_id`.

## The leak rules

A change is a prompt, a skill, a tool, a tool description or any other text
or code that the agent runs with. Every change follows these rules, and the
levers repeat them as hard limits:

- **No value from a train item goes into a change**: no item id, number,
  sentence, input or expected value. Search each change for copies before
  you measure it.
- **No rule that games the measurement**: no rule case by case, and no
  wording aimed at a grader. A general rule that a new input of the same
  kind also follows is fine. Naming a tool or a skill is fine.
- **No text copied from an eval, a judge or a spec**: no run of 8 or more
  words from a judge prompt, an eval config, a spec or an eval
  description, and no eval's full name. Search the whole change: the
  prompt, and every file of its skills and code tools. Text that the
  baseline's prompt or the task's instructions already carry is exempt
  (for a skill or a code-tool file, the baseline's whole text). The parent
  is not exempt: a phrase that an earlier candidate put in its prompt is
  found in every candidate built on that prompt. State a rule in new
  words, from what the task needs.
- **An example in a change uses invented values**, never the values of an
  item.
