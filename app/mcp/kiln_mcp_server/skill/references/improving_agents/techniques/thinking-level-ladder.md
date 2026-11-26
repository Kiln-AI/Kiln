---
title: Thinking level ladder
description: Change the thinking level one rung at a time from the baseline's level - up only for hard cases, down for cost or latency once quality is stable - and temperature at most once.
reviewed: 2026-11-13
status: active
levers:
  - params
applies_to: all
cost: low
---

# Thinking level ladder

## When to use

- **Up one rung**: the baseline measurement shows hard cases, items that
  fail in the same way on every prompt candidate. More reasoning can help an
  item that the model fails because it does not think the problem through.
- **Down one rung**: quality has stopped moving (no candidate moved a target
  eval for two waves), and what the user asked or the objective cares about
  cost or latency. Less reasoning costs less and returns sooner.
- **Temperature or top-p**: a trace shows a reason that a sampling setting
  can fix, for example answers that vary on the same input when the task
  needs one stable answer. One candidate at most.

## When not to use

- **The failure has a cause in the harness**: a missing requirement, a
  tool that floods the context, a malformed call. A setting is not a fix
  for a prompt, a tool or a skill. It changes how the same model reads the
  same harness.
- **There are no hard cases.** A higher level costs more on every item,
  and nothing shows an item that more reasoning would fix.
- **Do not read a quick check's direction as quality.** A quick check that
  compares the candidate with its parent says that the setting moves the
  behaviour (more or fewer characters of reasoning). It does not say that
  the change helps or hurts. A moved setting earns an experiment. It does
  not retire one.
- **The user says not to touch the thinking level**, or the run's objective
  is `speed` or `cost` (the run then opens with a screening of the lower
  levels). That request or objective replaces this order.
- **The highest level as a default.** More reasoning takes more time and
  more tokens. When the task or the eval has a time limit, the highest
  level can fail items that a lower level passes.

## Alternatives

- [Model swap inside a class](references/improving_agents/techniques/model-swap-inside-a-class.md), when the
  objective is cost or latency and `allowed_models` lists another model: a
  smaller model can save more than a lower level.
- [Faster provider for the same model](references/improving_agents/techniques/faster-provider-for-the-same-model.md),
  when the goal is latency, and the same model at the same level is served
  faster elsewhere.

## How

The change is a setting on a clone of the parent (the lever
[params](references/levers/params.md)). Everything else stays as the parent has
it. The lever gives the two ways: a screening, and a params experiment.

1. **Rung 0 is the baseline's level.** The levels come from the model's
   own list, lowest first.
2. **Up, for hard cases.** Name the hard cases from the baseline
   measurement. Test one rung up, or two or three rungs at once, as a
   screening on the evals that have the hard cases, in the mode that
   judges the baseline's failures and a few of its passes. Commit the best
   survivor as a params experiment.
3. **Down, for cost or latency.** Once quality has stopped moving, screen
   one rung down. Keep it if the target evals hold.
4. **One setting on each candidate.** A level and a temperature on one
   candidate do not tell which one moved the result.
5. **Temperature or top-p: one candidate at most**, and only with a reason
   from a trace. Some providers refuse a non-default value. One failed call
   shows it.

## Check that it took effect

Code reads the drives of the new run config: a level with no reasoning in
any drive, and output tokens that did not move against the parent, gives
the verdict `lever not applied`. Read that verdict before you read the
scores. A provider can accept a setting and not apply it.

## Budget

Low cost: a screening is measured in code, on few items, before any
experiment. It fits a small budget once the hard cases are named. On a small
budget, leave out a temperature candidate unless a trace gives its reason.

## If it does not move the evals

It depends. A rung up must move an eval: it costs more on every item. A
rung down that holds every eval and lowers the cost or the latency is a
gain: keep it. When a setting moves neither the evals nor the cost, the
provider may not apply it.

## Priors

- **A coding agent on a terminal benchmark, on one model with four
  reasoning levels.** The harness was tuned with the model fixed. A run at
  the highest level on every step scored 53.9%, against 63.6% at the
  second-highest level ("high"), because the agent ran out of time on
  tasks with a time limit. The team then used more reasoning for planning
  and for the final check, and less in between. One sample, not a rule.
  Source: public, the LangChain post "Improving Deep Agents with harness
  engineering". 2026-02-17.

## Confidence

Medium, that the highest level is not a safe default when the task has a
time or token limit: one public case, and it follows from cost, since more
reasoning takes more time on every step. Low to medium, for the order of
the ladder (up only for hard cases, down after quality is stable): it is
reasoning from cost, and it keeps each candidate to one change. Low, for
temperature and top-p: some providers refuse a value that is not the
default, and no case here shows a gain from one.
