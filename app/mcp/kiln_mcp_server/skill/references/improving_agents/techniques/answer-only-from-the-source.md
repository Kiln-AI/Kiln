---
title: Answer only from the source
description: A short prompt rule of scope discipline - answer from the attached source, and say so when the source does not cover the question.
reviewed: 2026-11-12
status: active
levers:
  - prompt
applies_to: all
cost: low
---

# Answer only from the source

## When to use

- The agent has its knowledge source in context: a search tool, a skill,
  or text in the prompt. The traces show that it reads the source.
- The answers still go past the source: they add facts that the source
  does not hold, fill a gap with general knowledge, or answer a question
  that the source does not cover.
- The eval rewards answers that stay inside the source, or answers that
  say when the source has no answer.

This is often the second step after the source is attached.

## When not to use

- **The source is not in context yet.** A rule of scope cannot help when
  there is nothing to stay inside:
  [attach the knowledge source](references/improving_agents/techniques/attach-the-knowledge-source.md) first.
- **The agent does not read the source.** That is a read failure, not a
  scope failure. Look at the tool or the skill first.
- **The source is wrong or stale.** A rule that says "only the source"
  makes the agent repeat the error.
- **The task wants general knowledge** beside the source. Read the task
  instruction before you narrow it.
- **A closed list of topics as the qualifier** ("answer only about A, B and
  C"). A list is narrower than the source, and it goes out of date. The
  model then declines a question that the source covers, because its topic
  is not on the list. State the rule by the source, not by topic.

## Alternatives

- [Attach the knowledge source](references/improving_agents/techniques/attach-the-knowledge-source.md), when the
  source is not in context.
- [Decline rules paragraph](references/improving_agents/techniques/decline-rules-paragraph.md), when the problem is
  requests outside the task's scope, not detail outside the source.

## How

The change is one edit of the [prompt](references/levers/prompt.md).

1. **Write one short paragraph** that names the source as the agent sees
   it (the tool, the skill or the section of the prompt) and states the
   rule: the answer uses what the source says.
2. **Say what to do when the source has no answer**: say so, ask a
   question, or decline in the form that the task wants. Take that form
   from the task instruction.
3. **Say what is allowed beside the source**, when the task allows
   anything: for example plain arithmetic on the facts the source gives.
4. **Replace, do not add.** Remove other lines that state the same rule
   less well.
5. Do not copy a phrase from an eval or its judge. State the rule in your
   own words.

## Check that it took effect

Smoke on two kinds of train item: one that the source does not cover, and
one that it covers. On the first, count the answers that say the source
has no answer. On the second, check that the agent still answers. A rule
that makes the agent decline questions the source covers is too strong.

## Budget

Low cost: one prompt edit. On a small budget it is a good second step
after the source is attached, when the residual failures show answers
outside the source.

## If it does not move the evals

It must move an eval. The rule exists to fix measured answers outside the
source. When those do not fall, the cause is another one.

## Priors

None yet.

## Confidence

Medium. It is common field practice for grounded answers, and the reason
is plain: the rule names the source as the limit of the answer. No measured
case is recorded here yet. The risk is known: a rule that is too strong
moves the failure to over-refusal.
