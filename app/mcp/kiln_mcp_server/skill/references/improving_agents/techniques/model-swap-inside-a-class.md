---
title: Model swap inside a class
description: Lock one model of the class the task needs, tune the harness on it, then scan the class again for a model that is better, cheaper or faster with that harness.
reviewed: 2026-11-13
status: active
levers:
  - model
applies_to: all
cost: high
---

# Model swap inside a class

## When to use

- `allowed_models` lists a model other than the baseline's, and the
  guidance does not forbid a model change. Otherwise the model is not a
  lever.
- **At the start**, the model shows no aptitude for the task: it passes
  almost nothing across the evals, and the outputs are wrong in
  substance, not only in form. A missing requirement or a wrong format
  can also put a capable model near zero, and text fixes it, so read the
  outputs first. A model of the same class with some aptitude for the
  task gives the tuning a start.
- **After the harness is tuned**, quality has stopped moving, and other
  models of the same class (the same size, price and latency) may do
  better, cost less or run faster with this harness.
- The metric that matters is not the overall pass rate: a kind of error
  that costs more than the others, or the cost or the latency at a fixed
  quality. Another model of the class can be better on that metric.

## When not to use

- **In the middle of the harness tuning.** Every change that the harness
  has gained was measured with the old model. A swap changes what each of
  those changes does. Tune with the model locked, and come back to it.
- **The failure has a cause in the harness**: a smell that blocks other
  work, a tool that floods the context, a missing requirement. A stronger
  model can hide the cause and cost more on every item.
- **Across classes, to compare a large model with a small one.** A harness
  tuned on a very large model can transfer badly to a small one, because
  a small model can need a shorter prompt and more progressive
  disclosure. A change of class is a new start, with its own tuning.
- **A model that the run's model policy does not allow.** The policy is a
  hard limit, and create refuses it.
- **The run's objective is `speed` or `cost`.** The run then opens with a
  screening round of the lower thinking levels, and the planner screens
  the allowed models next. That screening replaces this order (lock, tune, scan
  again).

## Alternatives

- [Thinking level ladder](references/improving_agents/techniques/thinking-level-ladder.md), when the same model
  at another level can reach the goal, which is a smaller change.
- [Faster provider for the same model](references/improving_agents/techniques/faster-provider-for-the-same-model.md),
  when the goal is latency, and the same model is served faster elsewhere.
- [Decision model for a classifier](references/improving_agents/techniques/decision-model-for-a-classifier.md),
  when the task has a classifier shape and the goal is cost or latency.

## How

The change is the model and the provider on a run config (the lever
[model](references/levers/model.md)). The lever gives the two ways: a screening
round of candidates in code, and an arm.

1. **Choose the class** from what the task needs and what the run allows:
   the size, the price and the latency. The candidates are the models of
   that class in the run's list of allowed models. `list_models` gives
   each one's list price, context window, release date and tags, and
   `get_model_details` gives Kiln's notes for agents.
2. **At the start, lock one model** with some aptitude for the task:
   some items pass, and many fail, so that there is room to rise. On a
   large budget, screen several models of the class first and lock the one
   with the best aptitude. On a small budget, lock one and start.
3. **Tune the harness with the model locked.** The prompt, the skills, the
   tools and the settings.
4. **Scan the class again** with the tuned harness: screen the candidates
   in code, on the same items, then commit the best survivor as an arm,
   measured on every eval. This is an exception to the planner's
   lean-target default: a model swap changes every item, so every eval is
   its target. Set a thinking level from the new model's own list, and the
   output mode to the new model's default (the lever gives the step).
5. **After a swap, measure again what the harness gained.** Each promoted
   change was measured with the old model. With the new model, a change
   can help less, help more, or hurt. Check the evals that each change
   targeted. Fix only what got worse, and look for workarounds that the
   new model no longer needs.
6. **Fine-tunes.** A fine-tune that exists is a candidate like any other
   model, when the policy allows it. Read what it was trained for before
   you plan it. The tuner does not start a fine-tune. A fine-tune is a late
   step, after the harness is tuned. It does not replace knowledge in the
   prompt or in a skill.

## Check that it took effect

Code checks that the swap reached the call: a drive that another model or
provider served gives the verdict `lever not applied`. A smoke on two or
three train items shows that the new model calls the tools and returns the
output form that the task needs. The capability flags of
`get_model_details` are Kiln's data, and one drive shows what the model
does on the task. Invalid output just after the swap points first to a
wrong output mode, not to a weaker model: check that the mode is the new
model's default before you record the model as refuted.

## Budget

High cost: each candidate is measured on every eval, and a swap can change
every item. On a small budget, lock a reasonable model and leave out the
scan at the start. A scan after the harness is tuned is worth a slot when
the objective is cost or latency. On a large budget, a scan at the start
and a scan at the end are both reasonable.

## If it does not move the evals

It depends. When the objective is cost or latency, a cheaper or faster
model that holds every eval is a gain: keep it. When the objective is
quality, a swap must move an eval, because it changes every item and the
promoted changes were measured on the old model.

## Priors

- **A small-model feature that edits charts from a request, with a hand-off
  to a larger agent.** The team chose to minimise wrong edits, not to
  maximise the overall pass rate. They adopted a model whose overall pass
  rate was about 1 point lower than the other candidate, because it made
  20% fewer wrong edits at half the cost. One sample, not a rule.
  Source: public, the Hex post "Hill climbing to glory: using evals to
  improve AI error rate by 7x". 2026-10-08.
- **An automated optimiser on eight benchmark tasks, with a fixed set
  of models of similar cost.** The optimiser changed prompts and models.
  In six of the eight tasks, the best variant used another model than the
  baseline, often with a new prompt too. One sample, from a vendor, not a
  rule.
  Source: public, the TensorZero post "We're building an automated AI
  engineer, and it works". 2026-03-23.

## Confidence

Medium, that the model is a large lever inside a class: two public cases.
The cases do not separate the model from the prompt changes made with it.
Medium, for the order (lock, tune, scan again): it follows from how
changes are measured, since each promoted change was measured on the
locked model. Low, for a swap across classes: no case here measures it.
