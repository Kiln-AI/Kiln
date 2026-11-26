---
title: A requirement is missing from the prompt
description: The eval checks for something that neither the prompt nor the task instruction asks for. State the requirement in new words - do not copy the eval.
reviewed: 2026-11-12
kind: failure
applies_to: all
---

# A requirement is missing from the prompt

## Situation

The eval wants X, and the prompt never asks for X. The train set often
shows it clearly. Look at the final output of the failing items, and at
the eval's criteria:

- the output is complete and correct by what the prompt asks, and it
  lacks the one thing that the eval checks;
- the same missing part repeats across many failing items;
- the prompt and the task instruction say nothing about that part, or say
  it only in a way that the model cannot act on.

In a multi-turn task, the missing requirement can be a behaviour: the
synthetic user asks an unclear question, and the eval passes only when the
agent asks a follow-up question first.

When the missing part is the form of the output (a closing block, a
layout, an escaping rule), see
[the output contract is not met](references/improving_agents/playbooks/output-contract-not-met.md).

## What to try, in order

1. [Add the missing requirement](references/improving_agents/techniques/add-the-missing-requirement.md),
   when one requirement explains most of the failing items. One prompt
   rule, in new words, with its reason.
2. [One general rule per
   edit](references/improving_agents/techniques/one-general-rule-per-edit.md),
   when the failing items lack several things. Group them by cause, and
   write one rule for the cause that explains the most items. The next cause
   goes in the next candidate.
3. [The output contract is not met](references/improving_agents/playbooks/output-contract-not-met.md), when the
   missing part turns out to be a format rule.

## What not to do yet

- Do not copy the text of the eval, of its judge or of a spec into the
  prompt. The judge-copy check finds a copied passage and ends the candidate.
  State the rule in new words, from what the task needs (the leak rules of
  `references/knowledge/train_val_test.md`).
- Do not write a rule for each failing item. A rule that names an item's
  values is a leak, and the generality check refuses it.
- No skill, no tool and no model swap. One prompt rule costs less, and it
  is the first thing to measure.
- Do not add the requirement when the prompt already states it and the
  model ignores it. That is a different problem:
  [lost in long instructions](references/improving_agents/playbooks/lost-in-long-instructions.md).

## Budget

The order does not change with the budget.
