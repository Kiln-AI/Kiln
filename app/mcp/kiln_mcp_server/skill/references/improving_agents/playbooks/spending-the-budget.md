---
title: Spending the budget
description: How to spend a fixed budget - fewer experiments, each large enough to pass its own test, the cheap techniques first on a small budget, and the scan of models only on a large one.
reviewed: 2026-11-16
kind: order
applies_to: all
---

# Spending the budget

## Situation

Read this before each plan. Every measurement spends a part of a fixed
budget, and the evals are the expensive part: each item drives the agent,
and often a synthetic user and a judge. The largest saving is to be right
often. A candidate that cannot pass its own test spends money and teaches
nothing.

Get the facts before you plan. This playbook gives the strategy, not the
numbers:

- the budget that remains, the price of each eval, of a full measurement
  and of a measurement of latency, and the most that you may spend on one
  candidate: ask the user for the spend limit;
- the train items that each eval can pair;
- what each score can show on train, and how much a repeat moves a score:
  Kiln Harness Tuner measures both, and the rules that use them apply when
  running it;
- what each lever took to build in your earlier experiments;
- whether this is the last round of experiments: ask the user.

Build cost and learning cost are different. A prompt line costs the least
to build. A new description on a clone of a tool, a change of the attached
tools, a flat skill, a wrapper, a skill with reference files, a new tool
and a consolidation of tools each cost more to build, in about that order.
A swap to another model needs no build. Its cost is the measurement. The
`cost` of each technique gives its class. But a text candidate that cannot
win at validation costs the most of all, because its spend buys no lesson.

## What to try, in order

1. Check what each eval can show before you predict an effect on it. When
   the predicted change is smaller than what the eval can detect, or than
   its noise, fix the measurement or choose another eval:
   [dealing with a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md).
2. Size each experiment so that it can pass its own test: enough items on
   the target eval for the predicted effect. Fewer experiments, each with
   enough items, teach more than many small ones. When a candidate targets
   the items it is built to fix, measure them first, and stop the
   candidate early when they still fail. A rule written for one or two failing
   items rarely transfers:
   [one general rule per edit](references/improving_agents/techniques/one-general-rule-per-edit.md).
3. On a small budget, prefer the techniques of `low` cost for each issue,
   and techniques that change one surface. Leave out the scan of models
   before the lock.
4. On a large budget, a scan of the models of the class before the lock
   becomes reasonable, when the model is a lever:
   [model swap inside a class](references/improving_agents/techniques/model-swap-inside-a-class.md).
   The techniques of `high` cost fit too, for example
   [consolidate tools](references/improving_agents/techniques/consolidate-tools.md).
5. A short screen of the settings:
   [thinking level ladder](references/improving_agents/techniques/thinking-level-ladder.md). It is
   low cost, and it fits a small budget, for example when no known harness
   problem is open. A setting does not fix a failure that has a cause in
   the harness.

## What not to do yet

- Do not split a small budget over many experiments that are each too
  small to pass their test. Each one then ends with no answer.
- Do not spend a small budget on the choice of the model to lock. Pick a
  model of the right class with some aptitude for the task, and begin the
  work.
- Do not plan a full measurement of every eval for a candidate that has
  not yet fixed its target. The target eval decides first. This holds for
  every candidate: a skill bundle and an idea of your own too. The
  confirmation on val measures every eval before a candidate becomes the
  baseline.
- Do not judge a candidate by its build cost alone. A cheap candidate that
  the evidence says cannot win is the most expensive candidate in the
  plan.

## Budget

The steps above change with the budget, as each one says. When running
Kiln Harness Tuner and it is the last round, its wrap-up procedure
replaces this order.
