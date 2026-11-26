---
name: prompt_rewrite
description: |
  Knowledge for an agent's prompt in Kiln — reading current prompts, creating saved prompts and the run config that uses one, building prompts with examples, the prompt types, and editing a prompt in place as a project operation. Loaded by the Project Operations and Improve Task modes.
---
# Prompt Rewrite

Reference knowledge for the agent's task instruction and saved prompts in Kiln: how to read them, how to make a new prompt and use it, and how to edit one in place when the user asks.

## Knowledge Required

- `references/knowledge/prompt_audit.md` — a review checklist, for a new prompt or when the user asks for a review
- `references/knowledge/model_create_configs.md` — for Kiln name validation rules when creating saved prompts
- `references/knowledge/model_create_configs.md` — when creating a run config for a new saved prompt

## API Docs

Load the relevant endpoint doc **before** making each API call — they have request body schemas, response fields, and parameter details.

If your endpoint isn't listed below, load the matching `*_api_list.md` catalog (see `references/knowledge/api_docs/calling_the_kiln_api.md`).

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

## Read the Current Task and Prompt

Load the current prompt and schemas — see `references/knowledge/prompt_audit.md` → Read the Current Task and Prompt.

## A Prompt Change to Improve an Agent

What to change, and how to change a prompt as an experiment, is the lever's: `references/levers/prompt.md`, reached through the playbook that fits (in a chat with a user, through `references/client_guidance/chat/improve_task.md`). In a chat with a user, how to measure the new prompt against the baseline and keep it is `references/client_guidance/chat/running_an_experiment_from_chat.md`. In Kiln the change is a **new saved prompt** and a **new run config** that names it; the task instruction and the saved prompt that the baseline uses stay as they are.

1. **Create a saved prompt**:
   Read `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_prompts.md`, then:
   `call_kiln_api("POST", "/api/projects/{project_id}/tasks/{task_id}/prompts", body={"name": "...", "prompt": "...", "description": "..."})`
   Body essentials: `{name, prompt, description?, chain_of_thought_instructions?}`.
   See `references/knowledge/model_create_configs.md` → Kiln Name Validation for naming rules (forbidden characters: `. , ; : = / \ ? % * | < >`).
2. **Create a run config that uses it**, a copy of the parent with the new `prompt_id` (the POST answers `id::<id>`, which the run config takes as-is, `references/knowledge/model_create_configs.md`):

   ```json
   {
     "run_config_properties": {
       "type": "kiln_agent",
       "model_name": "...",
       "model_provider_name": "...",
       "prompt_id": "id::<saved_prompt_id>"
     }
   }
   ```

- **Build prompt with examples**: `POST /api/projects/{project_id}/tasks/{task_id}/build_prompt_with_examples` (read `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_build_prompt_with_examples.md` first), with `body={"examples": [{"input": "...", "output": "..."}]}`. For a prompt that an experiment measures, the examples use invented values, never the values of a train item: the leak rules of `references/knowledge/train_val_test.md`.
- **No eval yet** to measure the change: `references/knowledge/create_spec.md` first.

## Project Operations: Edit a Prompt in Place

When the user asks for the task instruction to be changed in place, that is a project operation, not an experiment. A change in place makes the eval measurements made with that prompt wrong, so tell the user, and offer a new saved prompt in its place (`references/knowledge/working_with_project_files.md`, "Respect immutability"). When they still want it:

- **Update the task instruction**: read `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id.md`, then `call_kiln_api("PATCH", "/api/projects/{project_id}/tasks/{task_id}", body={"instruction": "..."})`.
- **A saved prompt's text cannot be changed**: `PATCH .../prompts/{prompt_id}` (`references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_prompts_prompt_id.md`) changes only its name and description. A new text is a new saved prompt (above).

**Show, then END.** For a rewrite the user has not yet seen, display the full rewritten prompt and explain what changed — then end the reply. The user's next message is the approval. Do not add "Do you want to apply this?"; when the user's message already asked for exactly this change, the ask is the consent: make it and report it.

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

## See also

When and why, in the knowledge: `references/levers/prompt.md`, `references/improving_agents/techniques/add-the-missing-requirement.md`, `references/improving_agents/techniques/one-general-rule-per-edit.md`, `references/improving_agents/techniques/structure-a-long-prompt.md`, `references/improving_agents/techniques/policy-as-step-by-step-procedures.md`, `references/improving_agents/techniques/state-the-output-contract.md`, `references/improving_agents/techniques/decline-rules-paragraph.md`, `references/improving_agents/techniques/prune-one-group-at-a-time.md`, `references/improving_agents/smells/very-long-prompt.md`, `references/improving_agents/playbooks/requirement-missing-from-the-prompt.md`, `references/improving_agents/playbooks/lost-in-long-instructions.md`, `references/improving_agents/playbooks/wrong-scope-or-refusal.md`, `references/improving_agents/playbooks/change-the-surface-not-the-words.md`.
