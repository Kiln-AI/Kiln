---
title: Document into a skill
description: Move a long reference document that sits behind a lookup tool into a skill - a contents body with key terms, one reference file per section - and drop the tool.
reviewed: 2026-11-13
status: active
levers:
  - skill
  - tool_config
applies_to:
  - tools
cost: medium
---

# Document into a skill

## When to use

- A long reference document sits behind a lookup tool: the agent reads it
  by page, by search or by section.
- The traces show the agent pick the wrong part, read many pages to find
  one fact, or never look.
- The document is stable, and it fits in a skill bundle as text.

## When not to use

- **You do not have the documents themselves.** You need the documents to
  do this. You may have them from existing traces, or from additional
  context from the user. If you lack them, do not attempt this method.
- **The agent already finds the right part** with the tool. The change
  adds a bundle and fixes nothing.
- **The document is very large, or it changes often.** A skill is
  immutable: each change of the document needs a new version.
- **The knowledge is not reachable at all**:
  [attach the knowledge source](references/improving_agents/techniques/attach-the-knowledge-source.md).
- **Do not add prompt rules on which page or section to choose.** The
  model then has to apply a rule to a choice that a contents file makes
  plain.

## Alternatives

- [Attach the knowledge source](references/improving_agents/techniques/attach-the-knowledge-source.md), when no
  source of the knowledge is in context.
- [Rewrite an inherited skill](references/improving_agents/techniques/rewrite-an-inherited-skill.md), when the
  document is already a skill and the agent reads the wrong file: a new
  version with a better description and body map.

## How

The change is a new [skill](references/levers/skill.md), and the lookup tool
dropped on the same new run config
([tool_config](references/levers/tool_config.md)).

1. **Get the documents themselves.** You need the documents to do this.
   You may have them from existing traces, or from additional context from
   the user. If you lack them, do not attempt this method. For the move
   that drops the tool, a part of a document is not enough: the same candidate
   drops the tool, so a section that the bundle leaves out loses its facts
   with no sign.
2. **Build the bundle from the document**, never from the train items (the
   leak rules of `references/knowledge/train_val_test.md`): one
   `references/` file for each section, and a body that maps each file. The
   steps are in Kiln Harness Tuner's skill-authoring guide, sections 2
   and 3. Section 4 ends with this same move. When the path index does not
   fit in the description, group the sections.
3. **Drop the lookup tool on the same candidate.** With both, the agent chooses,
   and the result does not tell which path it took. Remove each mention of
   the tool in the prompt and in other skills.
4. When the document cannot move (it is too large, or it changes often),
   a smaller change is a skill that holds only the keyword contents and
   names the tool's sections, with the tool kept.

## Check that it took effect

Smoke on two or three train items that need the document. In each trace,
find the read of the right section file before the answer, and no call to
the dropped tool.

## Budget

Medium cost: a bundle to write from the document, and a measurement on its
target evals. When it fixes its target, the confirmation on val measures
every eval before a promotion, the evals that the document touches too. On a
small budget, take it when the traces show wrong parts read, or many lookup
calls for one fact.

## If it does not move the evals

It depends. Keep it when it replaces many lookup calls and the cost or the
latency per item falls with no eval down, because the agent reaches the
fact in fewer steps. When the calls do not fall and no eval moves, the tool
was good enough.

## Priors

None yet.

## Confidence

Low to medium. It is reasoning, not a result: a contents file with key
terms lets the agent choose a section before it reads, which a lookup tool
does not. It applies the same progressive disclosure as other skill
techniques. No measured case is recorded here yet.
