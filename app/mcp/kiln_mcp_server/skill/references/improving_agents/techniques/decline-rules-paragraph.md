---
title: Decline rules paragraph
description: One prompt paragraph that states the agent's scope as rules - what it does, what it declines, how it declines, and what is not a reason to decline.
reviewed: 2026-11-13
status: active
levers:
  - prompt
applies_to: all
cost: low
---

# Decline rules paragraph

## When to use

- The agent answers requests that are outside its task (off-topic
  answers), or it refuses requests that are valid (over-refusal).
- The task has a scope that a person can state as a rule: the kind of
  requests it serves, and the kind it does not.
- The prompt states no scope, or states it as scattered lines.

## When not to use

- **A list of topics to decline.** A list teaches the model which topics
  to refuse. It does not teach the rule behind them, so it misses a topic
  that is not on the list. It also puts the listed topics in front of the
  model on every call, which can make it refuse a valid request that
  mentions one of them. State the rule, not the topics.
- **The answers are in scope, and they add detail that no source holds.**
  That is a grounding problem:
  [answer only from the source](references/improving_agents/techniques/answer-only-from-the-source.md).
- **The refusals come from a missing source.** The agent declines because
  it does not know the answer:
  [attach the knowledge source](references/improving_agents/techniques/attach-the-knowledge-source.md).

## Alternatives

- [Answer only from the source](references/improving_agents/techniques/answer-only-from-the-source.md), when the
  agent stays in scope and goes past its source.

## How

The change is one edit of the [prompt](references/levers/prompt.md).

1. **Read the task instruction** for the scope. Do not take the scope from
   the train items.
2. **Write one paragraph** with four parts:
   - what the agent does, as a category of request;
   - what it declines, as a category;
   - how it declines: the words or the form that the task wants, and what
     it offers in place of an answer;
   - the cases that look out of scope and are not. This part prevents
     over-refusal.
3. **Replace scattered rules** about scope with the paragraph, on the same
   edit.
4. **Read the residual failures** after the measurement, on both sides.
   When the agent now refuses valid requests, the next candidate rebalances: it
   adds to the fourth part, or makes the second part narrower. Change one
   side for each candidate.

## Check that it took effect

Smoke on two train items that are out of scope and two that are valid but
unusual. Count the declines on each side. Declines on the valid items show
over-refusal before the measurement.

## Budget

Low cost: one prompt edit. A good first step on any budget, when the
failures are about scope. Measure it on its target evals. When it fixes its
target, the confirmation on val measures every eval before a promotion, the
evals that check a valid answer too: a stronger guard can break them.

## If it does not move the evals

It must move an eval. The paragraph exists to fix measured scope failures.

## Priors

None yet.

## Confidence

Medium. A scope stated as a rule is common field practice: a rule covers
the requests that a list leaves out. No measured case is recorded here
yet. The balance between the two sides is specific to each task, so the
residuals decide the second candidate.
