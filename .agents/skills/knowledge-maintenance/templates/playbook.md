---
title: {{TITLE}}
description: {{DESCRIPTION}}
reviewed: {{REVIEWED}}
kind: {{KIND}}  # goal, order, failure, eval or design
# all, or a list of: single_turn, multi_turn, structured_output, free_text,
# classifier, tools, no_tools
applies_to: all
---

# {{TITLE}}

## Situation

<!-- The goal, or how to recognise the problem. For the kind "failure": what the trace shows, and where in the trace. A playbook that responds to a smell links to the smell here and does not repeat how to recognise it. -->

{{TEXT}}

## What to try, in order

<!-- A numbered list. Each item links to a technique or a playbook and states its condition. A new technique goes at the place its condition gives, not at the top. -->

1. [{{TECHNIQUE_TITLE}}](references/improving_agents/techniques/{{TECHNIQUE_ID}}.md), when {{TEXT}}

## What not to do yet

<!-- What looks like a fix and is not worth an experiment yet, and why. -->

{{TEXT}}

## Budget

<!-- How the order changes with the budget. Or the line "The order does not change with the budget." -->

The order does not change with the budget.
