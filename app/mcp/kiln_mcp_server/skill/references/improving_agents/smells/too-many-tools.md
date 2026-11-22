---
title: Too many tools
description: The run config attaches more than 40 tools, and every tool definition is in the context of every call. Count them yourself.
reviewed: 2026-11-13
applies_to:
  - tools
---

# Too many tools

## What it is

The agent has more tools than the reference count, 40, and the definition of
each tool is in the context of every call. The tool definitions then take a
large part of the context before the agent reads the request. Each call
pays for them, and at each step the agent chooses among all of them. This
is a property of the design, whether an eval passes or fails.

## How to recognise it

In the harness:

- count it yourself: the run config attaches more than 40 tools. Skills
  are not counted.

In how the agent runs:

- the tool definitions are a large part of the input of each call;
- the agent calls a few of the tools, and most of them are never called.

## How to confirm it

- Check that the tools are all in context on each call: they are attached
  to the run config, not found through a search tool.
- The reference is a default of Kiln Harness Tuner, not a measured
  optimum. Say so when you state how sure you are.
- **Not this smell:** tools that load only when the agent finds them, for
  example through tool search. Their definitions are not in each call. For
  that design, see [tool search](references/improving_agents/smells/tool-search.md).
- Tools that overlap or are never called are a second smell,
  [unnecessary tools](references/improving_agents/smells/unnecessary-tools.md). Report it on its own, with its
  trace evidence.

## What it blocks

A new tool added to the set. It is one more definition among many on each
call, and its effect is hard to see.

## Remedies

- [Fit the tool layer to the agent](references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md),
  first, when the fit is justified for the agent overall. It gives the
  order across the tool smells: remove or scope tools, then consolidate
  them.
- [Remove or scope tools](references/improving_agents/techniques/remove-or-scope-tools.md), when
  the traces show tools that this task does not use.
- [Consolidate tools](references/improving_agents/techniques/consolidate-tools.md), when the tools
  that remain are still many and each is needed for part of the work: a
  few general wrappers by job, in an experiment that makes this change alone.
