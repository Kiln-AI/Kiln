---
title: Change the surface, not the words
description: Two text changes failed on one issue, or the failure is mechanical. Change what the model touches before the words it reads. A policy failure comes here only after two text arms failed.
reviewed: 2026-11-16
kind: failure
applies_to: all
---

# Change the surface, not the words

## Situation

This playbook applies in two cases:

- **The failure is mechanical**: a wrong case or form of an id, pages
  that the agent does not follow, a result that floods the context, an
  error that the agent cannot act on, or a rule about one tool that sits
  in the prompt, and the model breaks it. Text in a tool moves with the
  tool, so the tool's own text is the very strong preference for that
  rule.
- **Two text changes failed on one issue.** A text change is a `prompt`
  arm, or a `skill` arm that only changes words (a description, a body).
  Your input's `lever_attempts` counts the arms opened on each issue and
  lever, with any outcome. The experiment records say which of them
  failed.

Instruction text is the cheapest change to build. For a mechanical
failure it can be the most expensive to learn from. The model that fails
a mechanical step does not stop because the words ask it to, and a rule
aimed at the failing items can fit the train items and not others. A
change to the surface (a tool, a wrapper, the structure of a skill)
removes the cause, instead of asking the model to avoid it.

Some causes are smells of the design, with their own documents:
[tool results flood the context](references/improving_agents/smells/tool-results-flood-the-context.md)
and [faulty inherited skill](references/improving_agents/smells/faulty-inherited-skill.md).

## What to try, in order

1. A wrapper that removes the mechanical failure, chosen by its cause:
   [normalize inputs wrapper](references/improving_agents/techniques/normalize-inputs-wrapper.md)
   for input forms,
   [errors the agent can act on](references/improving_agents/techniques/errors-the-agent-can-act-on.md)
   for unusable errors,
   [cap and preview wrapper](references/improving_agents/techniques/cap-and-preview-wrapper.md) for
   floods and pages,
   [roll-up tool](references/improving_agents/techniques/roll-up-tool.md) for a chain of calls, and
   [directive in the tool response](references/improving_agents/techniques/directive-in-the-tool-response.md)
   for a reply that misstates a tool's result.
2. A guard at the tool, when the failure is a rule that the product can
   check:
   [guard tool calls at the boundary](references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md).
3. A structural change to a skill, when the failure is in what the agent
   reads: a router with reference files,
   [long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md),
   or a new version of an inherited skill,
   [rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md).
4. **A policy failure, after two failed text arms.** A policy failure is
   not mechanical: the agent breaks a rule of the business that only words
   can carry (who gets a refund, which case needs a person). Its first
   text arm is
   [policy as step-by-step procedures](references/improving_agents/techniques/policy-as-step-by-step-procedures.md),
   through the normal path, not through this playbook. When two text arms
   already failed on a policy issue, change the structure: put the
   procedures in a skill, with one reference file for each procedure
   ([long prompt into a skill](references/improving_agents/techniques/long-prompt-into-a-skill.md)).
   Or defer the issue (step 5).
5. When no surface change fits the issue, defer the issue with the reason
   in `rejected_summary`.

When a wrapper, a guard or a tool takes over a step, the same arm removes
the prompt text that asked the model to do that step.

## What not to do yet

- No third text arm on the same issue after two failed. The planner's
  skill gives the count and the rule.
- No prompt list of rules for a mechanical failure. A wrapper removes the
  failure.
- No model swap to hide a mechanical failure. The cause stays in the
  harness, and a stronger model costs more on every item.

## Budget

The order does not change with the budget. A wrapper costs more to build
than a text change. On a small budget, that cost is still lower than more
text arms that cannot win.

## Priors

- **A customer-service agent with tools, on a retail benchmark, tuned by
  an automatic optimiser.** The optimiser grouped the failures, and sent
  each group to the prompt, to a guard at the tool boundary, or to both.
  With that routing, the mean gain on held-out items was 14.9 points.
  With the routing removed and all else the same, it was 5.4 points. One
  sample, not a rule.
  Source: public, the paper "Beyond Prompts: Measuring and Optimizing LLM
  Tool-Agent Harnesses". 2026-09-09.
