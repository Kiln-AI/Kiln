---
title: Dealing with an eval near zero
description: The baseline passes almost no item of an eval. Read the raw outputs first - text fixes a missing requirement or a wrong format. Try a smarter model only on evidence that the model cannot do the task.
reviewed: 2026-11-13
kind: eval
applies_to: all
---

# Dealing with an eval near zero

## Situation

The baseline passes almost no item of an eval.

A score near zero does not show that the model is too weak. Often one
cause makes every item fail, and one change removes it. For example, the
eval checks for a requirement that the prompt never states. The baseline
then scores near zero, and one prompt line that states the requirement
can take the score near the top.

The raw outputs show the cause. The usual causes are:

- **A missing requirement.** The eval checks for something that the
  prompt and the task's instructions never ask for. The output does what
  it was asked to do, and not the thing that the eval checks.
- **A format or protocol failure.** The content is right, and the output
  has the wrong shape or misses a step: a missing block, broken JSON, a
  field in the wrong form, a tool step that the agent does not do.
- **The eval is wrong.** The judge fails right answers, or the expected
  outputs cannot be met.
- **A capability floor.** The model does not have the ability that the
  task needs. Its answers are wrong in substance, not only in form: the
  reasoning goes wrong or stops short, and the errors are different from
  item to item. A clear statement of each requirement does not correct
  them.

Only the last cause is about the model. Text or a change to the eval
fixes the other three.

## What to try, in order

1. Read the raw outputs of several failing items, with the expected
   output and the judge's reasoning, before any arm. Name the cause of
   each.
2. A requirement that the prompt never states:
   [a requirement is missing from the prompt](references/improving_agents/playbooks/requirement-missing-from-the-prompt.md).
3. A format or protocol failure, broken JSON included:
   [the output contract is not met](references/improving_agents/playbooks/output-contract-not-met.md). A
   malformed tool call:
   [malformed tool calls](references/improving_agents/playbooks/malformed-tool-calls.md).
4. A judge that fails right answers, or expected outputs that cannot be
   met: [dealing with a wrong eval](references/improving_agents/playbooks/dealing-with-a-wrong-eval.md).
5. A capability floor, when the model is a lever (`allowed_models` lists
   another model, and the guidance does not forbid a model change). Look
   for evidence that this model cannot do the task. One sign is that the
   reads show answers wrong in substance on most failing items. Another
   sign is that repeated arms on sound fixes did not move the score: each
   arm stated the requirement or fixed the format, and the outputs stayed
   wrong in substance. On such evidence, consider a smarter model of the
   class before more harness tuning. Lock it, then tune the harness:
   [model swap inside a class](references/improving_agents/techniques/model-swap-inside-a-class.md).
   When an arm moves the score on the current model, keep tuning on it.
6. A capability floor where some items fail because the model does not
   think the problem through: one rung more thinking, on those items
   first:
   [thinking level ladder](references/improving_agents/techniques/thinking-level-ladder.md).
7. When the model is not a lever and no step above applies, say so in
   `open_questions`: the eval cannot steer the run on this model.

## What not to do yet

- Do not change the model on the score alone. A smarter model does not
  fix a missing requirement or a wrong format, and a model change needs a
  measurement of every eval.
- When the reads and the arms show a capability floor, do not keep
  planning new wordings of the same text. A new wording does not give
  the model an ability that it does not have.
- No settings scan to find a signal. A scan changes how the model reads
  the harness, and it does not lift a floor of capability on most items.
  Step 6 is one rung on the items that need more reasoning, not a scan.
- Do not tune on a very large model and expect the result to hold when
  the run goes back to a small one.

## Budget

Steps 1 to 4 cost reads and cheap arms, so they come first on every
budget. A model change at step 5 needs a measurement of every eval, so it
fits a larger budget, or a run where this eval is the main goal.
