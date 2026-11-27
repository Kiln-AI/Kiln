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

Your input already carries the facts. This playbook gives the strategy,
not the numbers:

- `measurement_prices`: the budget that remains, the price of each eval,
  of a full measurement and of the timing pairs, and the largest cap that
  code allows on one candidate;
- `eval_sizes`: the train items that each eval can pair;
- `train_detectability`: what each score can show on train, from Kiln
  Harness Tuner's pre-run detectability check;
- `train_noise`: how much a repeat moves a score, when the run sampled it
  with Kiln Harness Tuner's run-to-run noise check (`--noise-check N`);
- `lever_costs`: what each lever took to build in this run;
- `should_wrap_up`: the code's judgment that this is the last wave.

How to price a measurement, lane by lane, is in
`references/knowledge/experiment_costing.md`.

Build cost and learning cost are different. A prompt line costs the least
to build. A new description on a clone of a tool, a change of the attached
tools, a flat skill, a wrapper, a skill with reference files, a new tool
and a consolidation of tools each cost more to build, in about that order.
A swap to another model needs no build. Its cost is the measurement. The
`cost` of each technique gives its class. But a text candidate that cannot win
at validation costs the most of all, because its spend buys no lesson.

## What to try, in order

1. Check what each eval can show before you predict an effect on it. When
   the predicted change is smaller than what the eval can detect, or than
   its noise, fix the measurement or choose another eval:
   [dealing with a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md).
2. Size each experiment so that it can pass its own test: enough items on
   the target eval for the predicted effect. Fewer experiments, each with
   enough items, teach more than many small ones. When a candidate targets
   the items it is built to fix, they are measured first, and code stops the
   candidate early when they still fail. A rule written for one or two
   failing items rarely transfers: [one general rule per
   edit](references/improving_agents/techniques/one-general-rule-per-edit.md).
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
- Do not plan a full measurement of every eval for a candidate that has not yet
  fixed its target. The target eval decides first. This holds for every
  candidate: a skill bundle and the wildcard too. The confirmation on val
  measures every eval before a promotion.
- Do not judge a candidate by its build cost alone. A cheap candidate that the
  evidence says cannot win is the most expensive candidate in the plan.

## Budget

The steps above change with the budget, as each one says. When
`should_wrap_up` is true, Kiln Harness Tuner gives the wrap-up wave, and
that procedure replaces this order.
