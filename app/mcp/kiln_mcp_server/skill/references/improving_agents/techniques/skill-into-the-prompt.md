---
title: Skill into the prompt
description: Move the content of a skill into the prompt and drop the skill - for a small skill, content that most runs need, or a skill the agent does not open.
reviewed: 2026-11-13
status: active
levers:
  - prompt
  - skill
applies_to: all
cost: low
---

# Skill into the prompt

## When to use

- **A skill of a few words, with no other file.** Its description is in
  every call, and opening it costs one more call. Its content costs less in
  the prompt.
- **Most runs need the content.** Each of those runs reads the skill, so
  the skill saves no context and adds calls.
- **The agent does not open the skill** when it needs it, and the content
  is short enough for the prompt. Content in the prompt needs no decision
  to read it.
- **A capable model, and a prompt cache that applies.** A long prompt that
  is the same on every run can be cheaper and faster than many reads of a
  skill tree. A read of a skill file comes after the run's own input, so the
  cache does not share it between runs.

## When not to use

- **Many topics, and each run needs few of them.** The prompt then grows
  with content that most runs do not use:
  [long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md).
- **A small model that loses parts of a long prompt**, when a probe shows
  that it opens skills. It then does better with focused context.
- **The measured cost shows no cache saving.** Whether the cache applies
  depends on the provider and on how Kiln makes the call. Read the cost
  per item in the traces before you plan the cache as the reason.

## Alternatives

- [Long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md), the reverse
  move: when a probe shows that the model opens skills, and each run needs
  a part of the content or the prompt cache does not apply.
- [Rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md), when the
  agent opens the skill and then reads the wrong file, and the content is
  too large for the prompt: a new version, restructured.

## How

The change is an edit of the [prompt](references/levers/prompt.md), and the
[skill](references/levers/skill.md) dropped on the same new run config.

1. **Read the skill**: its `SKILL.md` and each reference file.
2. **Put the content in the prompt** in the place where it belongs. When
   it is long, keep its headings. Remove what the prompt already says.
3. **Drop the skill** from `tools_config.tools` on the new run config.
   Other run configs that attach the skill keep it: the change is on the
   new run config only.
4. **Remove each mention of the skill** in the prompt and in other skills:
   a line that tells the agent to open it now points at nothing.
5. Keep the static content at the top of the prompt, and no value that
   changes per run inside it. A per-run value breaks the cache prefix.

## Check that it took effect

Smoke on two or three train items that need the content. In each trace,
find no call to the skill, and the rule of the content followed in the
answer. Note the cost per item and the cached tokens when the trace has
them.

## Budget

Low cost: one prompt edit and one fewer skill. A good step when a smell
names a skill too small to earn its place. On a small budget, measure it on
the evals that the skill's content covers.

## If it does not move the evals

It depends. Keep it when the cost or the latency per item falls (fewer
calls) and no eval falls, because the harness is simpler. When the cost
rises and no eval moves, the skill was the better design.

## Priors

None yet.

## Confidence

Low to medium. It is an idea of the project's owners, and it agrees with
public reports that content always in context can beat a skill that the
agent must decide to open. The cache saving is real on some providers, and
it depends on how the call is made. No measured case is recorded here yet.
