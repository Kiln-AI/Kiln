---
title: Working inside restrictions
description: The user states a restriction - providers, the origin of a model, data retention, a tool that must not change. It is a hard limit on the plan. What to do when the best lever is not allowed.
reviewed: 2026-11-13
kind: goal
applies_to: all
---

# Working inside restrictions

## Situation

Some limits are known only because the user states them. Examples: models
of one vendor only, by contract; no models of one origin, for regulatory
reasons; providers with zero data retention only; a router is allowed,
but only for models with zero data retention; a tool or a skill that must
not change. A data set can also be sensitive, so that it must not go to a
provider that the user does not trust.

A restriction is a hard limit on the plan, not a preference. It comes
from two places:

- **The models that the user allows**, and the models that the user
  flags. Ask the user. Nothing refuses a run config whose model the user
  does not allow: check it yourself.
- **What the user asked**, in words. Nothing guards a restriction that is
  only in the user's words. The plan is the guard.

A candidate that breaks a restriction wastes its whole cost, because its
result cannot ship. A plan that knows the limits at the start does not
spend experiments on a model that is not allowed.

## What to try, in order

1. Read what the user asked and the models that the user allows before the
   first plan, and list
   each restriction:
   [know the agent before you plan](references/improving_agents/playbooks/know-the-agent-before-you-plan.md).
2. When the best lever for an issue is not allowed, take the next step of
   that issue's playbook that stays inside the limits. Examples:
   - A faster provider is not allowed: less thinking, with the same model
     and provider,
     [thinking level ladder](references/improving_agents/techniques/thinking-level-ladder.md).
   - A model change is not allowed: a change to the harness that does the
     same work, for example a tool that removes a mechanical failure,
     [change the surface, not the words](references/improving_agents/playbooks/change-the-surface-not-the-words.md).
   - A tool must not change: a wrapper is allowed only when the user
     says that the restriction is about the tool's code. A wrapper then
     adds a tool beside it and leaves its code as it is. Otherwise, change
     the text the agent reads about the tool, in the prompt or in a skill,
     [guide skill for a tool set](references/improving_agents/techniques/guide-skill-for-a-tool-set.md),
     and report the question to the user.
3. When no step inside the limits fits an issue, do not plan a candidate
   for it. Report to the user which restriction stops it.

## What not to do yet

- Do not plan a candidate that breaks a restriction, to see if it would help.
  Its result cannot ship, and the spend is lost.
- Do not read a restriction narrowly. "Zero data retention only" covers
  every model and every provider that the plan uses, not only the main
  one.
- Do not ask the user for an exception in the middle of the work. When a
  restriction is unclear, follow its strictest reading, and report the
  question to the user.

## Budget

The order does not change with the budget. On a small budget a
restriction matters more, because a wasted candidate is a larger part of the
budget.
