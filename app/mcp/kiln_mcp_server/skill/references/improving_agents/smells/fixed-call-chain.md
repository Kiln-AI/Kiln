---
title: Fixed call chain
description: The agent calls the same tools in the same order on each run, and passes an id from one result to the next call. The model decides nothing new between the calls.
reviewed: 2026-11-16
applies_to:
  - tools
---

# Fixed call chain

## What it is

The agent calls the same tools in the same order on each run, and it
passes an id or a value from one result to the next call. The model runs
again between each two calls, but it decides nothing new. Each step costs
a turn and context, and each step is one more place where the agent can
pass a wrong value or stop. The tools are made for software, which calls
them in a chain at no cost. This is a property of the design, whether an
eval passes or fails.

## How to recognise it

In the harness:

- tools that each return one part of a record, and take the id of another
  part as input, for example find the user, then get the account, then
  list its orders.

In how the agent runs:

- the same order of tool calls on most sampled items;
- each call takes its main argument from the result before it;
- between two calls of the chain, the model writes a short turn or no
  text at all.

## How to confirm it

- In the sampled traces, write the order of the tool calls of each run,
  and compare them.
- Check where each argument comes from.
- **Not this smell:** an order that changes with the data, where the agent
  chooses the next tool from what it read. That chain carries decisions.
- **Not this smell alone:** a chain that an eval scores. An eval made from
  the Kiln template `tool_call`, a `tool_call_check` eval config, or a
  judge whose criteria name a tool can expect each call of the chain. Read
  the spec of that eval before you name a remedy. A remedy keeps the tool
  names that it expects, or names that eval as a target eval of the
  experiment, as a stated coupling.

## What it blocks

Nothing.

## Remedies

- [Roll-up tool](references/improving_agents/techniques/roll-up-tool.md), when the chain is the
  same on most runs: one code tool that makes the calls in code and
  returns what the agent uses.
- [Fit the tool layer to the agent](references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md),
  when other smells of the tools are present too.
