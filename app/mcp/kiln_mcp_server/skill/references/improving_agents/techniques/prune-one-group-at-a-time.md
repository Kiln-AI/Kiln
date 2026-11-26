---
title: Prune one group at a time
description: Find what helps in a large harness - remove one group (a prompt section, a skill, a set of tools) on each candidate and measure it, or add groups one at a time to a bare base.
reviewed: 2026-11-13
status: active
levers:
  - prompt
  - skill
  - tool_config
applies_to: all
cost: low
---

# Prune one group at a time

## When to use

- The harness has grown: many skills, long sections of the prompt, many
  tools. It is not known which of them help.
- One part loads in many runs and is large: a skill read on most items, a
  long section of the prompt.
- The cost per item is high, and the evals do not show that each part
  earns its cost.
- A smell names a part that may not earn its place.

## When not to use

- **The harness is small.** There is little to remove, and each candidate costs
  a measurement.
- **The budget cannot pay one measurement for each group.** Remove only
  the group that a smell or a trace names.
- **A group is there for a guard**: a safety rule, a rule that the product
  enforces. Do not remove it without a measurement on the eval that guards
  it.
- **The group helps, and it is too large.** Cut it, do not remove it: see
  [rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md).

## Alternatives

- [Rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md), when a
  skill helps and holds content that this task does not need.
- [Long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md), when the prompt
  is long and each part helps on some runs.

## How

The change removes one group: a section of the
[prompt](references/levers/prompt.md), one [skill](references/levers/skill.md), or a set of
tools with one job ([tool_config](references/levers/tool_config.md)).

1. **List the groups.** A group is one thing that can be on or off: one
   section, one skill, the tools of one job.
2. **Choose the direction.**
   - **Leave one out**: each candidate removes one group from the baseline.
   - **Add one in**: from a base with no group of that kind, each candidate adds
     one group. This gives the effect of each group alone. It costs one
     candidate for the bare base.
3. **One group for each candidate.** Two groups on one candidate do not tell
   which one moved the eval.
4. **Measure the candidate on its target evals**: the evals that the group
   is for. When the candidate holds its target, the confirmation on val
   measures every eval before a promotion, the evals that the group could
   change too.
5. **Remove each mention** of a removed skill or tool in the prompt and in
   the other skills.
6. **Then act on the results.** Keep the groups that help. Drop the groups
   that hurt. For a large group that helps, cut the part that this task
   does not use, and measure the cut version against the full one.

## Check that it took effect

Read the new run config against the parent: exactly one group is gone or
added. The reference check finds no name that points at nothing. A smoke
shows no call to a removed tool or skill.

## Budget

Low cost for each candidate, and many candidates for the whole set. On a
small budget, prune only the group that a smell or the traces name. On a
large budget, a full pass over the groups is a good early step: it makes
every later measurement cheaper.

## If it does not move the evals

Keep it. A smaller harness with the same evals costs less on every call and
has less text to keep correct. The condition: no eval falls, including the
guard evals.

## Priors

- **An accounting assistant with hand-written skills, on an internal
  benchmark of simulated businesses.** All skills were removed, and
  then each skill was measured alone on the bare base. Only two skills were
  positive on average, one was neutral, and the others were negative. The
  largest skill was then cut by 64%, from 14k to 5k characters, and the cut
  part went to a narrower skill. On one simulated business, the original
  scored 3.7 points above the base with no skill, and the cut version 3.3
  points. One sample, not a rule.
  Source: public, the Ramp post "Stack Benchmarking". 2026-06-03.

## Confidence

Medium, that a large harness holds parts that do not help: one public case,
and public benchmarks that find large or comprehensive skills help less
than focused ones. Low, for which direction of the two is better: no case
compares them.
