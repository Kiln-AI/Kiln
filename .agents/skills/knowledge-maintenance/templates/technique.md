---
title: {{TITLE}}
description: {{DESCRIPTION}}
reviewed: {{REVIEWED}}
status: active  # active, or dormant: a dormant technique is not suggested
# The ids of the lever documents this technique uses. How links each one.
levers:
  - {{LEVER_ID}}
# all, or a list of: single_turn, multi_turn, structured_output, free_text,
# classifier, tools, no_tools
applies_to: all
cost: {{COST}}  # low, medium or high, compared with one prompt edit
---

# {{TITLE}}

## When to use

<!-- The design patterns, goals and failure modes that suggest this technique. State the condition of each. -->

{{TEXT}}

## When not to use

<!-- The conditions under which it does not help, and the problems that look like its problem and are not. -->

{{TEXT}}

## Alternatives

<!-- A list. Each item links to another technique and states when that one is the better choice. Or the line "None." -->

- [{{TECHNIQUE_TITLE}}](references/improving_agents/techniques/{{TECHNIQUE_ID}}.md), when {{TEXT}}

## How

<!-- The recipe, with examples where we have them. Link each lever in `levers`, and no other lever. Do not copy how-to text that the lever or another file of the skill already has. -->

The change is one edit of the [{{LEVER_TITLE}}](references/levers/{{LEVER_ID}}.md).

1. {{TEXT}}

## Check that it took effect

<!-- How to tell, before the evals are paid for, that the change reached the agent and did what it was built to do: a quick check, or a count in a few traces. -->

{{TEXT}}

## Budget

<!-- When to leave it out on a small budget, and when it is a good first step. -->

{{TEXT}}

## If it does not move the evals

<!-- Start with one of the three phrases "Keep it.", "It must move an eval." or "It depends.", then give the conditions. -->

{{STANCE}} {{TEXT}}

## Priors

<!-- A list of real cases, or the line "None yet." Each case is one list item: "- **<shape of the agent, with no name>.** <what was tried>. <what happened>. One sample, not a rule." and then, on the next line, "Source: <public | own experiment | anonymised>. <date>." A person approves a prior before it is committed, unless it is clearly public. -->

None yet.

## Confidence

<!-- Text, with its conditions: how sure we are, and on what basis. A reader must be able to tell an idea that one person proposed from a result seen many times. -->

{{TEXT}}
