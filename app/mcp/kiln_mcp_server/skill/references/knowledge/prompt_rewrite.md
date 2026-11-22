---
name: prompt_rewrite
description: |
  Knowledge for editing or improving an agent's prompt — reading current prompts, suggesting improvements, creating saved prompts, and building prompts with examples. Loaded by the Project Operations mode.
---
# Prompt Rewrite

Reference knowledge for editing or improving the agent's task instruction or saved prompts. This is the fastest optimization lever when the prompt has obvious gaps, is too vague, or the user says "I want my agent to do X" and it's not in the prompt.

## Knowledge Required

- `references/knowledge/prompt_audit.md` — when the systematic audit checklist is needed to identify what to improve
- `references/knowledge/model_create_configs.md` — for Kiln name validation rules when creating saved prompts
- `references/knowledge/model_create_configs.md` — when creating a run config for a new saved prompt

## API Docs

Load the relevant endpoint doc **before** making each API call — they have request body schemas, response fields, and parameter details.

If your endpoint isn't listed below, load the matching `*_api_list.md` catalog (see SKILL.md → API Rules).

| Endpoint | Load |
|----------|------|
| GET task (instruction, schemas) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id.md` |
| PATCH update task instruction | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id.md` |
| GET prompts list | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_prompts.md` |
| POST create saved prompt | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_prompts.md` |
| PATCH update saved prompt | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_prompts_prompt_id.md` |
| GET generated prompt | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md` |
| POST build prompt with examples | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_build_prompt_with_examples.md` |
| POST create run config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md` |
| PATCH update run config | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_run_configs_run_config_id.md` |

## Suggested Questions

1. **What's the goal?** "What should the prompt do differently?" (add a capability, fix a failure, change output format, improve tone)
2. **Existing prompt state?** Have they already written a prompt, or is this from scratch?
3. **Constraints?** Any output format requirements, length limits, or persona needs?

## Prompt Editing Approaches



### Read the Current Task and Prompt

Load the current prompt and schemas — see `references/knowledge/prompt_audit.md` → Read the Current Task and Prompt.

### Identify What to Change

Based on the user's goal + reading the prompt, identify gaps. If unsure what to improve, load `references/knowledge/prompt_audit.md` for the systematic audit checklist.

### Propose Changes

Show the user the full rewritten prompt and explain what changed and why.

**Critical rule: Show, then END.** Display the full rewritten prompt and explain changes — then end the reply. The user's next message IS the approval signal. Do not add "Do you want to apply this?" or any trailing approval request — that is a contract violation per the mode's Response Contract. Showing and creating in the same turn is also a violation.

### Create or Update the Prompt

After user approval:

- **Update task instruction**:
  Read `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id.md`, then:
  `call_kiln_api("PATCH", "/api/projects/{project_id}/tasks/{task_id}", body={"instruction": "..."})`
- **Create a saved prompt**:
  Read `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_prompts.md`, then:
  `call_kiln_api("POST", "/api/projects/{project_id}/tasks/{task_id}/prompts", body={"name": "...", "prompt": "...", "description": "..."})`
- **Build prompt with examples**:
  Read `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_build_prompt_with_examples.md`, then:
  `call_kiln_api("POST", "/api/projects/{project_id}/tasks/{task_id}/build_prompt_with_examples", body={"examples": [{"input": "...", "output": "..."}]})`

See `references/knowledge/model_create_configs.md` → Kiln Name Validation for naming rules (forbidden characters: `. , ; : = / \ ? % * | < >`).

### Create a Run Config (If Needed)

If a new saved prompt was created, create a run config that uses it:

```json
{
  "run_config_properties": {
    "type": "kiln_agent",
    "model_name": "...",
    "model_provider_name": "...",
    "prompt_id": "<saved_prompt_id>"
  }
}
```

Load `references/knowledge/model_create_configs.md` if a model needs to be chosen.

### Suggest Next Steps

- **Run evals** to compare the new prompt against the baseline → deep-link to [Compare Eval Scores](http://localhost:8757/specs/{project_id}/{task_id}/compare)
- **Create specs** if none exist yet to measure the improvement → `references/knowledge/create_spec.md`

## Prompt Types in Kiln

- **Task Instruction** — the base instruction on the task. Foundation for all prompt builders. Edit via PATCH.
- **Saved Prompts** — custom prompts saved to a task, referenced by ID in run configs.
- **Prompt Builders** — built-in generators: `simple_prompt_builder` (just the instruction), `few_shot_prompt_builder` (instruction + dataset examples).

## Prompt UI Access

| Action | How to access |
|--------|--------------|
| View/manage prompts | Navigate to the [**View all run configs** page](http://localhost:8757/optimize/{project_id}/{task_id}) → click **Prompts** in sidebar |
| Edit base task prompt | Task overview → Prompts → Edit base prompt |
| Create a new saved prompt | Task overview → Prompts → Create |

**Warning:** The prompts pages require the task to be selected in the sidebar first — they do not work as direct links.
