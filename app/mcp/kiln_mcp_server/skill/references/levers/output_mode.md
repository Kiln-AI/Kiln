---
title: The output mode
description: How Kiln asks the model for output that matches the task's output schema - the run config's structured_output_mode. A change is a model-level swap.
reviewed: 2026-11-13
api_docs:
  - references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md
  - references/knowledge/api_docs/get_api_model_info_model_details.md
  - references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md
---

# The output mode

## What it is

The output mode is the field `structured_output_mode` in
`run_config_properties`. It tells Kiln how to ask the model for output that
matches the task's output schema. It has an effect only when the task has
an output schema. On a task that returns free text, Kiln does not use it.

Each value is a different way to ask:

| Value | What Kiln sends with the call |
|---|---|
| `json_schema` | The schema, in the provider's structured-output parameter. A provider that supports it constrains the output to the schema. |
| `function_calling` | The schema, as the parameters of one tool (`task_response`) that the model must call, with the strict flag set. |
| `function_calling_weak` | The same tool, without the strict flag, for a provider that refuses the flag. |
| `json_instruction_and_object` | The schema as text after the saved prompt, and a request for a JSON object. |
| `json_mode` | A request for a JSON object only. Kiln does not send the schema, so the shape comes only from the saved prompt. |
| `json_instructions` | The schema as text after the saved prompt. Nothing is asked of the provider. |
| `json_custom_instructions` | Nothing. The saved prompt must state the JSON shape itself. |
| `default` | Legacy. Kiln chooses at call time: `json_schema` on Ollama and Docker Model Runner, else the tool of `function_calling`, with the strict flag only on OpenAI. |
| `unknown` | Legacy. Kiln looks up the model's default at call time. |

After the call, Kiln checks each output against the schema, in every mode.
An output that does not match fails the run. The modes that send the
schema as a tool are refused on a run config with tools (Limits).

## How to change it

1. Read the parent's mode:
   `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md`
   gives `structured_output_mode` in `run_config_properties`.
2. Read the default mode of each model:
   `references/knowledge/api_docs/get_api_model_info_model_details.md`
   gives the `default_structured_output_mode` of each provider entry:
   Kiln's value for a pair that Kiln offers.
3. Change it in one of three ways:
   - **A screening**: a candidate that changes only
     `structured_output_mode`. Make and measure its run config.
   - **A quick check**: the same change answers one mechanism question,
     for example whether every output parses as JSON, or whether the
     model still calls an attached tool.
   - **One experiment**: make a new run config with
     `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md`.
     Copy every property of the parent and change only
     `structured_output_mode`. Record it under the lever `output_mode`.
4. A model swap changes the mode too. The lever [model](references/levers/model.md) gives
   the step.

Rules of the object:

- **A change of the mode is a model-level swap.** Treat it as a change of
  the model or of a setting. A new mode changes how the model answers
  every item, not only the parent's failures, so do not stop it because it
  fixed few of the parent's failures. In a screening, an output-mode
  candidate is measured on as many items as the other candidates. When the
  user's goal is speed or cost, only a model or provider change is
  measured on the larger count of baseline passes, not a mode change.
- **The check is the count of invalid outputs.** No signal shows that the
  mode reached the call, so a mode change is never found "not applied".
  Count the outputs that do not parse as JSON or do not match the task's
  schema, and the runs that fail with Kiln's schema error. By default, one
  invalid output stops a candidate.
- **The properties of a run config are fixed when it is created.**

## Limits

- The lever exists only on a task with an output schema.
- Kiln's model list gives one default mode for each model and provider. It
  does not list the other modes that the model supports. A provider can
  refuse a mode, or the model can fail under it. One failed call shows it.
- Under `json_schema`, Kiln removes the number bounds (`minimum`,
  `maximum` and the like) from the schema that it sends, because some
  providers refuse them. The provider does not enforce a number range.
  Kiln checks it only after the call.
- **When the run config attaches a tool or a skill, Kiln refuses
  `function_calling`, `function_calling_weak`, and `default` outside
  Ollama and Docker Model Runner**. Each of them sends the schema as a tool,
  and Kiln does not mix that tool with the agent's tools. An attached skill
  counts: Kiln loads it through a tool. The run fails at its final call.
- Under another mode, the model can still call its tools less. Before you
  plan a mode change on a task with tools, check quickly whether the
  baseline model calls an attached tool under its mode, and under
  `json_instructions` when the mode is `json_schema`.
- A fine-tune can carry the mode it was trained with. Read it before you
  change it (the lever [model](references/levers/model.md)).

## See also

- The playbook [the output contract is not met](references/improving_agents/playbooks/output-contract-not-met.md):
  the modes ranked by how reliably the output matches the schema.
- `references/knowledge/model_create_configs.md`: the fields of
  `run_config_properties`, and the run config payload.
- `references/knowledge/run_an_experiment.md`: how to measure the change,
  judge it and keep it.
