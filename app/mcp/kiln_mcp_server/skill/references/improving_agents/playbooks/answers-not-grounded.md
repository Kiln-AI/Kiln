---
title: Answers are not grounded
description: The answers need knowledge that is not in the agent's context - attach the source, then add scope discipline. A source behind a lookup tool can move into a skill.
reviewed: 2026-11-12
kind: failure
applies_to: all
---

# Answers are not grounded

## Situation

The answer states facts that are wrong, invented or out of date, and the
right facts are not in the agent's context. Look at the trace before the
final answer:

- no tool call or skill read brought the facts in, because the agent has
  no source for them;
- or the agent has a source, and it did not reach the part that holds the
  answer: it searched with the wrong terms, read the wrong page or
  section, or did not look;
- or the source was read, and the answer goes past what the source says.

The knowledge exists somewhere you can reach: a search tool or a
RAG tool of the project, a document, a skill. When the source is a long
document that the agent reaches only by page, by search or by section, the
smell [document behind a lookup tool](references/improving_agents/smells/document-behind-a-lookup-tool.md)
says how to recognise it.

## What to try, in order

1. [Attach the knowledge source](references/improving_agents/techniques/attach-the-knowledge-source.md),
   when the agent has no source for the facts. Attach an existing search
   or RAG tool, or write the knowledge into a skill.
2. [Answer only from the source](references/improving_agents/techniques/answer-only-from-the-source.md),
   when the source is in the context and the answers go past it. A short
   rule of scope discipline: answer from the source, and say so when the
   source does not cover the question.
3. [Document into a skill](references/improving_agents/techniques/document-into-a-skill.md), when a
   long reference document sits behind a lookup tool (by page, by search
   or by section), and the agent picks the wrong part or never looks. A
   contents file that names what each section holds, one reference file
   per section, and the lookup tool dropped on the same candidate.

## What not to do yet

- No model swap. A stronger model does not know facts that are not in its
  context, and it can state wrong facts with more confidence.
- No closed list of what the agent may answer. A list breaks on each
  question that it does not name, and the model matches it by words, not
  by meaning.
- No prompt rules on which page or section to choose. The agent reads the
  rule before it sees the contents, and the rule cannot name every case.

## Budget

The order does not change with the budget. Step 1 and step 3 have a
medium cost. On a small budget, step 2 alone is worth a candidate when the
source is already attached.
