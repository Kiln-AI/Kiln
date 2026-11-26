---
title: {{TITLE}}
description: {{DESCRIPTION}}
reviewed: {{REVIEWED}}
# all, or a list of: single_turn, multi_turn, structured_output, free_text,
# classifier, tools, no_tools
applies_to: all
---

# {{TITLE}}

## What it is

<!-- One paragraph. A smell is an issue in the design of the agent: it is true whether an eval passes or fails. A reason why one eval item failed is a failure pattern, which is a playbook. -->

{{TEXT}}

## How to recognise it

<!-- The signs in the agent's design (prompt, skills, tools, model, settings), and the signs in how the agent runs (the traces). Where a number shows it, say how to measure it yourself. -->

{{TEXT}}

## How to confirm it

<!-- What to check before it is reported, and what looks like this smell and is not. -->

{{TEXT}}

## What it blocks

<!-- What is not worth an experiment until this smell is fixed. Or the line "Nothing." -->

Nothing.

## Remedies

<!-- A list, with at least one item. Each item links to a playbook or a technique and states its condition. This section holds links, not the fix. -->

- [{{PLAYBOOK_TITLE}}](references/improving_agents/playbooks/{{PLAYBOOK_ID}}.md), when {{TEXT}}
