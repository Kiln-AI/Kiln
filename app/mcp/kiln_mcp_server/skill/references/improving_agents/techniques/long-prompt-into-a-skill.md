---
title: Long prompt into a skill
description: Move the topics of a long prompt into a skill by progressive disclosure - a short prompt, a router body, one reference file per topic, a path index.
reviewed: 2026-11-13
status: active
levers:
  - skill
  - prompt
applies_to: all
cost: medium
---

# Long prompt into a skill

## When to use

- The prompt is long and holds many topics, and each run needs one or a
  few of them. Example: an agent that can do 25 things, with the rules of
  all 25 in its prompt.
- A probe shows that the model reliably opens skills under this run
  config. Small models often do not. The measured cases are in the
  playbook [the skill is not read](references/improving_agents/playbooks/skill-is-not-read.md).
- The traces show the agent miss a part of the long prompt, and the part
  it misses changes from item to item.
- The cost per item is high because of the prompt, and the measured cost
  shows no saving from a prompt cache.

The move is worth an experiment when the prompt holds many topics, each
run needs few of them, and a probe shows that the model opens skills. When
one of these conditions is not true, an alternative below fits better.

## When not to use

- **The model does not read skills** under this run config. Probe it first.
  When the probe says no:
  [structure a long prompt](references/improving_agents/techniques/structure-a-long-prompt.md).
- **Most runs need most of the content.** Each run then pays for the
  calls to read the files, and gets nothing that the prompt did not give.
- **A capable model, with a prompt that the cache serves.** A long prompt
  that is the same on every run can be cheaper and faster than many reads
  of a skill: see [skill into the prompt](references/improving_agents/techniques/skill-into-the-prompt.md).
- **The prompt is long because of rules that do not help.** Remove them
  first: [prune one group at a time](references/improving_agents/techniques/prune-one-group-at-a-time.md).
- **Do not rewrite the long text in place** and call it a skill. A skill
  that is one long file has the same problem as the prompt.

## Alternatives

- [Skill into the prompt](references/improving_agents/techniques/skill-into-the-prompt.md), when most runs need
  the content, the model is capable, and the measured cost shows that the
  prompt cache applies.
- [Structure a long prompt](references/improving_agents/techniques/structure-a-long-prompt.md), when a probe shows
  that the model does not read skills.
- [Policy as step-by-step procedures](references/improving_agents/techniques/policy-as-step-by-step-procedures.md),
  when the long text is one policy that every run follows.

## How

The change is a new [skill](references/levers/skill.md) bundle and a shorter
[prompt](references/levers/prompt.md), on one new run config.

1. **Probe**, when no earlier probe answered it: does this model open a
   skill under this run config?
2. **Build the bundle from the prompt text**, never from the train items.
   The steps are in the `kiln-harness-tuner-experiment-build` skill,
   `references/skill-authoring.md`: section 2, "When the model is lost in a
   long prompt or one big skill", for the topic files and the body map, and
   section 3 for the description.
3. **Trim the prompt on the same arm.** It keeps what every run needs (the
   role, the output contract) and one line that names the skill. The moved
   text leaves the prompt. Two copies can disagree.

## Check that it took effect

Smoke on two or three train items that need different topics. In each
trace, find the read of the right reference file before the answer. When
the skill is never opened, the change did not reach the agent.

The bundle changes the order of the agent's calls, and that can break another
criterion. Measure the bundle on its target evals, and add an eval only when
you have a stated reason to expect the bundle to break it. When it fixes its
target, the val gate measures every eval before a promotion.

## Budget

Medium cost: a bundle to write, and a measurement on its target evals. On
a small budget, take it when a smell of a long prompt or a failure pattern
of lost instructions names it, and after a probe says that the model reads
skills.

## If it does not move the evals

It depends. Keep it when the cost or the latency per item falls and no eval
falls, because a shorter prompt and focused files are a better design to
extend. When the cost does not fall and no eval moves, the extra calls are
not worth it.

## Priors

None yet.

## Confidence

Medium, as of 2026-11. It is the owners' view of the field, and public
benchmarks agree in part: focused skills help on average, and large or
comprehensive skills do not. It depends on the model, on how often a run
needs each topic, and on whether the agent opens the skill. No measured
case is recorded here yet.
