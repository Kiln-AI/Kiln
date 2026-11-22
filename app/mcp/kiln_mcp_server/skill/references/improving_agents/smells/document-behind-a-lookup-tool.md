---
title: Document behind a lookup tool
description: A long reference document that the agent can reach only by page, by search or by section, through a lookup tool, with no contents to choose from.
reviewed: 2026-11-13
applies_to:
  - tools
---

# Document behind a lookup tool

## What it is

A long reference document, for example a policy, a manual or a catalogue,
is behind a lookup tool. The agent can read it only by page, by a search
term or by a section name. It does not see what the document holds before
it asks. So it must guess where a fact is, and it can read the wrong part,
read many parts to find one fact, or not look at all. This is a property of
the design, whether an eval passes or fails.

## How to recognise it

In the harness:

- a tool that returns one page, one section or the hits of a search in one
  document;
- no contents of that document in the prompt or in a skill.

In how the agent runs:

- many lookups in one run, for parts that are near each other;
- lookups by search terms, then by page, for one request;
- runs with no lookup, where the request is about the subject of the
  document.

## How to confirm it

- Find the document's size and how stable it is: how often it changes.
- In the sampled traces, check which parts the agent asked for, and how
  many lookups one request took.
- **Not this smell:** a search tool over many records or many documents,
  for example a knowledge base. That tool finds data, and a contents file
  cannot replace it.

## What it blocks

A prompt rule on which page or section to choose. The rule cannot name each
case, and the agent reads it before it sees the document.

## Remedies

- [Document into a skill](references/improving_agents/techniques/document-into-a-skill.md), first,
  when the document is stable and fits in a skill: a contents body with
  key terms, one reference file for each section, and the lookup tool
  dropped on the same arm. When the document cannot move, the same
  technique gives a smaller change: a keyword contents skill in front of
  the tool.
- [Answers not grounded](references/improving_agents/playbooks/answers-not-grounded.md), when the
  answers state facts that the document does not hold.
