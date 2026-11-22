---
title: Old model
description: The baseline's model was released more than 8 months ago. Read its release date yourself, and give its age and the reference.
reviewed: 2026-11-13
applies_to: all
---

# Old model

## What it is

The baseline's model was released more than the reference time, 8 months,
before today. Model lines get new releases often. A newer model of the same
line, or of the same price, often does the same work better, at a lower cost
or faster. The harness was tuned on the old model, so nobody has measured
what a newer one does with it. This is a property of the design, whether an
eval passes or fails.

## How to recognise it

In the harness:

- read it yourself: the release date of the baseline's model in
  `references/knowledge/api_docs/get_api_model_info_model_details.md` is
  more than 8 months ago. Give the model, its release date and its age in
  months;
- `references/knowledge/api_docs/get_api_model_info_models.md` with `sort:
  newest` and the baseline's `family` lists newer models with `ready`
  provider entries; compare their `median_input_price` with the baseline's
  price;
- the `agent_notes` of the baseline's model name a model that replaces it.

In how the agent runs:

- nothing specific. The age of a model does not show in a trace.

## How to confirm it

- Find a newer candidate that you can use: a `ready` entry, among the
  models that the user allows. The lever
  [model](references/levers/model.md) gives the three model endpoints and their
  limits. With no such candidate, the model is not a lever for this work.
  The report can still
  name a good newer model whose provider is `not_connected`.
- Read the `agent_notes` of the baseline's model and of each candidate.
  Compare the capabilities that the task needs: tool calls, structured
  output, vision, thinking levels.
- The release date can be estimated (`release_date_estimated: true`).
  Then it comes from the name of the model, not
  from an exact entry. State that when you state how sure you are.
- The reference is a default of Kiln Harness Tuner, not a measured
  optimum: no published value is known.
- **Not this smell:** an old model that is kept on purpose. For example: a
  fine-tune base, a price or a latency that no newer model meets, or a
  model that the user pinned. When the user does not allow a model
  change, the model cannot change. The finding is then for the report
  only.

## What it blocks

Nothing.

## Remedies

- [Model swap inside a class](references/improving_agents/techniques/model-swap-inside-a-class.md),
  when the user allows a newer model of the same class and does not
  forbid a model change.
- [Faster provider for the same model](references/improving_agents/techniques/faster-provider-for-the-same-model.md),
  when no newer model fits, and the goal is latency or cost.
- [Cheaper or faster](references/improving_agents/playbooks/cheaper-or-faster.md), when the user's
  goal is cost or speed, and a newer model can cost less or answer
  sooner at the same quality.
