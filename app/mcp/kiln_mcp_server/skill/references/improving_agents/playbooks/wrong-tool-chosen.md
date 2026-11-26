---
title: The wrong tool is chosen
description: The agent picks the wrong tool, or breaks a rule that the product enforces. Fit the tool layer first when the agent as a whole needs it, then remove and scope tools, descriptions, guards.
reviewed: 2026-11-13
kind: failure
applies_to:
  - tools
---

# The wrong tool is chosen

## Situation

The agent calls a tool that does not fit the request, or calls the right
tool in a way that the product does not allow. Look at the tool calls of
the failing items:

- the agent calls one of two tools that do almost the same thing, and the
  choice changes from item to item;
- it calls a narrow tool many times where one general tool would do;
- it calls the right tool, and the call breaks a rule of the product: a
  permission, a limit, a default;
- the attached tools are too many for the context, or some overlap or are
  never called: the smells [too many tools](references/improving_agents/smells/too-many-tools.md)
  and [unnecessary tools](references/improving_agents/smells/unnecessary-tools.md).

When the right tool is called with a malformed input, see
[malformed tool calls](references/improving_agents/playbooks/malformed-tool-calls.md).

## What to try, in order

1. [Fit the tool layer to the agent](references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md),
   when that is justified for the agent overall, not only as a fix for
   this failure: the tool smells show in the design. This includes
   [remove or scope tools](references/improving_agents/techniques/remove-or-scope-tools.md), then
   [consolidate tools](references/improving_agents/techniques/consolidate-tools.md), in the order of
   that playbook. Do the fit first, and hold the other steps of this
   playbook until it is measured: it can fix the wrong choice. When it
   does not fix it, or when a fit is not justified, continue with the
   steps below.
2. [Remove or scope tools](references/improving_agents/techniques/remove-or-scope-tools.md), when
   some attached tools are not needed for this task, or two tools overlap
   and one can go.
3. [New tool description](references/improving_agents/techniques/new-tool-description.md), when the
   tool set is right and the descriptions do not say which tool is for
   which request. A new description on a clone or a wrapper of each tool
   that is confused with another.
4. [Guard tool calls at the boundary](references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md),
   when the right tool is called and the call breaks a rule that the
   product enforces.

## What not to do yet

- No prompt list of which tool to use when. Put when to use each tool in
  its own description. This is a very strong preference. Text in a tool
  moves with the tool. So a later experiment that adds, removes or changes
  a tool needs no prompt change, and its result stays clean. A prompt list
  ties the prompt to the tool set, and it grows with each tool.
- Do not put a consolidation and other changes in one candidate. A large change
  together with others gives a result that no one can attribute.

## Budget

Step 1 has a high cost when it consolidates tools. On a small budget, plan
it only when the budget leaves room for an experiment that makes that change
alone. Otherwise start at step 2: steps 2 and 3 each have a low cost.
