---
name: create_task
description: |
  Knowledge for building a new AI agent task from scratch — gathering requirements, writing the prompt, creating the task, initial run config, and first specs. Loaded by the Project Operations mode.
---
# Create New Task

Reference knowledge for building a new AI agent task from scratch. Covers requirements gathering, prompt drafting, task creation, initial run config, and setting up quality specs.

## Knowledge Required

- `references/knowledge/prompt_audit.md` — when checking the drafted prompt against the audit checklist
- `references/knowledge/model_work.md` — when choosing an initial model
- `references/knowledge/model_create_configs.md` — when creating the first run config
- `references/knowledge/create_spec.md` — when setting up initial quality specs

## API Docs

Load the relevant endpoint doc **before** making each API call.

| Endpoint | Load |
|----------|------|
| POST create project | `references/knowledge/api_docs/post_api_projects.md` |
| GET list projects | `references/knowledge/api_docs/get_api_projects.md` |
| GET project | `references/knowledge/api_docs/get_api_projects_project_id.md` |
| POST create task | `references/knowledge/api_docs/post_api_projects_project_id_tasks.md` |
| GET list tasks | `references/knowledge/api_docs/get_api_projects_project_id_tasks.md` |
| GET task details | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id.md` |
| PATCH update task | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id.md` |
| GET list available providers | `references/knowledge/api_docs/get_api_settings_available_providers.md` |
| GET available models | `references/knowledge/api_docs/get_api_available_models.md` |
| GET provider models | `references/knowledge/api_docs/get_api_providers_models.md` |
| POST create run config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md` |
| GET list run configs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md` |
| PATCH update run config | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_run_configs_run_config_id.md` |
| POST execute run | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run.md` |
| POST create prompt | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_prompts.md` |
| GET list prompts | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_prompts.md` |
| POST create spec | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_specs.md` |
| GET list specs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_specs.md` |
| POST create eval via Eval Builder | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_spec_with_copilot.md` |
| GET list evals | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals.md` |
| POST create evaluator | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_create_evaluator.md` |

## Suggested Questions

1. **What does the agent do?** "Describe what the AI should do — what input does it receive and what output should it produce?"
2. **Input/output format?** Free text, structured JSON, specific schema?
3. **Any constraints?** Cost budget, latency requirements, specific model preferences, privacy needs?
4. **Existing examples?** Do they have examples of good input/output pairs?
5. **Quality dimensions?** What matters most — accuracy, tone, format, completeness?

## Task Creation Approaches

**Quality-motivated arrival.** If you arrived here from `references/modes/improve_task.md` (user wanted to fix a specific quality problem like hallucination, verbosity, or accuracy in a task that turned out not to exist), load `references/knowledge/prompt_audit.md` **before** drafting the prompt — not after. The original quality concern should shape the starter prompt and the suggested initial specs; record it in the task description so future runs carry the context.

### Name validation (applies to projects, tasks, run configs, prompts)

Kiln's server rejects `name` values that contain any of these characters: `/ \ ? % * : | < > . , ; =` or newline; or consecutive whitespace / underscores; or leading / trailing whitespace / underscores. This applies to **every** POST that sends a `name` field — projects, tasks, run configs, and prompts. Before any such POST, strip or replace these characters. Examples:

- `"Email Triage (Urgent/Follow-up/Info/Spam)"` → `"Email Triage 4-Way Sorter"`
- `"GPT-4.1 Mini / OpenAI"` → `"GPT 4 1 Mini OpenAI"`
- `"v2.0 pipeline"` → `"v2 0 pipeline"` (or rename to avoid the `.`)

A 422 "Name is invalid" response wastes a round-trip; sanitize on the first attempt. If the sanitization changes the name's meaning, surface the sanitized form to the user and give them a chance to rename before proceeding.

Saved prompts are referenced by `id::<raw>` in run config bodies — see `references/knowledge/model_create_configs.md` → Getting the Prompt ID for the GET-vs-POST shape distinction and the canonical filter.

### Gather Requirements

The answers to the suggested questions determine the task instruction, I/O schemas, and model recommendation.

### Write the Task Instruction

Draft the task instruction (prompt) based on the requirements. Load `references/knowledge/prompt_audit.md` to check it against the audit checklist before showing to the user.

Show the full prompt and explain key decisions. **Wait for user approval** before creating.

### Create the Task

If the user doesn't already have a project, help them create one first:
```
# read first: references/knowledge/api_docs/post_api_projects.md
call_kiln_api("POST", "/api/projects", body={"name": "...", "description": "..."})
```

**If POST /api/projects returns 400 with a duplicate-name body, do NOT silently reuse the existing project.** List the existing project(s) with that name via `GET /api/projects`, surface them with deep-links, and ask the user whether to (a) use the existing one or (b) pick a different name. Silently swallowing the 400 drops resources into a project the user didn't intend.

Then create the task:
```
# read first: references/knowledge/api_docs/post_api_projects_project_id_tasks.md
call_kiln_api("POST", "/api/projects/{pid}/tasks", body={"name": "...", "instruction": "...", "description": "..."})
```

Deep-link to [Task Settings](/settings/edit_task/{pid}/{tid}).

**Do NOT stop at "task created".** A task without a run config cannot be run — proceed to *Create Initial Run Config* in the same turn, even if earlier steps were interrupted by a project-name conflict or other recovery. The session is incomplete until the user has a clickable `/optimize/{pid}/{tid}/run_config/{rcid}` link.

### Create Initial Run Config

Load `references/knowledge/model_create_configs.md` to choose an appropriate model based on their constraints.

**Strict ordered checklist (do all in order before POSTing a run config):**

1. Read `references/knowledge/api_docs/get_api_settings_available_providers.md`, call it, and confirm the target provider is connected.
2. Read `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_prompts.md`, call `GET /prompts`, and capture a real `prompt_id` from the `prompts` array. The list returns the ID in its prefixed form (`id::<raw>`) — **use it as-is, with the `id::` prefix included**. If you created the prompt in this same turn with `POST /prompts`, the POST response returned the bare form; see **Getting the Prompt ID** in `references/knowledge/model_create_configs.md`. **Never use the literal string `simple_prompt_builder` or any generator name as `prompt_id` — the API will 422.**
3. Sanitize the config name per the **Name validation** rule at the top of this section.
4. Read `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md` **immediately before** the POST — not after a failed attempt.
5. Then POST:

```
call_kiln_api("POST", "/api/projects/{pid}/tasks/{tid}/run_configs", body={"name": "<sanitized>", "run_config_properties": {"type": "kiln_agent", "model_name": "...", "model_provider_name": "...", "prompt_id": "<real-uuid-from-step-2>"}})
```

### Create Initial Evals

Deep-link to the Eval Builder to define 2-3 quality dimensions. Load `references/knowledge/create_spec.md` for the guided conversation.

> "Now let's define what 'good' looks like for your agent. I'd suggest starting with 2-3 evals:
> [Create Eval]({Eval Builder deep-link})"

Deep-link to the [Eval Builder](/specs/{pid}/{tid}/spec_builder).

### When an Existing Task Is Discovered

If the user's named task already exists **and they were asking to inspect/use it**, skip the creation steps. Check `default_run_config_id` in the task response:

- **`default_run_config_id` is null** — no model is connected yet. Proceed directly to **Create Initial Run Config** without asking for direction.
- **`default_run_config_id` is set** — the task is configured. Present its status and link to it, then offer next steps.

**If the user explicitly said "create" / "make me a new" task and a same-named task already exists**, do NOT stop on a disambiguation table. List the matches in one line as a heads-up for context, then **execute the creation path** under the project the user named (or pick one per `references/modes/project_operations.md` defaults). The only override: if the user's current or prior turn explicitly says "use the existing one" / "just point me at it" / "open that one" — then treat it as inspect, not create. Otherwise the verb "create" wins; disambiguation is a side-note, not a gate. Aligns with `references/modes/project_operations.md` "Default to executing".

### Suggest Next Steps

After the basics are set up:
- **Run a test** — deep-link to the [Run page](/run)
- **Run evals** once specs are created to get a baseline score
- **Try alternate models** if quality or cost isn't right → `references/modes/improve_task.md`
- **Add tools or RAG** if the agent needs external capabilities or knowledge
