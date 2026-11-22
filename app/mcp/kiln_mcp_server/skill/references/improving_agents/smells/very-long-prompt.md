---
title: Very long prompt
description: The system prompt is longer than 200,000 characters, or it holds many unrelated topics and each request needs a few. Measure the length yourself.
reviewed: 2026-11-13
applies_to: all
---

# Very long prompt

## What it is

The system prompt holds more than each request needs. The model reads all
of it on every call, whether the request needs a part or not. It costs
tokens on every call, and in a long text the model can miss a rule that
the request needs. How much it misses depends on the model and on how the
text is structured. This is a property of the design, whether an eval
passes or fails.

The smell has two forms. The sure form is a prompt longer than the
reference length, 200,000 characters (about 50,000 tokens). A measurement
finds it. A reader finds the other form at any length: a
prompt that holds many unrelated topics, of which each request needs one
or a few.

## How to recognise it

In the harness:

- measure it yourself: the prompt that the run config sends has more than
  200,000 characters;
- at any length: the prompt holds many unrelated topics, for example
  the rules of each thing that the agent can do, and each request needs
  only one or a few of them.

In how the agent runs:

- the prompt is most of the input of each call, whatever the request;
- the requests are short, and each of them is about one topic of the
  prompt.

## How to confirm it

- Read the prompt. Count its topics, and estimate how many of them one
  request needs. Under the reference length, report it only when the topics are
  unrelated and most requests need few of them. Name the topics in the
  evidence.
- The reference is a default of Kiln Harness Tuner, not a measured
  optimum: no published limit for a system prompt is known. Say so when you
  state how sure you are.
- **Not this smell:** a prompt that is one topic, which every request
  needs in full, for example a rubric or a policy that applies to each
  item. That prompt can still be hard to follow: its structure is the
  question, not its length.

## What it blocks

A new rule added to the prompt. The model can miss one more line in a long
text, so a result that does not move the eval says little about the rule.

## Remedies

- [Long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md),
  when the model reads skills and each request needs only some of the
  topics.
- [Structure a long prompt](references/improving_agents/techniques/structure-a-long-prompt.md),
  when the task has no tools, the model does not read skills, or most
  requests need most of the content.
- [Prune one group at a time](references/improving_agents/techniques/prune-one-group-at-a-time.md),
  when the prompt holds sections that may not help.
- [Lost in long instructions](references/improving_agents/playbooks/lost-in-long-instructions.md),
  when the traces show the agent miss parts of the prompt.
