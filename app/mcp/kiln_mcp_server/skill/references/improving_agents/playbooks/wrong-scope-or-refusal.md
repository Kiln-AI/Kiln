---
title: Wrong scope or refusal
description: The agent answers requests outside its scope, or refuses valid ones. A paragraph of decline rules, then a rebalance for the refusals that remain.
reviewed: 2026-11-12
kind: failure
applies_to: all
---

# Wrong scope or refusal

## Situation

The failure is in what the agent agrees to do, not in how well it does it.
Look at the first part of the final answer:

- the agent answers a request that the task says it must decline (an
  off-topic request, an action it is not allowed to take);
- or it refuses a request that the task covers, often because the request
  uses a word that sounds like a forbidden topic;
- or it declines in the wrong way: no reason, no next step, or the wrong
  tone for the task.

The eval shows both errors when it has items on each side of the scope.

## What to try, in order

1. [Decline rules paragraph](references/improving_agents/techniques/decline-rules-paragraph.md),
   when the prompt has no clear statement of scope. One paragraph: what
   the agent does, what it declines, how it declines, and what is not a
   reason to decline.
2. Read the residual failures of that arm. When refusals of valid requests
   remain, rebalance the same paragraph in the next arm: state what is in
   scope more clearly, and the signs that are not a reason to decline,
   with the same
   [technique](references/improving_agents/techniques/decline-rules-paragraph.md).

## What not to do yet

- No list of topics to decline. A list tells the model which words to
  refuse. It then refuses valid requests that use those words, and it
  misses off-topic requests that use other words.
- Do not add a rule for each refused item. Find the general sign that the
  model misreads.
- No model swap. The scope is an instruction, and a stronger model still
  needs it.

## Budget

The order does not change with the budget.
