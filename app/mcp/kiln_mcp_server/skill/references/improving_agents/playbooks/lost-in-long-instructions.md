---
title: Lost in long instructions
description: The agent misses a part of a long prompt or of a one-file skill. Progressive disclosure when the model reads skills, a prompt structure when it does not. A quick check first.
reviewed: 2026-11-13
kind: failure
applies_to: all
---

# Lost in long instructions

## Situation

The instructions hold what the item needs, and the agent does not act on
it. The prompt, or an attached skill that is one long file, is long and
holds many topics. Signs in the traces and the outputs:

- the output misses a part that the instructions state: a property that
  must be present, a rule in the middle of the text;
- different items miss different parts;
- the agent follows a rule from the wrong topic, or two rules that
  disagree;
- the task has no tools, and the eval is scored by a judge on long free
  text (a rubric, a summary, an extraction).

Two smells of the design describe the long text itself:
[very long prompt](references/improving_agents/smells/very-long-prompt.md) and
[one-file skill with many topics](references/improving_agents/smells/one-file-skill-with-many-topics.md).
Their documents say how to recognise each one.

This is not a missing requirement: the text asks for the part. When the
text does not ask for it, see
[a requirement is missing from the prompt](references/improving_agents/playbooks/requirement-missing-from-the-prompt.md).

First, run a quick check of whether this model opens a skill, or calls a tool,
under this run config and its output mode. The answer decides between the
first two steps.

## What to try, in order

1. [Long prompt into a
   skill](references/improving_agents/techniques/long-prompt-into-a-skill.md),
   when the quick check says that the model reads skills, and each run needs
   only some of the topics. A short prompt, a router body with one line per
   file, one reference file per topic, and a path index in the description
   with the key terms of each file. A second candidate can trim the prompt
   to the router.
2. [Structure a long
   prompt](references/improving_agents/techniques/structure-a-long-prompt.md),
   when the quick check says no, or the task has no tools, or most runs need
   most of the content. Topics under headings, the parts that must be
   present marked, and a last step that checks each required property before
   the answer.
3. [Rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md),
   when the long text is a skill that the baseline attaches: split it into
   reference files, restructure it, or remove what contradicts the task,
   as a new version of the skill.
4. [Prune one group at a
   time](references/improving_agents/techniques/prune-one-group-at-a-time.md),
   when the text is long because of rules that may not help: remove one
   group on each candidate and measure it.

When structure is not enough and the task has no tools, a step outside the
model can take over a check, for example a second pass over the draft. No
technique document covers it yet.

## What not to do yet

- Do not rewrite the long text in place and call it a fix. A shorter
  version of one long text has the same problem.
- Do not assume that the model will open a skill or call a tool. A quick
  check settles it for a small cost.
- Do not change the output mode on the same candidate. A change of the output
  mode is a lever of its own, and it can break other items.
- Do not let a router narrate an order of reads ("load X first"). It
  changes the order of the calls, and that can change items that the candidate
  was not aimed at.
- Do not measure a skill bundle on every eval before it has fixed its
  target. Measure its target, and add an eval only when you have a stated
  reason to expect the bundle to break it. When it fixes its target, the
  confirmation on val measures every eval before a promotion: [spending the
  budget](references/improving_agents/playbooks/spending-the-budget.md).

## Budget

On a small budget, step 2 comes first when the content must stay in the
prompt: it has a low cost. Step 1 and step 3 have a medium cost.
