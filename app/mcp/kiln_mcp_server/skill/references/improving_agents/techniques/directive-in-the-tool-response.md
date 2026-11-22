---
title: Directive in the tool response
description: A wrapper whose response states the tool's own status for the reply - derived facts, a fixable error, or how the tool works - as facts about the result, not as orders to the agent.
reviewed: 2026-11-13
status: active
levers:
  - new_tool
applies_to:
  - tools
cost: medium
---

# Directive in the tool response

## When to use

- **The failure is in the reply after a tool call.** The call is right,
  and the reply misstates the result: it leaves out a fact, states a wrong
  one, or does not see that the result is empty or partial.
- The agent must state facts that come from the result, and it computes
  them wrong or leaves them out: counts, the filters applied, dates and
  time zones resolved from a relative date.
- The agent repeats a call that the tool cannot serve, and the result does
  not say how to fix it: an invalid value, an empty result, a range that
  is too narrow.
- A new tool description fixed the call, and the reply that follows the
  call still fails.

## When not to use

- **The failure is before or with the call.** The rule for the call goes
  in the tool's description:
  [new tool description](references/improving_agents/techniques/new-tool-description.md).
- **The rule is about the reply in general**: a format, a thing not to
  say. It does not depend on the result. It goes in the tool's
  description, not in the result:
  [new tool description](references/improving_agents/techniques/new-tool-description.md).
- **The reply needs no tool.** A response field can only come back from a
  call that the agent makes. The rule then belongs where the agent reads
  it without a tool.
- **The field needs judgement about the item.** The field is fixed text,
  or facts that code derives. When it needs judgement, it is a rule for
  the model, not for the tool.
- **The rule is a hard limit of the product.** A response field states. A
  guard refuses:
  [guard tool calls at the boundary](references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md).

## Alternatives

- [New tool description](references/improving_agents/techniques/new-tool-description.md), when the failure is at
  the decision to call, or the rule is about the reply in general.
- [Errors the agent can act on](references/improving_agents/techniques/errors-the-agent-can-act-on.md), when the
  tool already refuses the call and its error text is the problem.
- [Roll-up tool](references/improving_agents/techniques/roll-up-tool.md), when the agent does not call a tool at
  all and a context loader with a prompt line would bring the facts in.
- [Guard tool calls at the boundary](references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md),
  when the reply leads to a call that the product does not allow.

## How

The change is a wrapper of the tool that comes before the reply, on a new
run config, with the wrapped tool dropped. See the lever
[new_tool](references/levers/new_tool.md) for the build. The template
`context_on_tool_surface.py` of the code-tool authoring skill has this
shape: a description read before the call, and a field in the response
read before the reply.

1. **Find the call that comes before the failing reply** in a few traces.
2. **Write a named field in the response**, for example `notes`, with one
   or two short lines. It is the tool's own status. Write it as a fact
   about the result, a fixable error, or a fact about how the tool works
   and how to call it. Do not write it as an order to the agent.
   - **Derived facts**, computed by code from the result: "3 orders;
     filtered to the last 30 days; dates in UTC". The agent then copies
     them and does not compute them.
   - **A fixable error, or the next valid action**: "date invalid; use
     YYYY-MM-DD", "no rows; widen the date range".
   - **A fact about how the tool works or how to call it**: "dates are
     UTC; pass a time zone to get local dates".
3. **Put the rules about the reply in general in the tool's description**,
   not in the result: a format, a thing not to say.
4. **Keep the rest of the result as the wrapped tool returns it**, unless
   another change trims it.
5. **Move the prompt text that the wrapper takes over**, on the same arm.
   A rule about the call, or about the reply in general, goes into the
   tool's description. A step that the field now does for the model (a
   count, a resolved date) is dead text: remove it. Text in a tool moves
   with the tool. So a later experiment that adds, removes or changes the
   tool needs no prompt change, and its result stays clean.
6. **Write from the rule and the traces**, never from the text of an eval
   or from a train item.

## Check that it took effect

Dry-run the wrapper and read its response: the field is there, with the
expected facts or the expected error. Read the tool's description and the
prompt: the rules that moved are in the description, and not in the
prompt. Then smoke two or three train items that failed in the reply. In
each trace, find the field in the tool result and the reply that follows
it.

## Budget

Medium cost: a wrapper and a dry run, and a measurement on its target
evals. When it fixes its target, the val gate measures every eval before a
promotion, the evals that the reply touches too. On a small budget, take
it after a new description, when the reply still fails after a right
call.

## If it does not move the evals

It must move an eval. The change exists to fix a failure in the reply.
When the count of those failures does not fall, the agent did not read the
field, or the failure is not at that reply.

## Priors

None yet.

## Confidence

Low to medium. It is reasoning, not a measurement. Facts that code
derives remove a computation that the model can get wrong, and a
fixable error says how to correct the call. No measured case is
recorded here yet.
