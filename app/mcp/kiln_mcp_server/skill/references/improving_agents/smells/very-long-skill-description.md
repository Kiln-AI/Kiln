---
title: Very long skill description
description: A skill description is longer than the reference length, or it holds rules that the agent needs only after it opens the skill. Code measures the length.
reviewed: 2026-11-13
applies_to: all
---

# Very long skill description

## What it is

The description in the front matter of an attached skill holds more than
the choice to open the skill needs. Every skill description is in the
context of every run, so its length is paid on every run, whether the
agent opens the skill or not. A description is for the choice to open the
skill. The content belongs in the body and in the reference files. This is
a property of the design, whether an eval passes or fails.

The smell has two forms. Code finds the sure form: a description longer
than the reference length. A reader finds the other form at any length:
rules or facts in the description that the agent needs only after it
opens the skill.

## How to recognise it

In the harness:

- the code detection in your input names the skill, the length of its
  description and the reference;
- with no detection: the description holds rules or facts for the work,
  for example the steps of a procedure, the rules of the product or the
  values of a field.

In how the agent runs:

- the agent acts on the description and does not open the skill.

Kiln limits this field to the reference length today. So a code detection
shows a skill from another source, or a change of that limit.

## How to confirm it

- Read the description, and sort its text in two parts: what helps the
  agent decide to open the skill, and what it needs only after. With no
  detection, report it only when the second part holds rules or facts, and
  quote them in the evidence.
- **Not this smell:** what the skill is for and when to open it, with a
  path index of the reference files and their key terms, that fits inside
  the reference length. That text helps the agent open the right file.

## What it blocks

Nothing.

## Remedies

- [Rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md),
  when the skill can get a new version: a short description, and the rules
  and facts moved into the body or the reference files. When the
  description is long because it lists the files, keep the paths and their
  key terms, and cut the other text.
- [Skill into the prompt](references/improving_agents/techniques/skill-into-the-prompt.md), when
  most runs need the content of the skill.
