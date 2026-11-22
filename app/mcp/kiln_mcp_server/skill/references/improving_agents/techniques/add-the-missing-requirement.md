---
title: Add the missing requirement
description: One prompt rule, in new words, for a requirement that the eval checks and that neither the prompt nor the task instruction asks for.
reviewed: 2026-11-12
status: active
levers:
  - prompt
applies_to: all
cost: low
---

# Add the missing requirement

## When to use

- The eval checks for a property X of the answer, and nothing that the
  model reads asks for X: not the prompt, not the task instruction, not a
  skill.
- The failing traces show answers that are reasonable for the prompt as it
  is written. They leave out X, or do the opposite of X.
- The same omission repeats over many failing items. One cause explains
  them.

A frequent case, and one of the easiest to see: compare what the spec of
the eval asks for with what the prompt asks for, then read a few failing
outputs.

## When not to use

- **The prompt already asks for X, and the model misses it.** Another line
  says the same thing again. Look at where the rule is and how long the
  prompt is: [structure a long prompt](references/improving_agents/techniques/structure-a-long-prompt.md).
- **X is a format rule** (a layout, a closing block, an escaping rule):
  [state the output contract](references/improving_agents/techniques/state-the-output-contract.md).
- **The model does not know the facts that X needs.** A rule cannot add
  knowledge: [attach the knowledge source](references/improving_agents/techniques/attach-the-knowledge-source.md).
- **X holds for a few items only**, each for its own reason. A rule for
  each case often does not transfer to val:
  [one general rule per edit](references/improving_agents/techniques/one-general-rule-per-edit.md).
- **The eval is wrong.** When the expected property contradicts the task
  instruction, or the judge's reasons do not match its scores, the
  measurement is the problem, not the prompt.

## Alternatives

- [State the output contract](references/improving_agents/techniques/state-the-output-contract.md), when the
  content is right and the form is wrong.
- [Attach the knowledge source](references/improving_agents/techniques/attach-the-knowledge-source.md), when the
  model would follow the rule but does not know the facts.
- [Structure a long prompt](references/improving_agents/techniques/structure-a-long-prompt.md), when the prompt
  asks for X in a place that the model does not read well.

## How

The change is one edit of the [prompt](references/levers/prompt.md).

1. **Name the requirement.** Read the spec of the eval and the failing
   outputs. Write the requirement in one sentence, in your own words.
2. **Do not copy the eval.** Never paste text from a judge prompt, a spec or
   an eval description, and never name an eval (the leak rules of
   `references/knowledge/train_val_test.md`). Search each build yourself for
   a run of words copied from those texts. State the rule from the task's
   point of view: what a good answer does, and why.
3. **State it as a general rule**, with its reason. Do not write a value
   from a train item. When an example helps, use invented values.
4. **Put the rule beside the instruction it belongs to.** When the prompt
   states a weaker or a different version, replace that text on the same
   edit.
5. **One requirement for each candidate**, unless two requirements are one rule.
   Then a result tells which rule moved which eval.

## Check that it took effect

Run the new run config on two or three train items that failed for the
missing property. Count the outputs that now have it. When none have it,
the rule did not reach the model, or the cause is not the prompt.

## Budget

A good first step on any budget, when the traces show the omission. It
costs one prompt edit and a measurement on the eval of the requirement,
plus the evals that the new rule could break.

## If it does not move the evals

It must move an eval. The rule exists to fix a measured omission. When the
count of failing items does not fall, the rule did not take effect, or the
cause is another one. Do not keep a rule that adds text and fixes nothing.

## Priors

None yet.

## Confidence

Medium to high, for an omission that the traces show on many items. An
underspecified prompt is one of the most common causes that error analysis
finds, in field practice and in the view of the authors of this
knowledge.
Low, when only a few items fail: a rule written for them often does not
transfer.
