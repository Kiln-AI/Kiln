---
title: Dealing with a saturated eval
description: The baseline passes almost every item of an eval, so an arm has no room to show a gain on it. Keep the eval as a guard, put the effort elsewhere, and ask its owner for harder items.
reviewed: 2026-11-13
kind: eval
applies_to: all
---

# Dealing with a saturated eval

## Situation

The baseline passes almost every item of an eval. Signs:

- `train_detectability` gives the score a `room` of 0, or a `room` that
  is a small share of its `n`;
- the few failures that remain are one or two items, or they come and go
  between repeats.

An arm aimed at this eval has little or no room to show a gain on train.
When `room` is also below `floor`, a gain on train can only be nominal.
The eval still has a use: it shows when an arm breaks what the baseline
already does well.

## What to try, in order

1. When an issue targets this eval, and it is not clear that the baseline
   still fails in the way the issue says: measure the issue on the
   current baseline (a `measure_issue_baseline` item). An earlier change
   can have fixed it.
2. Keep the eval as a guard, and target an eval with room. The val gate
   measures this eval before every promotion, so it guards the arms
   there. Do not add it to an arm's train measurement as a routine
   guard. Add it only when you have a stated reason to fear that the
   arm breaks it, under the planner's skill for `evaluation_target`.
3. Put the effort on the issues and the evals that have room:
   [ordering work](references/improving_agents/playbooks/ordering-work.md).
4. When the few failures that remain are false fires (the judge fails
   right answers):
   [dealing with a wrong eval](references/improving_agents/playbooks/dealing-with-a-wrong-eval.md).
5. Tell the eval's owner in `open_questions` that the eval needs harder
   items, or more items, to steer the tuning. The tuner does not change an
   existing eval. Only when `eval_building` is `true`, an `eval_only` item
   can commission a new eval with harder items for an open issue, under
   the rules of the planner's skill for that item.

## What not to do yet

- No fix arm aimed only at this eval while its `room` is 0. It cannot
  show a gain on train, so its spend is lost.
- Do not drop the eval from the guards because it shows no gain. The
  baseline fails almost nothing on it, so a break is easy to see.

## Budget

The order does not change with the budget. Steps 1 and 2 cost little.
