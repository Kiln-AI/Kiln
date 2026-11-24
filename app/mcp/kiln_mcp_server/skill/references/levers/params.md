---
title: Model settings
description: The model's settings on a run config - thinking level, temperature and top-p - changed on a clone of the parent, as a params experiment or in a screening.
reviewed: 2026-11-16
api_docs:
  - references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md
  - references/knowledge/api_docs/get_api_model_info_model_details.md
  - references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md
---

# Model settings

## What it is

A run config sends settings to the model with each call. This lever covers
three of them, in `run_config_properties`:

- `thinking_level`: how much the model reasons before it answers. Each
  model has its own list of levels.
- `temperature`: from 0 to 2.
- `top_p`: from 0 to 1.

The model and the provider are the lever [model](references/levers/model.md). The output
mode (`structured_output_mode`) is the lever
[output_mode](references/levers/output_mode.md). The prompt, the tools and the skills stay
as the parent has them.

## How to change it

There are two ways.

**A params experiment.** You make one run config with
`references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md`.
It is identical to the parent, except the named settings. No new prompt,
skill or tool. The `change` block of the build lists each setting with its
old and its new value, and everything else under `unchanged`.

**A screening.** You write a plan with `screen` set and no items. Each
candidate has `overrides` (`thinking_level`, `temperature`, `top_p`). Code
makes each candidate's run config, measures all of them on the same items,
and gives each one a verdict. No agent builds them. A survivor becomes an
experiment with `work.existing_rc_id`, and its judged rows are used again.

Rules of the object:

- **The thinking levels come from
  `references/knowledge/api_docs/get_api_model_info_model_details.md`**: the
  `thinking_levels` of the model's provider entry, lowest first. For a pair
  that the server offers, they are the server's list. A level that is not
  in that list is refused.
- **The properties of a run config are fixed when it is created.** A
  mistake means another new run config.

## Limits

- A provider can accept a setting and not apply it. Code reads the drives
  for two things only: the thinking level, and the model and provider. A
  thinking level with no reasoning in any drive, and output tokens that
  did not move against the parent, gives the verdict `lever not applied`.
  So does a drive that another model or provider served. When no signal
  can show one of these two, the verdict is `lever unverified`. Code does
  not check `temperature` or `top_p`: a change to them gets the verdict
  `applied` with no check.
- A provider can refuse a setting. One failed call shows it.
  `references/knowledge/api_docs/get_api_model_info_model_details.md` gives
  `supports_temperature` for each provider entry, from models.dev: `false`
  says that the model does not take a temperature.
- The output mode is not part of this lever. It has its own lever,
  [output_mode](references/levers/output_mode.md).
- Kiln has no setting for `max_tokens`, a seed, `top_k` or penalties.

## See also

- `references/knowledge/model_create_configs.md`: the fields of
  `run_config_properties`, and the run config payload.
- In a chat with a user:
  `references/client_guidance/chat/running_an_experiment_from_chat.md`.
