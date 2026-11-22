---
title: Rewrite an inherited skill
description: A new version of a skill that the baseline attaches - split, merged, restructured or scrubbed - attached in place of the old one on a new run config.
reviewed: 2026-11-13
status: active
levers:
  - skill
applies_to: all
cost: medium
---

# Rewrite an inherited skill

## When to use

- The failure comes from a skill that the baseline attaches. The skill is
  wrong, stale, one long file with many topics, contradicts the task, or
  holds data shaped like test cases.
- Earlier arms added prompt rules around the skill, and the failure stayed.
- The skill describes tools, routes or fields that the agent does not have
  any more.
- The agent opens the skill and then guesses a path or reads the wrong file.

Everything that the baseline attaches is part of what the tuner can change.
An inherited skill is not a fixed input.

## When not to use

- **The model does not open skills at all** under this run config. Probe
  it first. A new version of a skill that the agent never reads changes
  nothing: [skill into the prompt](references/improving_agents/techniques/skill-into-the-prompt.md).
- **The skill may not help at all.** Measure the agent without it first:
  [prune one group at a time](references/improving_agents/techniques/prune-one-group-at-a-time.md).
- **Do not add prompt rules around a skill that you can change.** A rule
  that says "ignore part X of the skill" leaves two texts that disagree.

## Alternatives

- [Skill into the prompt](references/improving_agents/techniques/skill-into-the-prompt.md), when the skill is a
  few words, or a probe shows that the model does not open skills.
- [Prune one group at a time](references/improving_agents/techniques/prune-one-group-at-a-time.md), when it is
  not known that the skill helps.

## How

The change is a new version of the [skill](references/levers/skill.md), attached
in place of the old one on a new run config.

1. **Choose the rewrite** that the failure names:
   - **split** a long file into one reference file for each topic;
   - **merge** skills that overlap, so one topic has one place;
   - **restructure** it into progressive disclosure: the description and
     the body map give each reference file's path and key terms
     (the `kiln-harness-tuner-experiment-build` skill,
     `references/skill-authoring.md`, section 3);
   - **correct** what is wrong or stale;
   - **scrub** data shaped like test cases: examples with real-looking ids,
     inputs with their expected answers.
2. **Build the new version.** The steps are "Rewriting an inherited skill"
   in the `kiln-harness-tuner-experiment-build` skill,
   `references/skill-authoring.md`, section 4.
3. **Change each mention of the old name** in the prompt and in other
   skills.
4. **Never write a value from a train item** into the new version. Code
   compares the new version with the old one, and searches it for train
   content.

## Check that it took effect

Read the diff of the new version against the old one: only the parts that
the hypothesis names changed. Smoke on two or three train items that need
the skill, and find the read of the new version in each trace.

## Budget

Medium cost: a bundle to write, and a measurement on its target evals.
When it fixes its target, the val gate measures every eval before a
promotion, the evals that the skill touches too. On a small budget, take
it when the traces tie the failure to the skill's text.

## If it does not move the evals

It depends. Keep it when the rewrite removes content that is wrong, stale,
contradicts the task or looks like test cases, because such content can
mislead the agent on inputs that the evals do not cover. Otherwise, it must
move an eval.

## Priors

None yet.

## Confidence

Medium. It follows from the lever `skill`: an inherited skill is part of
what the tuner can change, so a rule added around it leaves two texts that
can disagree. No measured case is recorded here yet.
