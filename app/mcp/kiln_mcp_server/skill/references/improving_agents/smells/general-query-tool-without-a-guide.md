---
title: General query tool without a guide
description: The agent has a SQL, GraphQL or general API tool, with no examples and no guide to the schema, so it must learn the data model on each run.
reviewed: 2026-11-13
applies_to:
  - tools
---

# General query tool without a guide

## What it is

The agent has a general query tool: SQL, GraphQL, or a general API that
takes a path or a query. Nothing in the harness gives it sample queries or
a guide to the schema. So on each run the agent must learn the data model:
which tables or types exist, how they join, which fields hold dates and in
which form. It learns by trial, with failed queries and schema reads, and
it can forget it in the same run. This is a property of the design, whether
an eval passes or fails.

## How to recognise it

In the harness:

- a tool whose input is a query string or an API path;
- no skill, no prompt text and no text in the tool's own description with
  sample queries, the main tables or types, or the rules of the data.

In how the agent runs:

- schema reads or listings before the first useful query;
- queries that fail on a name, a join or a date form, then a second try;
- different queries for the same kind of question on different items.

## How to confirm it

- Read the prompt, each skill and the tool's own description for sample
  queries and a description of the schema.
- In the sampled traces, count the failed queries and the schema reads
  before the first query that returns data. The traces decide.
- **Not this smell:** the tool description or the prompt gives the schema,
  and the traces show no failed query and no schema read before the first
  query that returns data.
- **Not this smell:** a narrow tool with fixed parameters, which needs no
  query language.

## What it blocks

A change to how the agent words its answer. While the agent cannot get the
data, the answer has nothing correct to word.

## Remedies

- [Guide skill for a tool set](references/improving_agents/techniques/guide-skill-for-a-tool-set.md),
  first: a side skill with sample queries at each level, the schema as
  leaf files, and the rules of dates and times.
- [Cap and preview wrapper](references/improving_agents/techniques/cap-and-preview-wrapper.md),
  when a query can also return a very large result.
- [Fit the tool layer to the agent](references/improving_agents/playbooks/fit-the-tool-layer-to-the-agent.md),
  when other smells of the tools are present too.
