---
title: Malformed tool calls
description: The agent calls a tool with the wrong case, the wrong form of an id, a body on a GET, or a misspelled tool name. A wrapper that normalises, errors the agent can act on, a guard at the tool.
reviewed: 2026-11-13
kind: failure
applies_to:
  - tools
---

# Malformed tool calls

## Situation

The agent chooses the right tool and calls it in a form that the tool
refuses. Look at the tool calls and at the errors that come back:

- an enum value in the wrong case, or a value that is near a valid one;
- a display number or a name where the tool wants an id;
- strings with extra spaces, numbers sent as text, a missing optional
  field that the tool needs;
- a body on a GET, or a filter in a syntax that the tool does not accept;
- a tool name that does not exist: a misspelling of a real tool's name.

The same errors repeat across items and across tools. The model knows
what it wants to do. The form is the problem.

## What to try, in order

1. [Normalize inputs wrapper](references/improving_agents/techniques/normalize-inputs-wrapper.md),
   when the agent sends a form that can be mapped to a valid one: case,
   aliases, display numbers, types, trimmed strings, defaults.
2. [Errors the agent can act on](references/improving_agents/techniques/errors-the-agent-can-act-on.md),
   when a form cannot be mapped. The error names what was wrong, the valid
   values or the nearest matches, and what to do next.
3. [New tool description](references/improving_agents/techniques/new-tool-description.md), when the
   agent misspells the tool's name. A wrapper or a clone with a name that
   the model cannot misspell.
4. [Guard tool calls at the boundary](references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md),
   when a malformed call also breaks a rule that the product enforces, for
   example a write that the task does not allow.

Steps 1 and 2 can be one wrapper: it maps what it can, and returns an
error that names the valid values when it cannot.

## What not to do yet

- No prompt list of formatting rules. A list cannot name every form that
  the model will try. A wrapper removes the failure instead of asking the
  model to avoid it. A form that the model must still know goes in the
  parameter description, not in the prompt. This is a very strong
  preference: text in a tool moves with the tool, so a later change of the
  tool set needs no prompt change.
- No model swap for a malformed call. The tool's contract is the problem,
  and a wrapper fixes it for every model.

## Budget

The order does not change with the budget. Each step has a medium cost,
apart from step 3, which has a low cost.
