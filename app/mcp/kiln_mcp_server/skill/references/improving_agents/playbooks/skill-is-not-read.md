---
title: The skill is not read
description: The agent never loads a skill file, guesses a path, or loads the skill and does not follow it. A rewrite of the skill, then a prompt rule.
reviewed: 2026-11-13
kind: failure
applies_to: all
---

# The skill is not read

## Situation

A skill holds what the failing items need, and the agent does not use it.
Look at the tool calls that open a skill or read one of its files:

- **not opened**: no call opens the skill in the failing items;
- **opened, file not found**: the agent opens the skill and does not load
  the reference file it needs, or it reads a path that does not exist, or
  a file near the right one;
- **read, not followed**: the agent loads the right file, and its answer
  does not do what the file says.

Each case has its own fix, so name the case first. A quick check settles at a
low cost whether this model opens skills at all under this run config.

## What to try, in order

1. [Rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md),
   when the agent opens the skill and misses the file, or guesses a path.
   A new version of the skill, attached in place of the old one.
2. [One general rule per edit](references/improving_agents/techniques/one-general-rule-per-edit.md),
   when the agent does not open the skill: one prompt rule that says which
   requests need the skill.
3. [Skill into the prompt](references/improving_agents/techniques/skill-into-the-prompt.md), when a
   quick check shows that the model does not open skills under this run config,
   or the skill is small, or most runs need it. The content, or a compact
   index of it, is then always in the context.
4. [Policy as step-by-step procedures](references/improving_agents/techniques/policy-as-step-by-step-procedures.md),
   when the agent reads the right file and does not follow it, and the
   file is prose. Numbered steps with yes-or-no conditions are easier to
   follow. When the skill is an inherited one, the change is a new
   version:
   [rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md).

## What not to do yet

- Do not add content to the `SKILL.md` body to fix a read failure. The
  body is a map of the reference files. Full paths and key terms in the
  map are part of the fix. More content in the body is not: it gives the
  model more to read before it picks a file.
- Do not assume that the agent reads a skill because it is attached. Count
  the reads in a few traces, or run a quick check.
- When the agent loads the skill and does not follow it, do not add more
  text to the skill. More text gives the model more to miss. A shorter,
  more procedural text, or the content in the prompt, is the next
  candidate.
  When the model is a lever, a model that follows long guidance better
  is another option.

## Budget

The order does not change with the budget. Steps 2 and 3 have a low cost.
Step 1 has a medium cost: a new version of the skill.

## Priors

- **A coding agent with the documentation of a web framework.** A skill
  held the documentation. In 56% of the eval cases the agent never invoked
  the skill, and the pass rate was the same as with no documentation
  (53%). An explicit instruction to use the skill raised the pass rate to
  79%. A compact index of the documentation, always in the context, in
  the agent's instruction file, reached 100%. One sample, not a rule.
  Source: public, the Vercel post "AGENTS.md outperforms skills in our
  agent evals". 2026-01-27.
- **Several models as the same agent, on a benchmark of tasks with
  skills.** A 32B open model loaded at least one skill in 0.251 of its
  runs, against 0.957 for a frontier model. A larger open model loaded
  skills in 0.961 of its runs, and was judged to follow the loaded skill
  in only 0.350 of them. One sample, not a rule.
  Source: public, the paper "Harness Updating Is Not Harness Benefit:
  Disentangling Evolution Capabilities in Self-Evolving LLM Agents".
  2026-05-28.
