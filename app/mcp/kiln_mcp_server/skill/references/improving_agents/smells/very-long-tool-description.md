---
title: Very long tool description
description: The description of an attached tool is longer than the reference length, 4,096 characters. A code detector measures each tool, and each detection names the tool.
reviewed: 2026-11-13
applies_to:
  - tools
---

# Very long tool description

## What it is

The description of an attached tool is longer than the reference length,
4,096 characters.
Each tool description is in the context of every call. A long one costs
tokens on every call, and the model reads it at the moment it chooses a
tool, when it needs only what the tool does and when to call it. Some agent
products cut a description at a fixed length, so the end of it is never
read. This is a property of the design, whether an eval passes or fails.

## How to recognise it

In the harness:

- the code detection in your input names the tool, the length of its
  description and the reference;
- the description holds a manual: many examples, the schema of the data,
  rules for other tools, or the policy of the product.

In how the agent runs:

- the agent calls the tool only in the forms that the start of the
  description shows, and never uses an option that only the later text
  names.

## How to confirm it

- Open the tool definition, and read what the description holds after its
  first paragraph.
- **Not this smell:** a long parameter schema with a short description.
  The parameters describe the input. Read them as part of the tool, not as
  its description.

## What it blocks

A new rule added to the description. In a long description, the new rule
is one more line among many at the moment the agent chooses a tool. In a
product that cuts a long description, the rule can also fall after the cut.

## Remedies

- [New tool description](references/improving_agents/techniques/new-tool-description.md), when the
  description can be shorter: a code-tool clone or a wrapper with a
  description that says what the tool does and when to call it.
- [Guide skill for a tool set](references/improving_agents/techniques/guide-skill-for-a-tool-set.md),
  when the description holds a manual for the tool, which can move into a
  skill that the agent reads when it needs it.
- [Fit the tool layer to the agent](references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md),
  when other smells of the tools are present too.
