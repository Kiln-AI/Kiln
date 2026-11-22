---
title: Decision model for a classifier
description: Run a classifier-shaped task on a decision model - a fast, cheap model that returns a prediction from a fixed set, not text - when cost or latency matters.
reviewed: 2026-11-13
status: active
levers:
  - model
applies_to:
  - single_turn
  - structured_output
  - classifier
  - no_tools
cost: medium
---

# Decision model for a classifier

## When to use

- The task has a classifier shape: one request, one answer, and an output
  schema whose fields each take a small closed set of values (an enum, a
  yes or no, a small integer scale, a number from 0 to 1).
- The user's goal is cost or latency, or the task runs at a high volume,
  and the user does not forbid a model change.
- A decision model is among the models that the user allows.

A decision model reads its input like a language model. It does not write
text: it returns a prediction for each field in one pass. So it is much
faster and cheaper than a language model on the same input.

## When not to use

- **The task returns free text**, or a field of free text. A decision
  model cannot write it.
- **The agent needs tools**, or more than one turn. A decision model makes
  no tool call.
- **The goal is quality, and the task is near its quality bar.** A
  decision model does not reason before it answers, so it can be less
  accurate than a language model on the same task. A small loss can be
  acceptable for a large saving. That is a decision for the user's goal,
  not a default.
- **The classes need reasoning over the input**: arithmetic, dates,
  indirection, long text with irrelevant parts. A decision model reads in
  one pass and does not reason step by step. Code that computes those
  facts first is an input transform, which no lever covers today.

## Alternatives

- [Model swap inside a class](references/improving_agents/techniques/model-swap-inside-a-class.md), when a
  smaller language model can hold quality and the task needs some
  reasoning.
- [Thinking level ladder](references/improving_agents/techniques/thinking-level-ladder.md), when the same model at
  a lower level is enough for the latency or the cost goal.

## How

The change is the model and the provider on a run config (the lever
[model](references/levers/model.md)). In Kiln, at the date of this document, the
decision model Jev is reachable as a model with its own provider, when the
user allows it and Kiln lists it.

1. **Check the shape.** Read the task's output schema. Each field takes a
   closed set of values. The task has no tools and is single-turn.
2. **Check the list.** The decision model is among the models that the
   user allows. When it is not, it is not a candidate.
3. **Read the instructions as a classifier reads them.** The task's
   instructions reach the decision model with the input. They work best
   when they state what each class means, with its criteria, in plain
   words. When the schema has no class for "other" or "unknown", an input
   that fits no class is forced into one. When the instructions need a
   change for the decision model, that is a second change, measured on its
   own or stated as part of the hypothesis.
4. **Screen it** against the baseline, on the same items, with the
   baseline's passes judged first. Take it on as one experiment only when
   it keeps the passes that the user's goal needs.
5. **Measure it on every eval.** This is an exception to the usual few
   target evals: a model swap changes every item, so every eval is its
   target.

## Check that it took effect

Check yourself that the swap reached the call: a run that another model or
provider served means that the change was not applied. A run on two or three
train items shows an output that fits the schema, and the latency and the
cost of the runs against the parent's.

## Budget

Medium cost: no build, but a screening and a measurement on every
eval. On a small budget, take it only when the user's goal is cost or
latency. It is not worth a slot when quality is the only goal.

## If it does not move the evals

It depends. When the user's goal is cost or latency, a decision model that
holds every eval is a large gain: keep it. When quality is the goal,
it must move an eval, and that is not what it is for.

## Priors

None yet.

## Confidence

Low to medium. The category is new, and few independent measurements
exist. It follows from how the model works that it is much faster and
cheaper than a language model on the same input, and that it fits only a
closed set of outputs. How much quality it keeps depends on the task, so
the measurement decides.
