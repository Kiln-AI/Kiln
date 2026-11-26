---
title: Tools on a live server
description: The agent's tools write to a real system, or read data that changes, so the right answer to an eval item moves and a measurement cannot be repeated. A read of fixed data (RAG) is fine.
reviewed: 2026-11-19
applies_to:
  - tools
---

# Tools on a live server

## What it is

An eval item has one right answer. A tool on a live or shared system can
make that answer move: two measurements of the same agent then differ for
a reason that is not the agent. This is a property of the design, whether
an eval passes or fails. Each tool is in one of four cases:

| The tool | Verdict |
|---|---|
| Reads fixed data: RAG over a document store, a fixed copy of a database | Fine. Not this smell. |
| Reads the real world: a web search | Usually fine: there is no fixed copy of the web. A smell only for an eval item whose answer depends on a result that can change: "returns the web site X" (the site can go away) is bad; "confirms that the sixth king of England is X" is fine. |
| Reads data that moves: a live or staging system that people change | Usually bad. "How many tickets did we close last week" has no fixed answer: people change the data, and "last week" moves. |
| Writes to a real system: create, change or delete | Always bad, for evals and for tuner runs. One run changes what the next run reads, and a write can do real harm. |

## How to recognise it

In the harness:

- a tool that creates, changes or deletes records on a production or
  shared host;
- a tool that reads a production or shared host that people change;
- an eval item whose expected answer moves with the data that a tool
  reads: a count of "last week", one exact web result.

In how the agent runs:

- writes in a trace of an eval run, on a live or shared host;
- a result that shows an earlier run's write, for example a record that an
  earlier eval item created;
- different results for the same input in two stored runs.

A write tool alone is not a sign. It needs evidence that the system is
real: a production host name, or a result that shows an earlier write.

## How to confirm it

- Read the tool definitions and the code of each code tool: the system
  that they reach, and any write.
- Compare the results of one input in two stored runs, where they exist.
- **Not this smell:** a read of fixed data; a web search with eval items on
  stable facts; a test system that is reset before each run.

## What it blocks

A decision on a small difference between two candidates, measured at different
times on data that can have changed. A write also blocks a safe run.

## Remedies

No experiment can fix the drift.

- [Dealing with a wrong eval](references/improving_agents/playbooks/dealing-with-a-wrong-eval.md),
  first: report the issue in `open_questions` and in the report. Name the
  tools, the host, the case from the table and the evidence.
  - **For a read of data that changes, check first:** read the eval
    expectations. One that stays true when the data changes is fine ("the
    sixth king of England is X"). Report only the items whose answer moves
    with the data ("42 tickets closed last week", "returns the web site
    X"), and ask the user to make them general.
  - **Otherwise, ask the user for the fix:** run the agent against an
    OpenEnv world, so that the data is reproducible and isolated. The
    alternative: the user confirms that the system is static (a read-only
    test system, the same data on each run). Then it is not this smell.
- [Dealing with a noisy
  eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md),
  when scores move between repeats with no change to the agent: repeat
  before you trust a small difference, until the user fixes it.
- [Guard tool calls at the boundary](references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md),
  when the agent can write to a real system: a wrapper that refuses a write
  that the task does not allow. It limits the harm, not the drift.
