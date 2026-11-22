---
title: Attach the knowledge source
description: Give the agent the knowledge its answers need - attach an existing search or RAG tool, or write the knowledge into a skill - when the answers are not grounded.
reviewed: 2026-11-16
status: active
levers:
  - tool_config
  - skill
applies_to: all
cost: medium
---

# Attach the knowledge source

## When to use

- The answer needs facts that are not in the agent's context: a product
  catalogue, a policy, a schema, a set of past cases.
- The traces show invented facts, or general answers where a specific one
  was needed, and no read of a source before the answer.
- The knowledge exists in a form that the tuner can reach: a search tool,
  a RAG tool or an MCP tool that the run config does not attach, or text
  that can go in a skill.

## When not to use

- **The source is attached, and the agent goes past it.** That is scope
  discipline: [answer only from the source](references/improving_agents/techniques/answer-only-from-the-source.md).
- **The source is a long document behind a lookup tool**, and the agent
  picks the wrong part: [document into a skill](references/improving_agents/techniques/document-into-a-skill.md).
- **Do not swap the model for this failure.** Another model does not know
  private facts either.
- **Do not narrow the answer to a closed list of topics** in place of a
  source. A list does not add the facts.
- The tuner cannot create a RAG config. When no tool exists and the
  knowledge is too large for a skill, this technique is out of reach.

## Alternatives

- [Document into a skill](references/improving_agents/techniques/document-into-a-skill.md), when the knowledge is
  a long document that a lookup tool already serves.
- [Answer only from the source](references/improving_agents/techniques/answer-only-from-the-source.md), when the
  source is already in context.

## How

The change is one of two, on a new run config: attach a tool that exists
([tool_config](references/levers/tool_config.md)), or write the knowledge into a
[skill](references/levers/skill.md).

1. **Find the source.** Read `list_available_tools` for a search, RAG or
   MCP tool that holds the knowledge. Read the task instruction and the
   attached skills for knowledge that is named and not given.
2. **Attach the tool**, when one exists. The model reads its description to
   decide whether to call it. When the description does not say what the
   source holds, a wrapper with a new description is a second
   change.
3. **Or write a skill**, when the tuner has the text of the knowledge.
   The sources for the skill's text are:
   - the task instruction;
   - existing skills and prompts;
   - the output of a tool that the run config can attach;
   - documents that the user supplied.

   The builder's own knowledge alone is usually not enough. It can be
   enough when the builder's model is much stronger than the agent's
   runtime model, for example a frontier builder that writes for a small
   local model. It is not enough when the two models are peers: the agent
   already knows what the builder knows. The train labels are never a
   source (step 5). The shape of the bundle is in the
   `kiln-harness-tuner-experiment-build` skill,
   `references/skill-authoring.md`, section 2.
4. **Choose the content by what the agent does with it.** Worked examples
   of correct work (for a query agent: example queries) can help more than
   general notes about the domain. Records that do not match the question
   can lower the result: see the prior below.
5. **Never write a value from a train item** into the skill, and never an
   expected answer. Facts that the skill holds only because the train
   labels show them are a leak too, even when they copy no value. The
   labels can show which rule the agent misses; they are not a source of
   the skill's facts.
6. A prompt line that tells the agent to use the source is part of the
   hypothesis, or a second arm. Scope discipline is the next step:
   [answer only from the source](references/improving_agents/techniques/answer-only-from-the-source.md).

## Check that it took effect

Smoke on two or three train items whose answers were not grounded. In each
trace, find the call to the tool or the read of the skill before the
answer, and the fact from the source in the answer. When the agent never
looks, the source did not reach the decision.

## Budget

Medium cost: a tool to attach is cheap, a skill to write is not, and both
need a measurement on their target evals. When it fixes its target, the
val gate measures every eval before a promotion, the evals that the
knowledge touches too. On a small budget, take it when the traces show
answers that need facts the agent does not have. It is the first step for
that failure.

## If it does not move the evals

It must move an eval. The source exists to fix measured answers that are
not grounded. When the agent reads the source and the answers do not
improve, the source does not hold what the answers need, or the agent
answers past it. When the traces show that the agent read the source and
still answered past it, the source can be right. Plan the source together
with the rule of [answer only from the source](references/improving_agents/techniques/answer-only-from-the-source.md)
on one arm, and name both in the hypothesis.

## Priors

- **A text-to-SQL analytics agent over a company's data warehouse, judged
  by an LLM on 133 questions from domain experts.** An ablation removed
  the parts of its knowledge source in sequence, each removal on top of the
  ones before it. Example queries raised the share of answers rated correct
  or close to correct from 24% to 49%. Domain-knowledge and jargon records,
  on top of those, lowered it to 42%. The authors suggest that records
  which do not match the question lower the result. One sample, not a rule.
  Source: public, the LinkedIn paper "Text-to-SQL for Enterprise Data
  Analytics", arXiv 2507.14372. 2025-07-18.

## Confidence

Medium. Attaching the source is the common first step for answers that are
not grounded, in field practice: a model cannot state a private fact that
it does not have. One public case shows that what the source holds matters
as much as whether it is attached. The condition on the builder's own
knowledge is reasoning: a skill adds facts only when its writer knows what
the agent's model does not.
