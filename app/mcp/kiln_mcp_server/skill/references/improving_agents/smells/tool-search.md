---
title: Tool search
description: The tools are listed nowhere the model can read, so the agent must guess that a tool exists and guess the raw search terms that find it.
reviewed: 2026-11-13
applies_to:
  - tools
---

# Tool search

## What it is

The agent does not see its tools. It sees a search tool, and it must find
each other tool through it. Nothing that the model can read lists the
tools: not the prompt, not a skill, not the search tool's description. So
before each call the agent must guess that a tool exists, and guess the
raw search terms that find it. Each guess can fail, and each search costs a
turn and context. This is a property of the design, whether an eval passes
or fails.

## How to recognise it

In the harness:

- a tool whose description says that it finds, lists or loads other tools;
- no list of those tools, or of their names, in the prompt, in a skill or
  in the search tool's description.

In how the agent runs:

- searches for tools before the calls that do the work;
- searches with terms that find nothing, then a guess;
- more tool searches in a run than calls of the tools that they find.

## How to confirm it

- Open the search tool's definition, and confirm that it returns tools,
  not data.
- Read the prompt and each skill for the names of the tools that the
  search can find.
- In the sampled traces, count the tool searches, and the searches that
  return nothing or the wrong tool.
- **Not this smell:** tool search with a way to search well, for example a
  skill with progressive disclosure that names the tools and their key
  terms. The agent then knows what exists, and the search only loads it.
  A search tool over documents or records is not this smell either: it
  finds data, not tools.

## What it blocks

A change to the description of one tool that the agent reaches through
search. The agent reads that description only after the search finds the
tool.

## Remedies

- [Remove or scope tools](references/improving_agents/techniques/remove-or-scope-tools.md), when
  the traces show that the task uses a few of the tools: attach those few
  directly, so that they are always in context, and drop the search.
- [Guide skill for a tool set](references/improving_agents/techniques/guide-skill-for-a-tool-set.md),
  when the model opens skills: a skill that names the tools by progressive
  disclosure, so that the agent knows what exists before it searches.
- [Consolidate tools](references/improving_agents/techniques/consolidate-tools.md), to consider, in
  the collapsed style: one general tool that can call each operation, such
  as a `call_api` tool, with a guide skill that names the operations. A
  `search_tools` call and an `add_tool` call before each use are extra
  steps, and this style removes them.
