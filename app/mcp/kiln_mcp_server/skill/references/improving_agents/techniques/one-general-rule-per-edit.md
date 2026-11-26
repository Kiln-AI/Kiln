---
title: One general rule per edit
description: A text edit states one general rule, with its reason and its source, and replaces text - not one rule for each failing case.
reviewed: 2026-11-13
status: active
levers:
  - prompt
  - skill
applies_to: all
cost: low
---

# One general rule per edit

## When to use

- A candidate edits the words of the prompt or of a skill, and the failing
  items have more than one cause.
- The failing items each fail for their own reason, and a rule for each
  one is easy to write.
- Earlier text candidates won on train and validation rejected them.
- The prompt or a skill grows with each promoted candidate, and old rules stay
  beside the new ones.

## When not to use

- **The failure is mechanical**: a malformed call, a result that floods
  the context, a wrong tool. Change what the model touches before the
  words that it reads.
- **No rule can be stated without the name or the value of an item.**
  Then the fix is not a text fix. The generality check refuses such a
  rule.

## Alternatives

- [Prune one group at a
  time](references/improving_agents/techniques/prune-one-group-at-a-time.md),
  when the text is already long with rules from earlier candidates.
- [Add the missing requirement](references/improving_agents/techniques/add-the-missing-requirement.md), when one
  requirement explains most failures and the prompt never asks for it.

## How

The change is an edit of the [prompt](references/levers/prompt.md), or a new
version of a [skill](references/levers/skill.md).

1. **Group the failing items by cause.** Choose the cause that explains the
   most items. A group of one or two items is rarely worth a rule: a rule
   for it often does not transfer.
2. **Write one rule** that states the cause and the action. Put its reason
   beside it, in a short clause. A rule with its reason is easier to keep
   correct.
3. **Apply "Text you add"** of your build instructions (in a chat with a
   user: "Build the candidate" of
   `references/client_guidance/chat/running_an_experiment_from_chat.md`):
   the rule replaces text, and it names its source, never a train case. An
   example in the rule uses invented values (the leak rules of
   `references/knowledge/train_val_test.md`).
4. **Look for a contradiction.** Search the prompt and the attached skills
   for text that says the opposite. Two rules that disagree make the model
   choose.
5. **State it once.** Do not add "always", "never" or capitals to a rule
   that the model already reads.

## Check that it took effect

Before the smoke, read the diff: one rule, no value from an item, and text
that did not grow, or grew by the one rule. Then smoke on two train items
of the chosen cause, and one item of another cause that passed before.

## Budget

Low cost. It matters most on a small budget: a candidate that wins on train and
loses at validation is the most expensive candidate there is.

## If it does not move the evals

It depends. Keep it when the rule replaced longer text and no eval fell,
because the harness is shorter and has fewer contradictions. When it only
added text and no eval moved, it adds a cost to every call.

## Priors

None yet.

## Confidence

Medium. It follows Kiln Harness Tuner's build rules and its generality check. It
agrees with public research on instruction files: files that only grow,
rules with no reason, and rules that contradict each other each lower how
well a model follows the file. No measured case of this exact rule is
recorded here.
