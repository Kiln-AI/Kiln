---
title: Dealing with a noisy eval
description: A score moves between repeats with no change to the agent. Read the noise, predict effects larger than it, let the val gate confirm on new items, and do not let a decision turn on one or two items.
reviewed: 2026-11-13
kind: eval
applies_to: all
---

# Dealing with a noisy eval

## Situation

The same run config, measured twice on the same items, gives different
scores. Signs:

- `train_noise` in your input shows a spread between repeats that is as
  large as the effects the arms predict;
- items flip between pass and fail with no change to the agent;
- an arm's win or loss rests on one or two items;
- a judge gives different verdicts on the same output.

The noise comes from the agent (it answers the same input in different
ways), from the judge, or from the synthetic user of a multi-turn eval. A
difference smaller than the noise is not a result, in either direction.

## What to try, in order

1. Read the noise before you plan against the eval. When `train_noise` is
   in your input, it gives how often the same config scores differently
   on a sample of train items, and `noise_adjusted_wins` is the bar with
   that noise counted. When `train_noise` is absent, the noise is not
   known, and the stop rules use a flip rate of 10%. Say in `rationale`
   which case applies.
2. Plan each arm so that its effect can show above the noise. Predict a
   larger effect and say why, or choose a target eval whose
   `train_detectability` can show the effect you predict:
   [spending the budget](references/improving_agents/playbooks/spending-the-budget.md).
3. Use the val gate as the repeat. The gate measures a candidate again,
   on val items that the arm was not built on. A train win is a candidate
   until the gate confirms it. When the gate rejects a win with "a gain
   at val, not clear", read
   [train wins rejected at validation](references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md).
4. When the judge is the source (it gives different verdicts on the same
   output, or verdicts that disagree with its reasoning), it is a judge
   failure. Read the fires and report them as
   [dealing with a wrong eval](references/improving_agents/playbooks/dealing-with-a-wrong-eval.md) says. Plan
   the arms against the noise with steps 1 to 3 here.
5. When the agent is the source, and the task needs one stable answer for
   one input: one arm on a sampling setting, with the trace-level reason:
   [thinking level ladder](references/improving_agents/techniques/thinking-level-ladder.md).
6. When the items that flip are the ones that carry the decision, choose
   the target items from the failures that repeat. A failure that repeats
   is a better target than one that comes and goes.

## What not to do yet

- Do not plan a repeat of a measured arm. A `remeasure` item fills only
  the items that have no stored row, so on a fully measured run config it
  returns the same rows. A duplicate run config built only to run its
  evals again is not allowed.
- Do not let a decision turn on one or two items. Two items can flip by
  chance alone.
- Do not plan many small arms on a noisy eval. Each one ends with no
  answer. Fewer, larger arms teach more.
- Do not read a single run of the baseline as its true score. Its own
  noise is in that number too.

## Budget

On a small budget, an arm that ends with no answer is a large part of the
spend. Put the arms on the noisy eval after the arms whose effect an eval
can show. On a large budget, the order matters less.

## Priors

- **A bank's customer-service agent, against a simulated customer, on a
  support benchmark.** Each task was run three times with the same
  skills. In every training and validation set, 16% to 53% of the tasks
  passed on some tries and failed on others. With one try for each task,
  each of those tasks reads as a pass or a fail by chance. One sample, not
  a rule.
  Source: public, the paper "EvoSkill v2: Fully Agentic Skill Evolution
  from Benchmark Adaptation to a Stateful Evolver". 2026-10-23.
