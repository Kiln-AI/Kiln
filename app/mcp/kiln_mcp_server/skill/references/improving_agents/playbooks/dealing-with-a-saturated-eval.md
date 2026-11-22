---
title: Dealing with a saturated eval
description: The baseline passes almost every item of an eval, so a candidate has no room to show a gain on it. Keep the eval as a guard, put the effort elsewhere, and ask the user for harder items.
reviewed: 2026-11-13
kind: eval
applies_to: all
---

# Dealing with a saturated eval

## Situation

The baseline passes almost every item of an eval. Signs:

- the score has a room of 0 on train, or a room that is a small share of
  its items. The room is the number of train items not at the best value.
  Kiln Harness Tuner measures it for each score, and this sign applies
  when running it;
- the few failures that remain are one or two items, or they come and go
  between repeats.

A candidate aimed at this eval has little or no room to show a gain on
train. When the room is also below the floor (the fewest wins, all one
way, that a paired test needs; Kiln Harness Tuner measures it), a gain on
train can only be nominal. The eval still has a use: it
shows when a candidate breaks what the baseline already does well.

## What to try, in order

1. When an issue targets this eval, and it is not clear that the baseline
   still fails in the way the issue says: measure the issue on the
   current baseline. An earlier change can have fixed it.
2. Keep the eval as a guard, and target an eval with room. The
   confirmation on val measures this eval before a candidate becomes the
   baseline, so it guards the candidates there. Do not add it to a
   candidate's train measurement as a routine guard. Add it only when you
   have a stated reason to fear that the candidate breaks it.
3. Put the effort on the issues and the evals that have room:
   [ordering work](references/improving_agents/playbooks/ordering-work.md).
4. When the few failures that remain are false fires (the judge fails
   right answers):
   [dealing with a wrong eval](references/improving_agents/playbooks/dealing-with-a-wrong-eval.md).
5. Tell the user that the eval needs harder items, or more items, to
   steer the tuning. An experiment does not change an existing eval. Only
   when the user agrees that you build evals, a new eval with harder items
   can be built for an open issue (`references/knowledge/create_spec.md`).
   It is the rare exception, not a routine step. Build none for a closed
   issue. When the new eval cannot reproduce the issue, close the issue as
   won't fix, and never reopen an issue that is fixed.

## What not to do yet

- No fix candidate aimed only at this eval while it has no room. It cannot
  show a gain on train, so its spend is lost.
- Do not drop the eval from the guards because it shows no gain. The
  baseline fails almost nothing on it, so a break is easy to see.

## Budget

The order does not change with the budget. Steps 1 and 2 cost little.
