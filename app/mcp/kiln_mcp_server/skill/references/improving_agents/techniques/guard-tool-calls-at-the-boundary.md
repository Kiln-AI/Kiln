---
title: Guard tool calls at the boundary
description: A check in a wrapper that refuses a call which breaks a rule the product enforces, with an error that says why, and the rule moved from the prompt into the tool's description.
reviewed: 2026-11-13
status: active
levers:
  - new_tool
  - prompt
applies_to:
  - tools
cost: medium
---

# Guard tool calls at the boundary

## When to use

- The agent makes a call that the product does not allow: a write in a
  scenario that only reads, an action without a required step before it,
  a value outside a limit, a record of another user.
- The prompt states the rule, and the traces show the agent break it on
  some items.
- The rule can be checked in code from the call and from what the tool
  can read: the arguments, the state of the record, the steps already
  taken in the call's own inputs.

## When not to use

- **The rule needs judgement** about the request, not a check of the
  call. A guard can only refuse what code can test.
- **The agent chooses the wrong tool, and no call breaks a rule.** That is
  a choice among tools: [consolidate tools](references/improving_agents/techniques/consolidate-tools.md), or
  [new tool description](references/improving_agents/techniques/new-tool-description.md).
- **A refused call leaves the agent with no way forward.** When the error
  does not say what to do, the agent retries or gives up. Each refusal
  says why, and what the allowed path is.
- **Do not rely on a prompt line alone for a rule that the product
  enforces.** The model can miss a line on any item. A check in the tool
  holds on every call.

## Alternatives

- [Errors the agent can act on](references/improving_agents/techniques/errors-the-agent-can-act-on.md), when the
  tool already refuses the call and its error is the problem.
- [Consolidate tools](references/improving_agents/techniques/consolidate-tools.md), when the rules belong inside a
  few general tools that carry the product's policy.
- [Directive in the tool response](references/improving_agents/techniques/directive-in-the-tool-response.md),
  when the reply misstates the result of a call, not when a call breaks a rule.

## How

The change is a wrapper with the guard, on a new run config, with the
wrapped tool dropped (the lever [new_tool](references/levers/new_tool.md)),
and an edit of the [prompt](references/levers/prompt.md) on the same
candidate. Make sure every function of the wrapped tool that the agent needs
is in a wrapper tool before you remove it. The template
`references/knowledge/code_tool_wrappers/readonly_guard.md` has one form of
it: a read-only variant of a read-write tool.

1. **State the rule** from the task's instruction, the product's own
   rules, and the traces. Do not copy the text of an eval or of its judge.
2. **Write the check in the wrapper.** Before it calls the tool, the
   wrapper tests the call against the rule. Common forms:
   - a read-only variant, which refuses every write;
   - a precondition, which refuses an action until a required read or
     confirmation is in the call's inputs;
   - a limit on a value, an amount or a count;
   - a scope, which refuses a record outside the user or the account of
     the request.

   A guard is a hard limit only when it checks a fixed value, or a state
   that the wrapper reads itself. A flag or an id that the model supplies
   only makes the model state its intent.
3. **Refuse with an error the agent can act on**: which rule, and what the
   allowed path is ("this tool only reads; to change an order, call
   `update_order` after the user confirms").
4. **Move the rule into the tool's description, and remove it from the
   prompt.** The guard refuses only after a wrong call. So the description
   states the rule, and the model reads it before the call ("call this
   only after the user confirms the change"). Text in a tool moves with the
   tool. So a later experiment that adds, removes or changes the tool needs
   no prompt change, and its result stays clean. Two places that state one
   rule can also disagree after a later change.
5. **Dry-run with reads only**, or with an id that does not exist. A dry
   run makes nested calls for real.

## Check that it took effect

Dry-run the wrapper with a call that breaks the rule, and read the
refusal. Read the new tool's description: it states the rule, and the
prompt does not. Then smoke two or three train items whose traces broke
the rule. In each trace, find the refusal, or a call in the allowed form,
and no call that breaks the rule.

## Budget

Medium cost: a wrapper with a check, a dry run, and a measurement on its
target evals: the evals that check the rule. When it fixes its target, the
confirmation on val measures every eval before a promotion, the evals that
the tool touches too. A good step on any budget when an eval guards a rule
that the agent breaks on some items.

## If it does not move the evals

It depends. Keep it when the rule is a hard limit of the product and no
eval goes down: the guard holds on inputs that the evals do not cover.
When the rule is soft, or the guard blocks valid work, it must move an
eval.

## Priors

None yet.

## Confidence

Medium, for a rule that code can check. Public guidance on tools over
databases and APIs agrees that a limit is held in code or in the system,
and not only in the prompt. It follows from first principles: a check in
code applies to every call, and a line in the prompt applies only when the
model follows it. Low, for how much of the gain comes from the guard and
how much from the rule in the description: no measured case is recorded
here yet.
