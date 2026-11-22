---
title: Structure a long prompt
description: Give a long prompt a structure - topics under headings, the must-include parts marked, and a last step that checks each required property before the answer.
reviewed: 2026-11-13
status: active
levers:
  - prompt
applies_to: all
cost: low
---

# Structure a long prompt

## When to use

- The prompt is long: a rubric, a set of rules for a summary or an
  extraction, a card of properties that each output must have.
- The outputs miss a part of the prompt: a property that must be present,
  a rule in the middle of the text. Different items miss different parts.
- The content cannot leave the prompt: the task has no tools, or a quick
  check shows that this model does not read a skill under this run config.

## When not to use

- **The model reads skills, and each run needs only a part of the
  content.** Progressive disclosure is the larger change:
  [long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md).
- **The prompt does not ask for the missing part at all**:
  [add the missing requirement](references/improving_agents/techniques/add-the-missing-requirement.md).
- **Do not assume that a tool or a skill will be used.** A quick check
  settles it at a low cost. Plan this technique or the skill after the
  check.
- **Do not change the output mode on the same candidate.** A change of the
  output mode is a change of its own, and it is not free: it can break the
  output on other items.

## Alternatives

- [Long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md), when a quick check
  shows that the model reads a skill and each run needs a part of the
  content.
- [Prune one group at a time](references/improving_agents/techniques/prune-one-group-at-a-time.md), when the
  prompt is long because it holds parts that may not help.

## How

The change is one edit of the [prompt](references/levers/prompt.md).

1. **Check quickly first**, when the task could use a skill: does this model
   read a skill, or call a tool, under this run config's output mode?
2. **Mark the must-include parts before you cut anything.** List what each
   output must contain. Put that list where the model reads it last,
   beside the output instruction.
3. **Group the rest by topic, under short headings.** One topic in one
   place. Remove the repeats.
4. **Add a last step**: before it answers, the model checks each required
   property of the answer, one by one.
5. **Keep the meaning.** Each rule of the old prompt is in the new one, or
   its removal is stated in the hypothesis.

No lever covers a pipeline step outside the model (a checker on the
draft, a second pass) today.

## Check that it took effect

Run the candidate on two or three train items whose outputs missed a part.
Count the required parts that are present in each output. When the count
does not rise, the structure did not reach the cause.

## Budget

Low cost: one prompt edit, and a quick check that costs little. A good first
step for a long prompt on a task with no tools. Measure it on its target
evals. When it fixes its target, the confirmation on val measures every eval
before a candidate becomes the baseline, the evals that the prompt covers
too. That matters here, because a new order changes what the model reads
first.

## If it does not move the evals

It depends. Keep it when the new prompt is shorter and no eval falls,
because a shorter prompt costs less on every call. When it is the same
length and no eval moves, it adds nothing.

## Priors

None yet.

## Confidence

Low to medium. Model vendors' prompt guides advise structure, headings and
a clear place for the output rules. The reason is plain: a rule under a
heading, and a last check of each property, are easier for the model to
find than a rule in the middle of long text. No measured case is
recorded here yet.
