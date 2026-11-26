---
title: One-file skill with many topics
description: An attached skill is one long file that holds many topics, with no reference files. The agent reads all of it to use one part of it.
reviewed: 2026-11-13
applies_to: all
---

# One-file skill with many topics

## What it is

An attached skill is one long `SKILL.md` that holds many topics, and it has
no reference files. When the agent opens the skill, it reads every topic to
use one of them. So the skill gives none of the gain of progressive
disclosure, and its one body has the problems of a long prompt. This is a
property of the design, whether an eval passes or fails.

## How to recognise it

In the harness:

- a skill whose bundle has only `SKILL.md`, and whose body is long;
- a body with many headings on different subjects, for example one
  section for each kind of request.

In how the agent runs:

- the agent opens the skill on most items, and each item needs a
  different part of it;
- the read of the skill is a large part of the context of a run that
  uses one topic of it.

## How to confirm it

- Read the skill. List its topics, and check which of them one request
  needs.
- In the sampled traces, check that the agent opens the skill, and which
  part it uses.
- **Not this smell:** a long skill that is one topic, which each run needs
  in full. A skill of a few words is another smell:
  [skill too small to earn its place](references/improving_agents/smells/skill-too-small-to-earn-its-place.md).

## What it blocks

A new rule added to the body of the skill. In one long body, the new rule
has the same chance to be missed as the rules already there.

## Remedies

- [Rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md),
  when the skill can get a new version: a short router body, and one
  reference file for each topic. The text is split, not rewritten in place.
  The description and the body map give the full path of each file, with
  its key terms.
- [Lost in long instructions](references/improving_agents/playbooks/lost-in-long-instructions.md),
  when the traces show the agent miss parts of the skill.
