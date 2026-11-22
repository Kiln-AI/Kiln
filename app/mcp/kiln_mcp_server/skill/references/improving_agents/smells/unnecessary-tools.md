---
title: Unnecessary tools
description: Tools that overlap - two tools used for the same kind of request - or tools never called in the traces. One tool for each job, and each tool needed.
reviewed: 2026-11-13
applies_to:
  - tools
---

# Unnecessary tools

## What it is

Some attached tools are not needed. Two tools do the same job, or a tool is
never called on this task. A good tool set has one tool for each job, and
each tool in it is needed. Each extra tool is one more definition in the
context, and each tool that looks like another is one more way to choose
wrong. This is a property of the design, whether an eval passes or fails.

## How to recognise it

In the harness:

- two tools with names or descriptions that say the same job;
- a tool for work that this task does not do.

In how the agent runs:

- for requests of the same kind, the agent calls one tool of a pair on
  some items and the other tool on others;
- an attached tool that is never called in the sampled traces.

## How to confirm it

- The trace evidence is required. A sign in the harness alone is not
  enough: two tools that look alike can each serve a different request.
- For an overlap, name the pair, the kind of request, and the items where
  the agent calls each tool.
- For a tool that is never called, read more train traces, of every eval,
  before you report it. The sample is small, and a tool that one class of
  item needs is not unnecessary.
- **Not this smell:** many tools that each do a different job that the
  task needs. A count above the reference is a second smell:
  [too many tools](references/improving_agents/smells/too-many-tools.md).

## What it blocks

A new description to tell two overlapping tools apart. When one of the two
can go, the description is not needed.

## Remedies

- [Remove or scope tools](references/improving_agents/techniques/remove-or-scope-tools.md), first:
  drop the tools that are never called, and one tool of an overlapping
  pair, each on its own candidate.
- [Consolidate tools](references/improving_agents/techniques/consolidate-tools.md), when the
  overlapping tools each do part of the job well, so neither can go alone.
- [New tool description](references/improving_agents/techniques/new-tool-description.md), when both
  tools of a pair are needed, and their descriptions do not say which is
  for which request.
- [Fit the tool layer to the agent](references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md),
  when other smells of the tools are present too.
- [Wrong tool chosen](references/improving_agents/playbooks/wrong-tool-chosen.md), when the traces
  show the agent choose the wrong tool.
