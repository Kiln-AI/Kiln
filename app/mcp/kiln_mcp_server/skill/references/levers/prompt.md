---
title: The system prompt
description: The prompt text that a run config sends to the model, and its chain-of-thought instructions. A change is a new saved prompt and a new run config.
reviewed: 2026-11-13
api_docs:
  - references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md
  - references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_prompts.md
  - references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md
  - references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_prompts.md
  - references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md
---

# The system prompt

## What it is

The system prompt is the text that a run config sends to the model before
the task input. In Kiln it is a saved prompt of the task: a `prompt` text
and optional `chain_of_thought_instructions`. A run config names one prompt
in its `prompt_id`.

The task's own instruction and requirements are not the prompt of a run
config. The tuner does not change the task.

## How to change it

1. Read the prompt that the parent run config runs with:
   `get_run_config` gives the `prompt_id` and the frozen prompt, and
   `get_prompt_text` gives the text that a prompt id renders.
   `list_prompts` lists the task's saved prompts.
2. Write the new text. Start from the parent's text and change only what
   the experiment's hypothesis names.
3. Save it as a new prompt with `create_prompt` (`name`, `prompt`, and
   `chain_of_thought_instructions` when the parent has them).
4. Create a new run config with `create_run_config`. Copy every property of
   the parent, and set `prompt_id` to the new prompt (`id::<id>`).

Rules of the object:

- **A saved prompt is not changed in place.** A new text is a new prompt.
- **The properties of a run config are fixed when it is created.** A
  mistake means another new run config.
- **A prompt generator is frozen into the run config** when the config is
  created, so a config never follows a later change to a generator.

## Limits

- No value from a train item goes into the prompt: no item id, number,
  sentence or expected value. Code searches each build for copies before it
  measures the build.
- No text copied from an eval or its judge. The judge-copy check refuses it.
- The prompt is in the context of every call, so each line costs tokens on
  every item. A long prompt has its own smell:
  [very long prompt](references/improving_agents/smells/very-long-prompt.md).
- The input transform (`input_transform`) is out of scope. It is the
  template that turns the task input into the first user message. No lever
  covers it: copy it as the parent has it.

## See also

- The `kiln-harness-tuner-experiment-build` skill: the build discipline,
  provenance, and what text you may add.
- The `kiln-task-setup` skill: the prompt and run-config payloads, and the
  known platform bugs.
- The `kiln-harness-tuner-gateway` skill: the fields of each operation.
