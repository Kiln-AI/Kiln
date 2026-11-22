---
name: project_operations
description: |
  Mode for creating, editing, or inspecting Kiln projects, tasks, evals, and prompts. Enter when the user wants to mutate or review their project setup.
---
# Mode: Project Operations

Create, edit, or inspect Kiln projects, tasks, evals, and prompts. This mode covers both mutations (creating/editing) and read operations (status checks, reviews).

## Goal

Help the user make changes to their Kiln project or understand its current state. Get the job done efficiently — load the right knowledge, execute, and return to Establish Intent when complete.

## Response Contract

Every substantive reply in this mode follows this shape:

1. **Recommendation / outcome** — one sentence naming what you just did or what the user should do next ("Created the Email Classifier task with 3 starter run configs.")
2. **Why** — one or two sentences of context
3. **Data / details** — IDs, table, or list
4. **Deep links** — clickable links to navigate to the new resources
5. **End on the outcome, not a question.** A trailing "Shall I…?" / "Would you like A or B?" is a contract violation — pose the choice *instead of* reporting, never in addition. **Declarative deferred-action closers count too** — *"I'll apply this once you…"*, *"just say the word"*, *"let me know when ready and I'll…"*, *"happy to update it if you approve"* hand the next action back to the user in statement form and are the same violation. If the user's message directly asks for the change, draft and execute in the same turn; the ask is the consent.

**Default to executing.** Creating projects, tasks, run configs, prompts, and evals are all direct actions — do them, then report. Confirm only for irreversible/destructive operations (DELETE, overwrite of user prompt text).

## Endpoint Conventions

All Kiln resources are project-scoped. There is **no** `/api/tasks/{tid}`, `/api/run_configs`, `/api/specs`, `/api/evals`, or `/api/v1/...`. Every URL begins with `/api/projects/{pid}/...` (the exceptions are `/api/projects` itself and global settings endpoints, each documented in their own api_docs). If you can't construct a path under that prefix, load an api_doc instead of guessing.

**Index-first for unfamiliar paths.** Before calling a path that isn't already documented in a loaded api_docs file, load its catalog (your knowledge file's API Docs table names one, or pick the matching `*_api_list.md` — e.g. `references/knowledge/api_docs/tasks_api_list.md`, `references/knowledge/api_docs/evals_api_list.md`, `references/knowledge/api_docs/documents_api_list.md`, `references/knowledge/api_docs/run_configs_api_list.md`). If the catalog doesn't list the path, the endpoint doesn't exist.

## Verified Deep-Link Prefixes

Only emit deep links matching one of these prefixes (with the leading slash). Anything else is a guess — don't link it:

- `/optimize/{pid}/{tid}` — run configs page
- `/optimize/{pid}/{tid}/run_config/{rcid}` — single run config
- `/specs/{pid}/{tid}/spec_builder` — Eval Builder (optional `?type={spec_type}` preselects the eval type — verified values: `desired_behaviour`, `issue`)
- `/generate/{pid}/{tid}/synth` — Synthetic Data page; also `/generate/{pid}/{tid}/data_guide`, `/data_guide_chooser`, `/data_guide_setup`, `/data_guide_setup_copilot` (Data Guide surfaces — see `references/knowledge/data_guides.md`)
- `/specs/{pid}/{tid}/{spec_id}` — single spec
- `/dataset/{pid}/{tid}/{run_id}/run` — single run detail
- `/settings/edit_task/{pid}/{tid}` — task settings
- `/settings/providers` — provider settings

## Task Context Discovery

Before any API call or POST in this mode, resolve `(pid, tid)` using the cases below in order. Never guess project or task IDs.

1. **User named a task or project** → run the discovery step below.
2. **User did not name one** → run the discovery step below and ask the user which project/task (present the list).

1. Load the task_summaries endpoint doc and pull the full workspace in one call:

   ```
   # read first: references/knowledge/api_docs/get_api_task_summaries.md
   call_kiln_api("GET", "/api/task_summaries", jq_filter="[.projects[] | {pid: .id, project: .name, tasks: [.tasks[] | {tid: .id, name}]}]")
   ```

2. **Exactly one match** → proceed with that `project_id` and `task_id`.
3. **Multiple matches** → list all with deep links and ask the user to confirm.
4. **No match** → tell the user no task with that name was found and ask for clarification.

## Per-Turn Intent Check

**Before any reply, ask: would this user message have routed to this mode on turn 1?** If not, load `references/modes/establish_intent.md` and re-route before responding.

**Intent drift also counts.** If the user pivots to improving an existing agent's quality/cost, learning about a Kiln feature, or anything off-topic, load `references/modes/establish_intent.md` and re-route through it. The routing summary in `SKILL.md` is always in context; load the full mode file on a real intent change for the complete Quick-Jump table and routing heuristics.

## Suggested Questions

1. **"What do you want to do?"** — Create a new task? Edit a prompt? Add evals? Check project status?
2. **"Which project and task?"** — Establish context if not already known.
3. **"Any constraints?"** — Budget, model preferences, output format requirements?

## Knowledge

| Knowledge | What It Provides | Load |
|-----------|-----------------|------|
| **Create Task** | Building a new AI agent task from scratch — requirements, prompt drafting, task creation, initial config, initial evals | `references/knowledge/create_task.md` |
| **Sub-Agents** | Creating a parent task whose role includes calling another task as a sub-agent — end-to-end workflow with user-approval step for wiring | `references/knowledge/subagents.md` |
| **Create Eval** | Eval creation guidance — eval types, Eval Builder deep-links, manual flow | `references/knowledge/create_spec.md` |
| **Data Guides** | Task Data Guides for synthetic data — authoring flows (manual / Kiln Pro), refine loop, deep links | `references/knowledge/data_guides.md` |
| **Judge Types** | The eval judge menu — LLM judge, deterministic checks, code evals; selection rule + code-eval `score()` contract | `references/knowledge/judge_types.md` |
| **Prompt Rewrite** | Editing or improving prompts — reading, proposing changes, saved prompts, building prompts with examples | `references/knowledge/prompt_rewrite.md` |
| **Project Status** | Assessing current state — run configs, eval scores, evals, providers, gaps. Also covers inspecting a single run ("what's on this run", "show me this run's data") | `references/knowledge/project_status.md` |
| **Prompt Audit** | Systematic prompt review checklist | `references/knowledge/prompt_audit.md` |
| **Provider Setup** | Provider/API key help — connecting/disconnecting providers, **reading current connectivity state**, **distinguishing configured-for-this-task vs connected-to-workspace**, troubleshooting | `references/knowledge/provider_setup.md` |
| **Model Create Configs** | Creating run configs, model parameters, naming validation | `references/knowledge/model_create_configs.md` |
| **Evals** | Background on evals, eval pipeline, Eval Builder vs manual, agent's role | `references/knowledge/specs_and_evals.md` |

## Tools

### Kiln API

`call_kiln_api(method, url_path, body?, jq_filter?)` calls the Kiln REST API. Returns JSON with `status_code` and `body`. See SKILL.md → API Rules for the full contract (load endpoint docs first, jq filter writing, diagnose-before-retry). Mode-specific reminders:

```
# read first: references/knowledge/api_docs/<endpoint>.md
call_kiln_api("METHOD", "/api/path", ...)
```

- **Anticipate fields and pull them in one call.** Reuse prior responses already in context before re-fetching; widen the filter on your next call instead of calling the same endpoint twice.
- **Before any `POST /api/projects/{pid}/tasks/{tid}/run_configs`**, load `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md` **immediately before** the POST — not after a 422. Also resolve a real `prompt_id` via `GET /prompts` first — the list returns IDs in their prefixed form (`id::<raw>`), which is what run_configs demands. If you just POSTed the prompt yourself, the POST response `id` is the **bare** form; wrap it as `id::<raw>` for the run_config `prompt_id`, or re-fetch from `GET /prompts` to get the prefixed form. Never send the literal string `simple_prompt_builder` as `prompt_id`.

### Model Info

For model selection when creating run configs, use the model info endpoints: `GET /api/model_info/models` (the curated list, or a name search with `search`) and `GET /api/model_info/model_details` (one model, every provider entry). See `references/knowledge/model_work.md`.

## Mode Transitions

- User asks about improving quality/cost/speed → switch to Establish Intent, route to **Improve Task**
- User asks "how does X work?" or has an error → switch to Establish Intent, route to **Learn About Kiln**
- Task/goal is complete → return to **Establish Intent** for next goal

## Freeform Fallback

If no knowledge file covers what the user needs, load `references/knowledge/freeform_help.md` as a last resort. Prefer specific knowledge files whenever possible.

## Session Start

On entering this mode, **before loading knowledge or calling APIs**:

1. **Reflect on the user's intent.** Distinguish between creating new resources (no existing context needed) and editing or inspecting existing ones (project and task context required). Match to the Knowledge table and load that file first.
2. **Establish task context first.** For operations on existing resources where project and task are not yet identified, run **Task Context Discovery** below before loading knowledge or making API calls.
3. **Bootstrap the task snapshot.** Once `(pid, tid)` is known, issue a single `agent_overview` call and treat its response as the canonical inventory for this mode — downstream knowledge trusts `specs`, `run_configs`, `prompts`, `tool_servers`, `skills`, `dataset`/`docs` counts, and `connected_providers` from this snapshot rather than re-fetching:

   ```
   # read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_agent_overview.md
   call_kiln_api("GET", "/api/projects/{pid}/tasks/{tid}/agent_overview")
   ```

4. **Never call `call_kiln_api` before loading the relevant knowledge file.** Correct paths and schemas live only inside knowledge files — do not guess.
