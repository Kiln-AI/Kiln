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

1. Read the parent's mode: `get_run_config` gives `structured_output_mode`
   in `run_config_properties`.
2. Read the default mode of each model: `get_model_details` gives the
   `default_structured_output_mode` of each provider entry: the server's
   value for a pair that the server offers. The planner's
   `allowed_models` input does not carry it.
3. Change it in one of three ways:
   - **A screening round**: a candidate with
     `overrides: {"structured_output_mode": "<value>"}`. Code makes and
     measures its run config.
   - **A probe**: a `check` probe with the same override answers one
     mechanism question, for example whether every output parses as JSON
     (`count: json_valid`), or whether the model still calls an attached
     tool (`attach: probe_tool`, `count: tool_calls`). A probe can set the
     mode. It cannot set a model, a provider or a setting.
   - **An arm**: the builder makes a new run config with
     `create_run_config`. It copies every property of the parent and
     changes only `structured_output_mode`. The `technique` of the arm is
     `output_mode`.
4. A model swap changes the mode too. The lever [model](references/levers/model.md) gives
   the step.

Rules of the object:

- **A change of the mode is a model-level swap.** Code treats it as it
  treats a change of the model or of a setting (`items.SWAP_KEYS`). The arm
  gets judge-free timing drives, and the residual block of the parent's
  failures does not gate it: a new mode changes how the model answers
  every item, not only the parent's failures. In a screening round, an
  output-mode candidate keeps the round's size. Under speed and cost, only a
  model or provider change takes the larger count of baseline passes.
- **The check is the output-validity count.** Code has no signal that the
  mode reached the call, so no `lever not applied` verdict exists for it.
  Code counts the outputs that do not parse as JSON or do not match the
  task's schema (the stop rule `invalid_output_rate`). By default, one
  invalid output stops a candidate or an arm. In a smoke, count the runs
  that fail with Kiln's schema error too.
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
  The model preflight does not show this: its test call
  attaches no tools.
- Under another mode, the model can still call its tools less. The setup
  reconnaissance asks whether the baseline model calls an attached tool
  under its mode, and under `json_instructions` when the mode is
  `json_schema`. The answers are in `probe_results`.
- A fine-tune can carry the mode it was trained with. Read it before you
  change it (the lever [model](references/levers/model.md)).

## See also

- The playbook [the output contract is not met](references/improving_agents/playbooks/output-contract-not-met.md):
  the modes ranked by how reliably the output matches the schema.
- The `kiln-harness-tuner-batch-selection` skill: the screening rounds and
  the `check` probes.
- The `kiln-harness-tuner-experiment-build` skill: how a run-config-only arm
  is built and smoked.
- The `kiln-task-setup` skill: the fields of `run_config_properties`.
