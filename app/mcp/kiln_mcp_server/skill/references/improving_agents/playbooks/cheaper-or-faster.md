---
title: Cheaper or faster
description: The user wants the agent to cost less or answer sooner, with quality held - each step is marked cheaper, faster or both, because the two goals do not always agree.
reviewed: 2026-11-13
kind: goal
applies_to: all
---

# Cheaper or faster

## Situation

The run's objective is `cost` or `speed`, or the user asks for a
cheaper or a faster agent. Quality must not get worse. The two cases differ
in when this playbook applies:

- **The objective is `speed` or `cost`.** Quality is held, not tuned. Kiln
  Harness Tuner opens the run with a screening in code, and it
  screens many variants (the allowed models, the thinking levels) before it
  commits any of them. That procedure comes first, and its rule decides a
  win. The steps below are the ideas for the candidates around it, from the
  start of the run.
- **The objective is quality, and the user also asks for a lower cost
  or latency.** The cost goal comes after quality is stable: a change for
  cost that is measured on a harness that still changes for quality needs
  a new measurement later.

Most changes that cut tokens or calls help both goals. Some do not. A
very fast provider can cost more, and a cheap model that reasons a lot
can be slow. So each step below says which goal it serves.

This playbook gives the order of the ideas. It does not replace the
screenings of Kiln Harness Tuner.

## What to try, in order

1. **Faster, sometimes cheaper.** The same model on another provider,
   when the run allows that provider:
   [faster provider for the same model](references/improving_agents/techniques/faster-provider-for-the-same-model.md).
   Read the cost of the drives, not only the price per token: a provider
   with no prompt cache can cost more on a long, repeated prefix.
2. **Both.** Less thinking, one rung down, when the target evals hold:
   [thinking level ladder](references/improving_agents/techniques/thinking-level-ladder.md).
3. **Both.** A shorter prompt. Remove the parts that do not help:
   [prune one group at a time](references/improving_agents/techniques/prune-one-group-at-a-time.md).
   When each run needs only a few topics of a long prompt, and the model
   reads skills:
   [long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md).
   When a prompt cache serves the prompt, and most runs need most of a
   skill:
   [skill into the prompt](references/improving_agents/techniques/skill-into-the-prompt.md).
4. **Both.** Fewer tokens from the tools, and fewer calls. A result that
   carries fields the agent does not use:
   [cap and preview wrapper](references/improving_agents/techniques/cap-and-preview-wrapper.md). A
   chain of calls that is the same each time:
   [roll-up tool](references/improving_agents/techniques/roll-up-tool.md).
5. **Both.** Fewer output tokens, when the answer has text the task does
   not need (the input restated, a long preamble): a rule on the layout of
   the answer,
   [state the output contract](references/improving_agents/techniques/state-the-output-contract.md).
6. **Cheaper, often faster.** A smaller model of the class, with the
   harness adapted to it, when the model is a lever (`allowed_models`
   lists another model):
   [model swap inside a class](references/improving_agents/techniques/model-swap-inside-a-class.md).
   For a task with a classifier shape:
   [decision model for a classifier](references/improving_agents/techniques/decision-model-for-a-classifier.md).

## What not to do yet

- Do not trade quality for speed or cost unless the user says so. A
  change that is faster and loses items is not a win under these
  objectives.
- On a quality run, do not cut the prompt while the harness still changes
  for quality. The cut is measured on a harness that will not ship.
- On a quality run, do not swap to a small model before the cheaper steps
  that keep the model. A smaller model can need a different harness, so it
  is the largest change of this list. Under a `speed` or `cost` objective,
  the screening of Kiln Harness Tuner measures the allowed models
  first, and its result replaces this order.
- Do not read tokens per second as speed. A model that answers in fewer
  tokens can finish sooner at a lower rate.

## Budget

On a small budget, steps 1 and 2 come first: they change one setting,
with the harness unchanged, and cost the least to measure. Steps 3 to 6
need a build and a full check of quality. On a large budget, step 6 can
include a scan of the smaller models of the class.
