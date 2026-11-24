---
title: Consolidate tools
description: Replace many narrow or overlapping tools with a few general wrappers by job, each with the product's policy inside - its permission checks, guards and defaults.
reviewed: 2026-11-16
status: active
levers:
  - new_tool
  - tool_config
applies_to:
  - tools
cost: high
---

# Consolidate tools

## When to use

- The agent has many tools that each do one small thing, or tools that
  overlap, and the traces show it pick the wrong one.
- The agent breaks a rule that the product enforces, because no tool
  carries the rule: a permission check, a required step, a default.
- The tools mirror the endpoints of an API, one for one, and the work of
  the task needs several of them for each step.
- A smell of too many tools or of unnecessary tools is reported, and
  removal alone would leave a part of the work with no tool.
- The agent finds its tools through tool search, with no list of them to
  read. The collapsed style is one general tool that can call each
  operation, such as a `call_api` tool, with a guide skill that names the
  operations (step 6). A search call and a load call before each use are
  then gone.

## When not to use

- **The tools are few and clear**, and the agent chooses well. A
  redesign costs a large build and a full measurement.
- **The tools are needed, and only one pair is confused.** A new
  description is cheaper: [new tool description](references/improving_agents/techniques/new-tool-description.md).
- **Many tools are attached and never called.** Drop them first:
  [remove or scope tools](references/improving_agents/techniques/remove-or-scope-tools.md).
- **A prompt list of which tool to use when is not the fix.** Prefer the
  tool descriptions to the prompt. Text in a tool moves with the tool. So
  a later experiment that changes the tool set needs no prompt change, and
  its result stays clean. A prompt list ties the prompt to the tool set,
  and it grows with each tool. A tool set with one tool for each job makes
  the choice plain.
- **An eval scores the tool calls.** An eval made from the Kiln template
  `tool_call`, a `tool_call_check` eval config, or a judge whose criteria
  name a tool can expect the tools that a consolidation merges or renames.
  Read the spec of that eval first. Keep the tool names that it expects, or
  list that eval in the candidate's `evaluation_target` as a stated coupling.

## Alternatives

- [Remove or scope tools](references/improving_agents/techniques/remove-or-scope-tools.md), when the extra tools
  are not used, so no new tool is needed.
- [New tool description](references/improving_agents/techniques/new-tool-description.md), when better
  descriptions on clones or wrappers of the existing tools can make the
  choice clear.
- [Roll-up tool](references/improving_agents/techniques/roll-up-tool.md), when the problem is a fixed chain of
  calls, not a choice among tools.
- [Guard tool calls at the boundary](references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md),
  when the only problem is one rule that one tool must enforce.

## How

The change is a set of new code tools that wrap the existing ones (the
lever [new_tool](references/levers/new_tool.md)), and a new tool list that attaches
the new tools and drops the tools that they replace
([tool_config](references/levers/tool_config.md)). The tools of the company stay as
they are. The wrappers are a layer over them.

1. **Group the tools by job** from the task and the traces: for example
   "find a record", "read a record", "change a record". A job is what the
   agent wants to do, not one endpoint.
2. **Write one wrapper for each job.** It calls the existing tools that
   the job needs, with a parameter that selects the variant (for example
   the record type). Its description says what the job is and when to call
   it. That text goes in the description, not in the prompt.
3. **Put the product's policy inside.** From the product's own rules: the
   permission check, the required step before an action, the defaults, the
   limits. The wrapper refuses a call that breaks a rule, with an error
   that says why.
4. **Attach the new tools and drop the replaced ones** on the same run
   config. With both, the agent chooses, and the result does not tell
   which path it took. Remove each mention of a dropped tool in the prompt
   and in the skills.
5. **Plan it as an experiment that makes this change alone.** A consolidation
   changes many tools at once. When it is measured together with a prompt
   or a skill change, the result does not tell which change moved it, and
   the next plan cannot build on it.
6. **The guide changes with the tools.** When a guide skill describes the
   old tools, its new version is part of the same set of changes:
   [guide skill for a tool set](references/improving_agents/techniques/guide-skill-for-a-tool-set.md).

## Check that it took effect

Dry-run each wrapper with reads, and with a call that breaks a rule. Read
the new run config: the new tools are attached and the replaced tools are
gone. Then smoke two or three train items that chose the wrong tool, and
count the calls to the right job.

## Budget

High cost: several code tools, a dry run for each, and a measurement on its
target evals. When it fixes its target, the confirmation on val measures
every eval before a promotion. That matters here, because the change touches
every call. On a small budget, leave it out unless the traces show wrong
tool choices on many items and cheaper changes did not fix them. On a large
budget, it is a good step once the cheaper tool changes have been measured.

## If it does not move the evals

It depends. Keep it when the calls, the latency or the cost per item fall
and no eval goes down: fewer tools with the policy inside are a better
design for the next changes. When nothing falls and no eval moves, the old
tools were good enough, and the larger tool code is a cost to maintain.

## Priors

None yet.

## Confidence

Low to medium. Public guidance on tool design and public case studies
agree that tools by job are better for an agent than one tool for each
endpoint, and that fewer tools are easier to choose from. No public case
here measures a consolidation alone, apart from the other changes made
with it. It follows from first principles: a few tools with clear jobs
leave fewer wrong choices on each call.
