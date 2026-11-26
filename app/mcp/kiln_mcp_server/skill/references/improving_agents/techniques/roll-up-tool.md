---
title: Roll-up tool
description: One code tool that does what the agent does in many calls - a fixed chain that passes an id along, a loop of one call per item, or the context the agent needs at the start.
reviewed: 2026-11-16
status: active
levers:
  - new_tool
  - prompt
applies_to:
  - tools
cost: medium
---

# Roll-up tool

## When to use

- **A fixed chain.** The traces show the same tools called in the same
  order, and an id from one result passed to the next call. The model is
  invoked between each call, but it decides nothing new.
- **A loop of one call per item.** The agent calls one tool once for each
  item of a list, and one error can stop the loop.
- **Missing context.** The agent fails because it did not know a fact
  that a tool could give it, and it did not think to call that tool. When
  it is given that fact, it does the right thing. The facts that the
  agent needs are the same kind on every item: the account, the order, the
  state of the request.

## When not to use

- **The chain changes from item to item.** When the agent chooses the
  next call from what the last one returned, a fixed tool removes a
  choice that the agent needs. Fold only the part that is the same each
  time.
- **The calls write.** A roll-up of writes makes one call do many
  changes. Fold reads first. A write in a roll-up needs a guard:
  [guard tool calls at the boundary](references/improving_agents/techniques/guard-tool-calls-at-the-boundary.md).
- **Each result is large.** A roll-up of large results is one large
  result. Trim first: [cap and preview wrapper](references/improving_agents/techniques/cap-and-preview-wrapper.md).
- **One existing tool already gives the context in a compact form.** A
  prompt line that tells the agent to always call it costs less:
  [missing context the agent could be given](references/improving_agents/playbooks/missing-context-the-agent-could-be-given.md).
- **The context tool returns everything that it can.** A context loader
  that returns all fields of many APIs floods the context. It returns only
  the facts that the failures show the agent needs.
- **An eval scores the tool calls.** An eval made from the Kiln template
  `tool_call`, a `tool_call_check` eval config, or a judge whose criteria
  name a tool can expect the tools that a roll-up replaces. Read the spec
  of that eval first. Keep the tool names that it expects, or list that
  eval in the candidate's `evaluation_target` as a stated coupling.

## Alternatives

- [Cap and preview wrapper](references/improving_agents/techniques/cap-and-preview-wrapper.md), when one call
  returns too much, not many calls in a row.
- [Consolidate tools](references/improving_agents/techniques/consolidate-tools.md), when the problem is many
  narrow tools that the agent chooses among, not a chain that it calls in
  one order.
- [Directive in the tool response](references/improving_agents/techniques/directive-in-the-tool-response.md),
  when the agent calls the right tools and then its reply misstates the
  result.

## How

The change is a new code tool on a new run config (the lever
[new_tool](references/levers/new_tool.md)). For a context loader, it is also one
line in the [prompt](references/levers/prompt.md) that says to call the tool
first. The tool and the line are one set of changes.

1. **Find the pattern in the traces.** List the calls of a few train
   items in order, with the value that each call passes to the next. A
   roll-up is worth it when the same sequence appears on most items.
2. **Choose the form.**
   - **A chain**: one tool that takes the input of the first call, makes the
     calls in order, and returns the facts that the agent used from any call
     in the chain. The template
     `references/knowledge/code_tool_wrappers/composite_resolve_fetch.md`
     has this shape for search, disambiguate and fetch.
   - **A loop**: one tool that takes a list, runs the operation on each
     item, and returns what was done and the errors for each item. A partial
     success is then usable. The template
     `references/knowledge/code_tool_wrappers/batch_with_errors.md` has this
     shape.
   - **A context loader**: one tool, for example `get_account_context`,
     that calls the tools that hold the facts and returns a short summary
     of them. Add one prompt line that tells the agent to call it before
     it answers. This line is the workflow exception of
     [missing context the agent could be given](references/improving_agents/playbooks/missing-context-the-agent-could-be-given.md).
3. **Return a compact result.** Keep the fields that the agent uses in
   its answer or in its next step. Drop the ids that it only passed
   along.
4. **Drop the tools that the roll-up replaces** when the agent no longer
   needs them alone. Remove each mention of them in the prompt and in the
   skills. When the agent still needs one of them for other work, keep it,
   and say in the roll-up's description when to prefer the roll-up.
5. **Write from the traces and the tools**, never from the values of a
   train item.

## Check that it took effect

Dry-run the tool on a read. Then smoke two or three train items that
showed the pattern. In each trace, find one call to the roll-up where the
baseline made several calls, and fewer model turns before the answer. For
a context loader, find the call before the answer, and the fact from it in
the answer.

## Budget

Medium cost: one code tool, a dry run, and a measurement on its target
evals. When it fixes its target, the confirmation on val measures every eval
before a promotion, the evals that the tools touch too. A good step on any
budget when the traces show the same chain on most items, because each item
then costs fewer model calls. A context loader that fixes a class of
failures is worth a slot on a small budget.

## If it does not move the evals

It depends. Keep a chain or a loop roll-up when the calls, the latency or
the cost per item fall and no eval goes down: the agent does the same work
in fewer steps. A context loader exists to fix failures. When the failures
that it targets do not fall, the agent did not call it, or it did not
return the fact that was missing.

## Priors

None yet.

## Confidence

Medium. It is field practice from public guidance on tool design, and it
follows from cost: each call in a chain is one more model turn, with the
whole context read again. Low, for the size of the gain on a given agent:
no measured case is recorded here yet.
