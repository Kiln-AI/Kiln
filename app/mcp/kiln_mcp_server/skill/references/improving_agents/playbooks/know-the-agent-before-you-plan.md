---
title: Know the agent before you plan
description: Classify the agent before the first plan - its turns, its output, a classifier shape, its tools, skills and model - because each document says which shapes it fits.
reviewed: 2026-11-13
kind: order
applies_to: all
---

# Know the agent before you plan

## Situation

This is the first step of each run, before wave 1. Do it again after a
promotion that changes the model, the tools or the output.

Each technique, playbook and smell states the task shapes it applies to.
A document that does not fit the shape of this agent is not a candidate.
So find the shape first. Read the task, the baseline run config, the
quick-check answers of the setup reconnaissance in your input, and a few train
traces. Record these facts:

- **Turns.** Single-turn: one request, one answer. It can still make many
  tool calls. Multi-turn: a conversation, where each turn builds on the
  earlier ones. A multi-turn eval is driven by a synthetic user. That user
  can ask an unclear question on purpose, and the agent passes only if it
  asks the right follow-up question.
- **Output.** Structured output (the task has an output schema) or free
  text. A classifier shape: each field of the output takes a small, closed
  set of values.
- **Tools.** Which tools the run config attaches, how many, and of which
  kind (code tools, MCP tools, built-in tools, another Kiln task, a search
  tool). No tools at all is a shape too.
- **Skills.** Which skills are attached, and whether this model opens a
  skill under this run config. A quick check answers that at a low cost.
- **Model and settings.** The model, the provider and the thinking level.
  Whether the model is a lever: only when `allowed_models` lists another
  model, and what the user asked does not forbid a model change.
- **Evals.** What each eval measures, whether a judge or code scores it,
  and how many train items it can pair.
- **Restrictions.** What the user asked and the model policy do not allow.

When the task has no eval for an issue, you do not write one
unless the run turned eval building on. The report then sends the user
to the eval builder in the Kiln app.

## What to try, in order

1. [Ordering work](references/improving_agents/playbooks/ordering-work.md), when the facts above are known. The
   shapes decide which smells and playbooks apply.
2. [Spending the budget](references/improving_agents/playbooks/spending-the-budget.md), to size the plan with
   the prices and the budget in your input.
3. [Working inside
   restrictions](references/improving_agents/playbooks/working-inside-restrictions.md),
   when what the user asked or the model policy states a restriction.
4. Starting points that depend on the shape, each only when its condition
   holds:
   - A single-turn classifier with no tools, and an objective of cost or
     latency:
     [decision model for a classifier](references/improving_agents/techniques/decision-model-for-a-classifier.md).
   - No tools and a long prompt, and a quick check shows that the model does
     not read skills: [structure a long
     prompt](references/improving_agents/techniques/structure-a-long-prompt.md).
   - Many tools that are the company's software APIs:
     [fit the tool layer to the agent](references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md).
   - A multi-turn agent that does not ask the follow-up question that the
     synthetic user waits for:
     [requirement missing from the prompt](references/improving_agents/playbooks/requirement-missing-from-the-prompt.md).

## What not to do yet

- Do not plan a candidate before the shapes are known. A technique for tools
  does nothing for an agent with no tools, and a prompt rule for a format
  does nothing when a schema gives the format.
- Do not assume that a tool or a skill will be used. A quick check settles it
  for a small cost, before a candidate rests on it.
- Do not read a multi-turn failure as a single-turn one. The synthetic
  user's turns are part of the trace. Read them before you name the cause.

## Budget

The order does not change with the budget. The classification costs only
reads and, at most, a quick check.
