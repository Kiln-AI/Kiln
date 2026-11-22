---
title: New tool description
description: A new description for a tool - a code-tool clone, or a wrapper - for a failure at a call. A rule in the tool moves with the tool, so the prompt does not change with the tool set.
reviewed: 2026-11-13
status: active
levers:
  - new_tool
applies_to:
  - tools
cost: low
---

# New tool description

## When to use

- **The failure is at the decision point of a call.** The failing message
  comes before or with a tool call: a preamble that the task does not
  allow, a narration with the call, a call that is not needed, or no call
  where one is needed.
- The agent calls the wrong tool of two that look alike, and the
  descriptions do not say when to use each.
- The agent passes a wrong argument, and the parameter description does
  not say what the argument is or what form it takes.
- The agent misspells the tool's name, or calls a name that does not
  exist. A clearer name is a new tool too.
- **A rule about one tool is in the prompt**, or the plan is a prompt edit
  for a failure at a call. Prefer the tool's description to the prompt, a
  skill body or a skill description. This is a very strong preference.
  Text in a tool moves with the tool. So a later experiment that adds,
  removes or changes the tool needs no prompt change, and its result stays
  clean. A
  rule about a tool in the prompt ties the prompt to the tool set, and a
  later change of the tools can leave it out of date.

## When not to use

- **The failure comes after the tool result**, and the reply misstates
  the result: a fact that it leaves out or gets wrong. The result is the
  text to change:
  [directive in the tool response](references/improving_agents/techniques/directive-in-the-tool-response.md). A
  rule about the reply in general, such as a format, can go in this
  description.
- **The tool works, and the call is right, but the result is too large**
  or the call fails on a form that code could fix. Change what the tool
  does, not what it says: [cap and preview wrapper](references/improving_agents/techniques/cap-and-preview-wrapper.md),
  [normalize inputs wrapper](references/improving_agents/techniques/normalize-inputs-wrapper.md).
- **The rule is not about one tool**: it applies to all the work of the
  agent. That rule goes in the prompt.
- **The description is already long.** Add the missing point and remove
  text that does not help the decision. A longer description is read on
  every call.

## Alternatives

- [Directive in the tool response](references/improving_agents/techniques/directive-in-the-tool-response.md),
  when the reply after the call misstates the result.
- [Normalize inputs wrapper](references/improving_agents/techniques/normalize-inputs-wrapper.md), when the agent
  sends inputs in many forms and code can map each one.
- [Consolidate tools](references/improving_agents/techniques/consolidate-tools.md), when many tools overlap and
  no description can make the choice clear.

## How

The change is a new tool, because the description of an attached tool is
fixed: a clone of a code tool with the new description, or a wrapper of an
MCP or built-in tool. See the lever [new_tool](references/levers/new_tool.md) for
the build, and drop the old tool on the same run config.

1. **Name the decision point.** From the analyzer's findings or the
   traces: which tool, and whether the failure came before, with or after
   the call.
2. **Write the description for that decision.** Say what the tool does,
   when to call it, and when not to. When the failure is a preamble or a
   narration, say what the agent does with the call (for example, "call
   this before you reply, with no text before the call").
3. **Write each parameter description**: what the value is, its form, and
   an invented example when the form is not plain.
4. **A name the agent can write.** When the traces show a misspelled or
   invented tool name, give the clone a short name in the words that the
   agent uses. The new tool needs a fresh function name in any case.
5. **Keep it short.** The description is read on every call of every
   item. Do not copy the whole prompt into it.
6. **Move the rule out of the prompt.** On the same arm, remove the prompt
   text about this tool that the new description now states.
7. **Write from the traces and the tool**, never from the text of an eval
   or from a train item.

## Check that it took effect

Read the new run config: the new tool is attached, the old one is gone,
and the description that the model sees (`get_tool_definition`) is the
new text. The prompt no longer states the rule that moved. Then smoke two
or three train items that failed at that call, and count the calls in the
right form.

## Budget

Low cost: a clone or a thin wrapper, and one measurement. A good first
step on any budget when the failure is at the decision point of one call.

## If it does not move the evals

It must move an eval. The change exists to fix a failure at one call. When
the count of those failures does not fall, the description did not reach
the decision, or the failure is of another kind. A description that only
reads better is not worth a new tool.

## Priors

None yet.

## Confidence

Medium, for a failure at the decision point of one call. It is field
practice: the description and the parameters of a tool say what the call
is and what form it takes. The preference for the description over the
prompt is a design choice of the tuner: the prompt does not change with
the tool set. It is not a claim that a description works better than a
prompt line. Low, for a change of description with no failure that it
targets: a longer description can add steps.
