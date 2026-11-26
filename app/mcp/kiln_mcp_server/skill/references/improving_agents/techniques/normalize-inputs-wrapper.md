---
title: Normalize inputs wrapper
description: A wrapper that accepts the input forms the agent sends - case, aliases, display numbers, types - maps each to what the tool needs, and names the valid values when it cannot.
reviewed: 2026-11-13
status: active
levers:
  - new_tool
applies_to:
  - tools
cost: medium
---

# Normalize inputs wrapper

## When to use

- The agent makes calls that fail on the form of an input: the wrong
  case of an enum value, a display number where the tool needs an id, a
  string where the tool needs a number, extra whitespace, a known alias.
- The same kind of malformed call appears on many items, and the agent's
  intent is clear in each one.
- The agent sends a body with a call that takes none, or leaves out an
  optional field that has a safe default.

## When not to use

- **The intent is not clear from the input.** When code cannot map a value
  to one meaning, a guess in the wrapper hides the error. Return the valid
  values and let the agent choose.
- **The agent calls a tool name that does not exist.** That is a name the
  agent cannot write: [new tool description](references/improving_agents/techniques/new-tool-description.md),
  with a new name.
- **The tool returns an error that the agent cannot read, and the input
  was right.** [Errors the agent can act on](references/improving_agents/techniques/errors-the-agent-can-act-on.md).
- **A prompt list of formatting rules is not the fix.** The wrapper
  accepts what the model sends. When the model must still know a form,
  prefer the parameter description to the prompt. Text in a tool moves
  with the tool. So a later experiment that changes the tool set needs no
  prompt change, and its result stays clean.

## Alternatives

- [Errors the agent can act on](references/improving_agents/techniques/errors-the-agent-can-act-on.md), when the
  inputs vary too much to map, and an error with the valid values lets the
  agent correct itself.
- [New tool description](references/improving_agents/techniques/new-tool-description.md), when one parameter
  description that states the form would fix most of the calls.

## How

The change is a wrapper of the tool on a new run config, with the wrapped
tool dropped. See the lever [new_tool](references/levers/new_tool.md) for
the build. The template
`references/knowledge/code_tool_wrappers/normalize_inputs.md` has this
shape.

1. **List the malformed calls** from a few traces: the parameter, the form
   that the agent sent, and the form that the tool needs.
2. **Map each form in code.**
   - Enum values: accept any case, and map known aliases.
   - Ids: map a display number or a name to the id, with a read.
   - Types: coerce a number sent as a string, and a string sent as a
     number.
   - Strings: trim whitespace.
   - Optional fields: set the safe default when the agent leaves it out.
3. **When a value cannot be mapped**, return an error that names the
   valid values, or the nearest matches. Do not pass the raw error of the
   tool.
4. **Keep the parameter names** of the wrapped tool, so that the calls in
   the agent's habit still fit.
5. **Remove the prompt text on input formats** that the wrapper takes
   over, on the same candidate. A form that the wrapper cannot map, and that the
   model must know, goes in the parameter description.

## Check that it took effect

Dry-run the wrapper with each malformed form from the traces. Each one
maps, or returns an error that names the valid values. Then smoke two or
three train items that had malformed calls, and count the failed calls.

## Budget

Medium cost: a wrapper with a mapping, a dry run for each form, and a
measurement on its target evals. When it fixes its target, the confirmation
on val measures every eval before a promotion, the evals that the tool
touches too. A good step on any budget when malformed calls recur in the
traces, because it removes a failure that text can only ask the model to
avoid.

## If it does not move the evals

It depends. Keep it when the failed calls, the retries or the cost per
item fall and no eval goes down: each failed call costs a model turn. When
the failed calls do not fall, the mapping does not cover the forms that
the agent sends.

## Priors

None yet.

## Confidence

Medium. It is field practice, and it follows from where the failure is:
the model sends a form that code can map with no doubt, so code removes
the failure. Low, for the size of the gain on a given agent: no measured
case is recorded here yet.
