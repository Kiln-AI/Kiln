---
name: diagnose_an_agent
description: The Kiln API steps that read what the knowledge tells you to look at before you change an agent - the agent as it is, what the smells measure, the scores on train, and the failing train items with their traces. Read it before you choose a playbook or plan an experiment.
---

# Diagnose an agent

This file holds the calls that read the evidence. What to look for in it,
how to name a failure and what to do about it are in the smells and the
playbooks (`references/improving_agents/index.md`). It reads train items
only: the split rule is in `references/knowledge/train_val_test.md`.

Read each endpoint doc before the first call. `{project_id}` and `{task_id}`
come from the task context (in a chat with a user, that of
`references/client_guidance/chat/improve_task.md`).

## The agent as it is

What [know the agent before you plan](references/improving_agents/playbooks/know-the-agent-before-you-plan.md)
and the "What it is" part of each lever ask for.

1. **The snapshot.** `GET /api/projects/{project_id}/tasks/{task_id}/agent_overview`
   (`references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_agent_overview.md`):
   the task, its default run config, its run configs, prompts, specs,
   tools, skills, the dataset counts and the connected providers.
2. **The task.** Its instruction, and its input and output schemas. The
   snapshot cuts a long instruction: read the whole task with
   `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id.md`.
3. **The baseline run config.** `GET .../run_configs`
   (`references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md`),
   with a `jq_filter` on the baseline's id: the model and provider, the
   settings, `structured_output_mode`, the tools in `tools_config`, and the
   frozen `prompt` that it sends. Which run config is the baseline is in
   `references/knowledge/memory.md`.
4. **The tools.** For each tool id of the run config, its definition, as
   the model sees it:
   `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_tools_tool_id_definition.md`.
   The tool servers and their state: `references/knowledge/tools.md`
   ("Checking Tool State").
5. **The skills.** `references/knowledge/api_docs/get_api_projects_project_id_skills.md`
   for the name and description of each skill that the run config
   attaches; `references/knowledge/adding_skills.md` reads a skill's body.
6. **The evals and their judges.** `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals.md`:
   each eval, its default judge (`current_config_id`) and its split
   filters. The judge's prompt: `references/knowledge/eval_scores.md`
   ("Viewing and Editing Judge Prompts").

## What the smells measure

The smells that give a number say what to measure and the reference value;
these are the calls that return each value.

- **The prompt and its length.** The frozen `prompt` of the run config is
  the text that it sends. When the run config names a prompt generator in
  place of a saved prompt, render it with
  `GET /api/projects/{project_id}/tasks/{task_id}/gen_prompt/{prompt_id}`
  (`references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md`).
  Count its characters.
- **The tool descriptions and the number of tools**: the definitions of
  step 4 above; count the tools that the run config attaches.
- **The skill descriptions**: step 5 above.
- **The release date of the model**: `GET /api/model_info/model_details`
  (`references/knowledge/api_docs/get_api_model_info_model_details.md`),
  its `release_date`, and `release_date_estimated`.

## The scores on train

What [ordering work](references/improving_agents/playbooks/ordering-work.md)
and the eval playbooks read: where the baseline stands today, per eval.

For each eval, read the baseline's per-item results on the train split:
`GET .../evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results`
with `query_params={"split": "train"}`
(`references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_config_run_config_id_results.md`),
with the default judge. Take the score of each item with a `jq_filter`
first, not the traces. When the baseline has no train results yet, run them
(`references/knowledge/specs_and_evals.md`, "Running an eval", with
`"split": "train"`).

Show the user a scorecard of where the task stands today: one row per
eval, with the pass rate or mean score on train, the items scored out of
the items in the split, and the link of the eval. Say that the numbers are
train numbers. An eval with no judge, or no train split, is a gap: list it
(`references/knowledge/train_val_test.md` when the eval has only a test
split).

## The failing train items

What the failure playbooks ask you to read. For each failing train item of
the target eval, from the same results call, read:

- the output (`output`) and the trace (`task_run_trace`): which tool calls
  came before the failing message, and what they returned;
- the judge's scores and its reasoning (`eval_run.scores`,
  `eval_run.intermediate_outputs`, and `eval_run.judge_trace`);
- the expected output. For an item of the dataset (`eval_run.dataset_id`),
  read its task run:
  `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_runs_run_id.md`
  (`references/knowledge/project_status.md` shows one run and its trace).
  For an eval input (`eval_run.eval_input_id`) of a benchmark or
  multi-turn eval, read the eval input, with its reference data:
  `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_eval_inputs_eval_input_id.md`
  (`references/knowledge/benchmark_eval_inputs.md`). For a multi-turn item,
  the trace is the driven conversation.

Read a few items in full before you group them. Narrow the answer with
`jq_filter` to the failing items, or save it with `save_to_tmpfile` and read
it there: traces are large.

## Where to go next

`references/improving_agents/index.md`: a smell or a playbook that fits what
you found, then, in a chat with a user,
`references/client_guidance/chat/running_an_experiment_from_chat.md`
to measure the change.
