---
name: improve_task
description: |
  Mode for making an existing AI agent better — quality, cost, speed, model selection, experiments, tools and skills, fine-tuning, local/on-prem deployment. Enter when the user wants to improve or compare. It routes to the knowledge that owns each question.
---

For chat clients working with a user. A non-interactive agent with its own instructions does not need this file.

# Mode: Improve Task

Make an existing agent better: its quality, cost or speed, its model, its tools and skills. This mode states no method of its own. It finds the task, then sends you to the file that owns each question:

- **What to try, in what order, and when**: the playbooks, smells and techniques, from `references/improving_agents/index.md`.
- **How to change one part of a run config as an experiment**: its lever, from `references/levers/index.md`.
- **How to do it in Kiln** (request bodies, name rules, traps, app links): the knowledge file of that feature, in the table at the end.
- **How to measure a change, judge it and keep it**: `references/client_guidance/chat/running_an_experiment_from_chat.md`.
- **The split rule and the leak rules**: `references/knowledge/train_val_test.md`.

## Two paths

- **Experimentation at scale** (many rounds, "take it as far as it goes", a search over many ideas) goes to Kiln Harness Tuner: recommend it to the user. Never manage many waves of experiments yourself. `references/client_guidance/chat/running_an_experiment_from_chat.md` ("Two paths").
- **One or two clear ideas** are done in the chat, with the by-hand procedure of `references/client_guidance/chat/running_an_experiment_from_chat.md`.

## Task context

Before any API call in this mode, resolve `(project_id, task_id)`. Never guess project or task IDs.

1. Load the task_summaries endpoint doc and pull the full workspace in one call:

   ```
   # read first: references/knowledge/api_docs/get_api_task_summaries.md
   call_kiln_api("GET", "/api/task_summaries", jq_filter="[.projects[] | {pid: .id, project: .name, tasks: [.tasks[] | {tid: .id, name}]}]")
   ```

2. **Exactly one match** → proceed with that `project_id` and `task_id`.
3. **Several matches, or only a close one** → list the candidates with project context and deep links, and ask the user to confirm. Never proceed silently with a near-match (e.g., "content classifier" → "Email Classifier").
4. **No match** → tell the user no task with that name was found and ask.

After two replies spent on finding the task, list the final candidates with deep links and read the knowledge of the request, so that the user's pick lands you ready to work.

Once the task is known, take the snapshot in one call, and trust it as the inventory for this mode (specs, run configs, prompts, tool servers, skills, dataset counts, connected providers) rather than fetching each again:

```
# read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_agent_overview.md
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/agent_overview")
```

Every resource URL begins with `/api/projects/{project_id}/...`; there is no `/api/tasks/{task_id}` and no `/api/run_configs`. `run_configs` has list, create and PATCH (name, starred, prompt name) only: there is no GET of one run config, so list them and filter by id. When no catalogue lists a path, the endpoint does not exist.

At the start, ask what is not yet known: the goal (quality, cost, speed, a model, privacy), the restrictions, the models allowed, and a spend limit. Read the project's memory first (`references/knowledge/memory.md`, "Orientation"): never ask what is already answered there. A request that could fan out over many projects, tasks or run configs gets one question on its scope before any wide scan.

## The usual path for a one-off

1. `references/knowledge/diagnose_an_agent.md`: read the agent, its scores on train and its failing train items.
2. The playbook that fits, through `references/improving_agents/index.md`. Inside the knowledge the path is a smell or a playbook, then a technique, then the lever it uses. Prefer a playbook.
3. `references/client_guidance/chat/running_an_experiment_from_chat.md`: build, measure, confirm and keep.

Do not build an eval in the middle of another request. When no eval measures the user's problem, list the gap, and build the eval only when the user agrees (`references/knowledge/create_eval.md`).

## Routing by what the user asks

| The user asks | Start from |
|---|---|
| Make it better; fix a named problem | `references/knowledge/diagnose_an_agent.md`, then the failure playbook that fits |
| Many rounds of experiments; take it as far as it goes | The Kiln Harness Tuner path of `references/client_guidance/chat/running_an_experiment_from_chat.md` |
| Cheaper or faster | [cheaper or faster](references/improving_agents/playbooks/cheaper-or-faster.md), with `references/knowledge/model_work.md` |
| Which model is best; compare these run configs | `references/client_guidance/chat/running_an_experiment_from_chat.md` ("Variants"), with `references/knowledge/model_work.md` and [model swap inside a class](references/improving_agents/techniques/model-swap-inside-a-class.md) |
| The scores jump, all pass, none pass, the judge looks wrong | The eval playbook that fits (`references/improving_agents/index.md`, "Eval problems"), then `references/knowledge/judge_types.md` or `references/knowledge/create_eval.md` for the change |
| A provider, origin or privacy limit; a local model | [working inside restrictions](references/improving_agents/playbooks/working-inside-restrictions.md), `references/knowledge/local_private_on_prem.md` |
| Add a tool, a skill, retrieval, a sub-agent | The knowledge file for the setup (`references/knowledge/tools.md`, `references/knowledge/code_tools.md`, `references/knowledge/adding_skills.md`, `references/knowledge/rag.md`, `references/knowledge/subagents.md`), the lever (`references/levers/index.md`), and the technique or smell that says when it helps |
| Fine-tune | `references/knowledge/fine_tuning.md`, after [ordering work](references/improving_agents/playbooks/ordering-work.md) |
| How did my evals go | `references/knowledge/eval_scores.md` |
| Run my evals | `references/knowledge/specs_and_evals.md` ("Running an eval"), then `references/knowledge/eval_scores.md` |
| Add an eval; choose a judge | `references/knowledge/create_eval.md`, `references/knowledge/specs_and_evals.md`, `references/knowledge/judge_types.md` |
| Synthetic data; data for an eval or a fine-tune | `references/knowledge/synthetic_data.md` |
| A data guide | `references/knowledge/data_guides.md` |
| There is no eval yet | An eval first: `references/knowledge/create_eval.md` |

When the request changes to creating project resources that are not about an improvement, route to `references/client_guidance/chat/project_operations.md`; to learning about a feature or an error, `references/client_guidance/chat/learn_about_kiln.md`; when the new goal is unclear, `references/client_guidance/chat/establish_intent.md`.

## Reporting

- **The recommendation first**, then the evidence with the split that each number came from, then the links. End on the recommendation, not on a question; when the user asked for a change, make it and report it.
- **A reply that lists 2 or more run configs** gets the prefilled Compare link of `references/knowledge/eval_scores.md`, with its note that the page shows test scores.
- **External URLs come only from data**: a tool response, or the `online_url` of a help article in `references/docs/`. For a benchmark site, a paper or a model's home page that no response gave, give no URL; say that a search for the name finds it.
- A help article says what a feature does; the knowledge says when to use it.

## Knowledge

**Method**

| File | What it holds; read it when |
|---|---|
| `references/improving_agents/index.md` | The smells, playbooks and techniques, and how to read them: to choose what to try |
| `references/levers/index.md` | The parts of a run config an experiment can change, and the rules of each: before you build a candidate |
| `references/knowledge/diagnose_an_agent.md` | The calls that read the agent, its train scores and its failing items: before you choose a playbook |
| `references/client_guidance/chat/running_an_experiment_from_chat.md` | The two paths, and how to measure, judge and keep a change: before any experiment or comparison |
| `references/knowledge/experiment_costing.md` | The cost of an experiment, lane by lane, from measured usage, and when to ask before you spend: before any eval run or experiment that spends tokens |
| `references/knowledge/train_val_test.md` | Which split may decide what, which call reads which split, the leak rules: before you measure or change anything |
| `references/knowledge/memory.md` | The project's durable memory: at the start of work, and to record lessons, dead ends and new issues |
| `references/knowledge/working_with_project_files.md` | The project's files on disk: before you read or change one |

**Run configs, models, prompts**

| File | What it holds; read it when |
|---|---|
| `references/knowledge/model_work.md` | Model facts, tiers, prices, providers, the model info endpoints: any "which model?" question |
| `references/knowledge/model_create_configs.md` | The create call of a run config, the model and provider check, name rules: to create a run config |
| `references/knowledge/prompt_rewrite.md` | Reading prompts, saved prompts, the prompt types: to make a new prompt |
| `references/knowledge/prompt_audit.md` | A review checklist for a prompt: a new prompt, or a user who asks for a review |
| `references/knowledge/fine_tuning.md` | The fine-tune workflow, datasets, the check before submitting, status: to fine-tune |
| `references/knowledge/local_private_on_prem.md` | Open-weight models for privacy or local use: a local or private deployment |
| `references/knowledge/typesafe_jev.md` | A classification-only provider for judges and closed-set tasks: a classifier or a judge on a decision model |

**Evals**

| File | What it holds; read it when |
|---|---|
| `references/knowledge/eval_scores.md` | The score calls and the split each reads, the paired statistics recipe, scorecards, judge prompts: to read or compare scores |
| `references/knowledge/specs_and_evals.md` | What evals are, the splits, running an eval as a job: to run an eval or explain the pipeline |
| `references/knowledge/create_eval.md` | Eval types, the Eval Builder links, the map from a problem to a type of eval: to add an eval |
| `references/knowledge/judge_types.md` | The judge menu and the code-eval contract: to choose or write a judge |
| `references/knowledge/benchmark_eval_inputs.md` | Benchmark and multi-turn evals, reference data, synthetic-user drives: an eval built on eval inputs |
| `references/knowledge/synthetic_data.md` | Synthetic data, made in the app; never eval data from the chat: before any request to generate or add data |
| `references/knowledge/data_guides.md` | Task data guides, made in the app: what shapes generated inputs |

**Capabilities**

| File | What it holds; read it when |
|---|---|
| `references/knowledge/tools.md` | MCP tool servers, demo tools, wiring a server, tool state: to add or check a tool |
| `references/knowledge/code_tools.md` | Code tools: trust, testing, the dry run, create and attach: to add a Python tool |
| `references/knowledge/code_tool_authoring.md` | A code tool for an agent as an experiment, and the eight wrapper templates: to build a new tool or a wrapper |
| `references/knowledge/subagents.md` | A Kiln task as a tool: to wire a sub-agent |
| `references/knowledge/adding_skills.md` | Project skills, the name limits, attaching one: to add a skill |
| `references/knowledge/rag.md` | Document retrieval setup: to ground the agent in the user's documents |

When no file covers what the user needs, read `references/client_guidance/chat/freeform_help.md` as a last resort.

## See also

When and why, in the knowledge: `references/improving_agents/playbooks/know-the-agent-before-you-plan.md`, `references/improving_agents/playbooks/ordering-work.md`, `references/improving_agents/playbooks/spending-the-budget.md`.
