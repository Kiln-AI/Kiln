---
name: project_status
description: |
  Knowledge for assessing the current state of a project and task — run configs, eval scores, specs, prompts, providers. Loaded by the Project Operations mode.
---
# Project Status

Reference knowledge for assessing the current state of a user's project and task to understand what's set up, what's working, and what to improve.

## Knowledge Required

- `references/knowledge/eval_scores.md` — when reading scores and building the status scorecard
- `references/knowledge/provider_setup.md` — when the user has no connected providers

## API Docs

The bootstrap `agent_overview` snapshot (loaded by the mode's "Starting Work in This Mode" steps) supplies task metadata, run configs, specs, prompts, tool servers, skills, dataset/docs counts, and connected providers. Only the endpoints below are needed for further drill-down from this file.

| Endpoint | Load |
|----------|------|
| GET eval results summary (batch scores, test split: report them as test scores; `references/knowledge/train_val_test.md`) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_eval_results_summary.md` |
| GET runs summaries | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_runs_summaries.md` |
| GET single run details | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_runs_run_id.md` |

## Suggested Questions

If not already established in conversation:
1. **Which project and task?** (the mode's Task Context Discovery resolves it)

## Status Assessment Approaches

### Present from the Bootstrap Snapshot

The mode's bootstrap snapshot (`agent_overview`) is the data source for this scorecard — do not re-fetch. Map fields to the response:

- **Task** → `task.name`, `task.description`, `task.instruction`
- **Run Configs** → `run_configs.items` (id, name, model_name, model_provider, starred)
- **Specs** → `specs.items` (name, spec_type, priority, status)
- **Connected Providers** → `connected_providers`
- **Runs total** → pull from `runs_summaries` length (see below) when the user asks for a count
- **Dataset / Docs counts** → `dataset.total_count`, `docs.doc_count`

### Pull Eval Scores (If Specs Exist)

If `agent_overview.specs.items` is non-empty, load `references/knowledge/eval_scores.md` and call `eval_results_summary` (one call returns `evals_by_id`, `run_configs_by_id`, and `scores_by_run_config_by_eval`).

### Pull Runs Count (If Needed)

```
# read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_runs_summaries.md
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/runs_summaries", jq_filter="length")
```

### Present the Assessment

Build a status overview:

**Task:** {name} — {description}
**Prompt:** {first 200 chars} — [Task settings](http://localhost:8757/settings/edit_task/{project_id}/{task_id})

**Run Configs ({count}):**
| Config | Model | Provider | Starred | Link |
|--------|-------|----------|---------|------|
| ... | ... | ... | ... | [View](...) |

**Specs ({count}):**
| Spec | Type | Priority |
|------|------|----------|
| ... | ... | ... |

**Eval Scores:** (scorecard table if data exists, or "No evals run yet")

**Connected Providers:** {list} — [Provider Settings](http://localhost:8757/settings/providers)

**Runs:** {count} total

### Inspect a Single Run

When the user asks about a specific run (e.g. "what's the data on this run", "show me this run") and you have `project_id`, `task_id`, and `run_id` (from the conversation):

```
# read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_runs_run_id.md
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/runs/{rid}", jq_filter="{input, output: .output.output, rating: .output.rating, usage, created_at, tags, source: .output.source}")
```

Present the result as a small table (Output, Input, Source/model, Rating, Usage, Tags, Created) with a [deep link to the run detail page](http://localhost:8757/dataset/{project_id}/{task_id}/{run_id}/run).

### Identify Gaps and Recommend

Based on the assessment, identify what's missing and suggest next steps. Common gaps and their remedies:

- **No specs** → "You need specs to measure quality. Let's create some." Load `references/knowledge/create_spec.md`
- **No eval data** → "Specs exist but no evals have run. Let's run them." Run them with the eval job of `references/knowledge/specs_and_evals.md` ("Running an eval")
- **Only one run config** → "You only have one config. Let's experiment with alternatives." In a chat with a user, read `references/client_guidance/chat/improve_task.md`
- **Low scores** → "Some scores are below target. Let's investigate." In a chat with a user, read `references/client_guidance/chat/improve_task.md`, which starts from `references/knowledge/diagnose_an_agent.md`
- **No connected providers** → "You need at least one provider." Load `references/knowledge/provider_setup.md`
- **Prompt is short/vague** → "The prompt could use more detail." Load `references/knowledge/prompt_rewrite.md`
- **High cost** → "Costs are high. We could optimize." In a chat with a user, read `references/client_guidance/chat/improve_task.md`
