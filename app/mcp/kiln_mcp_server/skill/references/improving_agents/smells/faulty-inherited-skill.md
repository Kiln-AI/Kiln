---
title: Faulty inherited skill
description: A skill that the baseline attaches is wrong or stale, contradicts the task, or holds an example whose answer contradicts a rule. It can be changed as a new version.
reviewed: 2026-11-13
applies_to: all
---

# Faulty inherited skill

## What it is

A skill that the baseline attaches has a fault in its content: a fact that
is wrong, a description of tools, routes or fields that the agent does not
have, a rule that contradicts the task, or an example whose answer
contradicts a rule. The agent follows the skill, so the fault reaches the
output. This is a property of the design, whether an eval
passes or fails.

## How to recognise it

In the harness:

- a skill that names tools, fields or steps that the run config does not
  have;
- a rule in a skill that says the opposite of the prompt or of the task's
  instruction;
- a block of examples with inputs and answers, where one answer
  contradicts the prompt, the task's instruction or another rule in the
  same skill.

In how the agent runs:

- the agent calls a tool or a field that the skill names and that does not
  exist;
- the agent follows the skill against the prompt.

## How to confirm it

- Read the whole skill, with its reference files, beside the prompt, the
  task's instruction and the tool list.
- State each fault with the file and the words. For an example block,
  quote the answer and the text that it contradicts, both.
- **Not this smell:** a block of examples whose answers contradict no
  other text. Worked examples are a normal technique, and the review does
  not judge whether an answer is right. A skill that copies train items
  word for word is not this smell either: the baseline audit reports that
  as its own issue. A skill that is right and that the agent does not open
  is a failure pattern, not a fault of the skill.

## What it blocks

A prompt rule that works around the skill. The skill is part of what you
can change, and a rule around it leaves the fault in place.

## Remedies

- [Rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md),
  first: a new version of the skill, with the fault removed, attached in
  place of the old one. When the agent does not open the reference file it
  needs, the new version also restructures it: the full path of each file,
  with its key terms, in the description and in the body map.
- [Prune one group at a time](references/improving_agents/techniques/prune-one-group-at-a-time.md),
  when the skill may not help at all: drop it on one candidate and measure it.
