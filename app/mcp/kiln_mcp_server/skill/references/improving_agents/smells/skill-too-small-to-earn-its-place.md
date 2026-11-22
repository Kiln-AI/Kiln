---
title: Skill too small to earn its place
description: An attached skill holds a few words and no other file. Its description is in every run and opening it costs a call, so it can cost more than it saves.
reviewed: 2026-11-13
applies_to: all
---

# Skill too small to earn its place

## What it is

An attached skill holds a few words in its body, and no reference file. Its
description is in the context of every run, and the agent needs one more
call to read the body. When the body is about as short as the description,
the skill saves no context and adds a call. This is a property of the
design, whether an eval passes or fails.

## How to recognise it

In the harness:

- a skill whose bundle has only `SKILL.md`, with a body of a few lines;
- a body that repeats its own description, or adds one or two rules to it.

In how the agent runs:

- the agent opens the skill on most items, so its text is read on each of
  them;
- or the agent never opens it, so its content never reaches the model.

## How to confirm it

- Compare the length of the body with the length of the description.
- In the sampled traces, count the items where the agent opens the skill.
- **Not this smell:** a short body that routes to reference files. That
  skill is small because it uses progressive disclosure.

## What it blocks

Nothing.

## Remedies

- [Skill into the prompt](references/improving_agents/techniques/skill-into-the-prompt.md), when
  the content is needed and short enough for the prompt: move it there and
  drop the skill.
- [Prune one group at a time](references/improving_agents/techniques/prune-one-group-at-a-time.md),
  when it is not known that the content helps: drop the skill on one
  candidate and measure it.
