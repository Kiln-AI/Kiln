---
title: The model and the provider
description: The model and the provider that a run config names, chosen from the models the user allows. Existing fine-tunes are candidates too.
reviewed: 2026-11-13
api_docs:
  - references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md
  - references/knowledge/api_docs/get_api_model_info_models.md
  - references/knowledge/api_docs/get_api_model_info_model_details.md
  - references/knowledge/api_docs/get_api_model_info_providers.md
  - references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md
---

# The model and the provider

## What it is

A run config names one model and one provider, in `model_name` and
`model_provider_name`. The same model can be served by more than one
provider. A fine-tune that already exists is a model too, with the provider
`kiln_fine_tune`.

The settings of the model (thinking level, temperature, top-p) are the
lever [params](references/levers/params.md). The output mode is the lever
[output_mode](references/levers/output_mode.md).

## How to change it

1. Read what you can use:
   `references/knowledge/api_docs/get_api_model_info_models.md` gives each
   model with its `ready` provider entries: the pairs that Kiln offers. Use
   only the pairs that the user allows. Each row has the list price, the
   context window, the release date and the tags.
   `references/knowledge/api_docs/get_api_model_info_model_details.md`
   gives one model's notes for agents (`agent_notes`), and per provider
   entry the capability flags (tool calls, structured output, vision), the
   thinking levels and `default_structured_output_mode`.
   `references/knowledge/api_docs/get_api_model_info_providers.md` gives
   the notes on each provider, for example data retention or routing.
2. Change it in one of two ways:
   - **A screening**: candidates with another `model_name` and
     `model_provider_name`, a thinking level when the new model needs one,
     and the output mode of step 4. Make and measure each candidate's run
     config.
   - **One experiment**: make a new run config with
     `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md`.
     Copy every property of the parent, change the model and the provider,
     and set the output mode of step 4.
3. A thinking level comes from the new model's own list. A level of the
   old model can be missing on the new one.
4. **The output mode is the new model's default**: the
   `default_structured_output_mode` that step 1 gives for the new model
   and provider. The parent's mode was chosen for the parent's model, and the
   new provider can refuse it or the new model can follow it less well.
   When step 1 gives no mode, or the legacy `default` or `unknown`, keep
   the parent's mode. On a task with no output schema, the mode has no
   effect. **On a run config that attaches a tool or a skill**, Kiln
   refuses the modes that send the schema as a tool: `function_calling`,
   `function_calling_weak`, and `default` outside Ollama and Docker Model
   Runner (the lever [output_mode](references/levers/output_mode.md)). When the default is
   one of them, use `json_schema` if you know that the new model supports
   it, else `json_instruction_and_object`. Step 1 gives only the default
   mode, so that knowledge comes from a quick check or an earlier screening
   of the model. The one exception is an experiment that tests the output
   mode on the new model: it sets the mode that it tests, and its
   hypothesis names both changes. A copy of the parent keeps the parent's
   mode until you set it.

Rules of the object:

- **Use only the models that the user allows.** Ask the user which
  models and providers are allowed before you create a run config with
  another model or provider.
- **The properties of a run config are fixed when it is created.**
- **Check yourself that the swap reached the call.** A run that another
  model or provider served means that the change was not applied.
- **Invalid output just after a swap points first to the output mode**,
  not to a weaker model. When a swap stops on invalid output, or every run
  fails, check its mode against step 4 before you record the model as
  refuted: the new model's default, or the fallback on a run config with
  tools. A swap with the wrong mode is a fault of the build.

## Limits

- **The model is a lever only when the user allows another model.** Ask
  the user which models are allowed. When they allow the baseline's model
  alone, the model is the environment that the task is tuned for, and you
  plan no model swap. A request of the user that forbids a model change
  also excludes it.
- An experiment does not start a fine-tune. It can choose one that exists,
  when the user allows `kiln_fine_tune` and Kiln lists it. A fine-tune can
  be made for another task, or carry its own prompt and output mode: read
  what it is before you plan it.
- The capability flags, the prices and the notes are Kiln's and
  models.dev's data. They can be missing or wrong for one pair. A quick
  check or one run shows what the pair does on the task.
- Use `ready` pairs only: a pair that Kiln does not offer fails when it
  runs. A good model with the status `not_connected` is a finding to
  report to the user: the user can connect that provider.

## See also

- `references/knowledge/model_work.md`: the model facts, the tiers, the
  providers and the model info endpoints.
- `references/knowledge/model_create_configs.md`: the run config payload,
  the model and provider check, and the name rules.
