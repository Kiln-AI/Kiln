---
title: Failure at a tool call
description: The failing message comes before or with a tool call - a preamble, or a narration that rides the call. A new tool description, then a directive in the tool's response.
reviewed: 2026-11-13
kind: failure
applies_to:
  - tools
---

# Failure at a tool call

## Situation

The failure is at the moment the agent calls a tool. Find the failing
message in the trace, and where it is compared with the tool calls:

- **before** a tool call: a preamble or a promise that the task does not
  want, written just before the call;
- **with** a tool call: a narration that rides in the same message as the
  call;
- **after** a tool's result: the reply ignores or restates the result in a
  way that the task does not want.

Naming the decision point is process. When you read the results, write
down before, with or after which tool the failure comes. Then choose the
text to change. Before or with a call, that text is the
tool's description. After a call, it is the tool's response, and a rule
about the reply in general goes in the tool's description.

## What to try, in order

1. [New tool description](references/improving_agents/techniques/new-tool-description.md), when the
   failing message is before or with the call. A code tool gets a new
   description on a clone. Any other tool gets one through a wrapper. The
   rule moves from the prompt into the description, on the same candidate.
2. [Directive in the tool response](references/improving_agents/techniques/directive-in-the-tool-response.md),
   when the failing message is after the call, or step 1 did not hold. A
   wrapper whose response states derived facts, a fixable error, or how
   the tool works, as facts about the result.

## What not to do yet

- No prompt rule, no change to a skill body and no change to a skill
  description for a failure at the call, while the tool's text can carry
  the rule. This is a very strong preference. Text in a tool moves with
  the tool. So a later experiment that adds, removes or changes a tool needs
  no prompt change, and its result stays clean. A prompt rule about a tool
  ties the prompt to the tool set, and a later change of the tools can
  leave it out of date. Also, the description applies to that one tool,
  and a prompt list of tool rules grows with the tool set.
- Do not plan a third text change on the same issue after two failed:
  [change the surface, not the words](references/improving_agents/playbooks/change-the-surface-not-the-words.md).

## Budget

The order does not change with the budget. Step 1 has a low cost, and
step 2 a medium cost.
