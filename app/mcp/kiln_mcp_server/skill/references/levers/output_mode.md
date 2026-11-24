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
matches the task's output schema.

Each value asks in a different way:

| Value | What Kiln sends with the call |
|---|---|
| `json_schema` | The schema, in the provider's structured-output parameter. A provider that supports it constrains the output to it. |
| `function_calling` | The schema, as the parameters of one tool (`task_response`) that the model must call, with the strict flag set. |
| `function_calling_weak` | The same tool, without the strict flag, for a provider that refuses it. |
| `json_instruction_and_object` | The schema as text after the saved prompt, and a request for a JSON object. |
| `json_mode` | A request for a JSON object only, with no schema: the shape comes only from the saved prompt. |
| `json_instructions` | The schema as text after the saved prompt. Nothing is asked of the provider. |
| `json_custom_instructions` | Nothing. The saved prompt must state the JSON shape itself. |
| `default` | Legacy. Kiln chooses at call time: `json_schema` on Ollama and Docker Model Runner, else the tool of `function_calling`, with the strict flag only on OpenAI. |
| `unknown` | Legacy. Kiln looks up the model's default at call time. |

After the call, Kiln checks each output against the schema, in every mode.
An output that does not match fails the run.

## How to change it

1. Read the parent's mode:
   `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md`
   gives `structured_output_mode` in `run_config_properties`.
2. Read the default mode of each model:
   `references/knowledge/api_docs/get_api_model_info_model_details.md` gives
   the `default_structured_output_mode` of each provider entry: the
   server's value for each pair that it offers. Your `allowed_models`
   input does not carry it.
3. Change it in one of three ways:
   - **A screening**: a candidate with
     `overrides: {"structured_output_mode": "<value>"}`. Code makes and
     measures its run config.
   - **A quick check** (`check`) with the same override answers one
     mechanism question, for example whether every output parses as JSON
     (`count: json_valid`), or whether the model still calls an attached
     tool (`attach: probe_tool`, `count: tool_calls`). A quick check can set
     the mode. It cannot set a model, a provider or a setting.
   - **An experiment**: you make a new run config with
     `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md`.
     You copy every property of the parent and change only
     `structured_output_mode`. Its `technique` is `output_mode`.
4. A model swap changes the mode too: see the lever
   [model](references/levers/model.md).

Rules of the object:

- **A change of the mode is a model-level swap.** Code treats it as a
  change of the model or of a setting (`items.SWAP_KEYS`). The experiment
  gets judge-free timing drives, and the residual block of the parent's
  failures does not gate it: a new mode changes how the model answers
  every item, not only the parent's failures. In a screening, an
  output-mode candidate keeps the screening's size. Under speed and cost, only a
  model or provider change takes the larger count of baseline passes.
- **The check is the output-validity count.** Code has no signal that the
  mode reached the call, so no `lever not applied` verdict exists for it.
  Code counts the outputs that do not parse as JSON or do not match the
  task's schema (the stop rule `invalid_output_rate`). By default, one
  invalid output stops a candidate or an experiment. In a smoke, count the runs
  that fail with Kiln's schema error too.
- **The properties of a run config are fixed when it is created.**

## Limits

- The lever exists only on a task with an output schema.
- Kiln's model list gives one default mode for each model and provider, not
  the other modes that the model supports. A provider can
  refuse a mode, or the model fail under it: one failed call shows it.
- Under `json_schema`, Kiln removes the number bounds (`minimum`,
  `maximum` and the like) from the schema that it sends, because some
  providers refuse them, and checks the range only after the call.
- **When the run config attaches a tool or a skill, Kiln refuses
  `function_calling`, `function_calling_weak`, and `default` outside
  Ollama and Docker Model Runner**. Each sends the schema as a tool, which
  Kiln does not mix with the agent's tools. An attached skill
  counts: Kiln loads it through a tool. The run fails at its final call.
  The model preflight does not show this: its test call attaches no tools.
- Under another mode, the model can still call its tools less. The setup
  reconnaissance asks whether the baseline model calls an attached tool
  under its mode, and under `json_instructions` when the mode is
  `json_schema`. The answers are in `probe_results`.
- A fine-tune can carry the mode it was trained with. Read it before a
  change (the lever [model](references/levers/model.md)).

## See also

- The playbook [the output contract is not
  met](references/improving_agents/playbooks/output-contract-not-met.md):
  the modes ranked by reliability.
- `references/knowledge/model_create_configs.md`: the fields of
  `run_config_properties`, and the run config payload.
- `references/knowledge/run_an_experiment.md`: how to measure the change,
  judge it and keep it.
