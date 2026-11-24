---
title: Old model
description: The baseline's model was released more than the reference time (8 months) before the run. A code detector reads the release date, and the detection gives the age, the reference and its source.
reviewed: 2026-11-13
applies_to: all
---

# Old model

## What it is

The baseline's model was released more than the reference time, 8 months,
before the run. Model lines get new releases often. A newer model of the
same line, or of the same price, often does the same work better, at a lower
cost or faster. The harness was tuned on the old model, so nobody has
measured what a newer one does with it. This is a property of the design,
whether an eval passes or fails.

## How to recognise it

In the harness:

- the code detection in your input gives the model, its release date, its
  age in months, and the reference it was compared with;
- `references/knowledge/api_docs/get_api_model_info_models.md` with `sort:
  newest` and the baseline's `family` lists newer models with `ready`
  provider entries; compare their `median_input_price` with the baseline's
  price;
- the `agent_notes` of the baseline's model in
  `references/knowledge/api_docs/get_api_model_info_model_details.md` name a
  model that replaces it.

In how the agent runs:

- nothing specific. The age of a model does not show in a trace.

## How to confirm it

- Find a newer candidate that the run can use: a `ready` entry in
  `references/knowledge/api_docs/get_api_model_info_models.md`, inside the
  run's `allowed_models`. The lever
  [model](references/levers/model.md) gives the three model endpoints and their
  limits. With no such candidate, the model is not a lever in this run.
  The report can still
  name a good newer model whose provider is `not_connected`.
- Read the `agent_notes` of the baseline's model and of each candidate.
  Compare the capabilities that the task needs: tool calls, structured
  output, vision, thinking levels.
- The release date can be estimated (`release_date_estimated: true` in
  `references/knowledge/api_docs/get_api_model_info_model_details.md`). Then
  it comes from the name of the model, not from an exact entry. State that
  when you state how sure you are.
- The reference is a default, not a measured optimum. Read the detection's
  source.
- **Not this smell:** an old model that is kept on purpose. For example: a
  fine-tune base, a price or a latency that no newer model meets, or a model
  that the user pinned (`--models keep`, a model policy, or what the user
  asked). A run with `--models keep` cannot change the model. The finding is
  then for the report only.

## What it blocks

Nothing.

## Remedies

- [Model swap inside a
  class](references/improving_agents/techniques/model-swap-inside-a-class.md),
  when `allowed_models` lists a newer model of the same class and what the
  user asked does not forbid a model change.
- [Faster provider for the same model](references/improving_agents/techniques/faster-provider-for-the-same-model.md),
  when no newer model fits, and the goal is latency or cost.
- [Cheaper or faster](references/improving_agents/playbooks/cheaper-or-faster.md), when the run's
  objective is cost or speed, and a newer model can cost less or answer
  sooner at the same quality.
