---
title: Missing context the agent could be given
description: The agent fails because it did not know a fact that a tool could give it - if it had known that, it would have done the right thing. A prompt line to always call that tool, or a new tool.
reviewed: 2026-11-13
kind: failure
applies_to:
  - tools
---

# Missing context the agent could be given

## Situation

The agent answers from what it has, and what it has is not enough. A
tool could give it the fact, and it did not think to call that tool. Read
a failing train trace and ask: "If it had known that, would it have done the
right thing?" Signs:

- the answer is right for the request as stated, and wrong for the state
  of the account, the order or the case;
- the trace has no call to the tool that holds that state, or the call
  comes after the answer was decided;
- in a passing item of the same kind, the agent called that tool, or the
  request itself stated the fact.

Example: a support agent answers a billing question and does not check
for a pending cancellation. When it is told that the account will close
in three days, it answers correctly.

The facts that the agent needs are often the same kind on every item.
List them from the failures: what the agent must be given, not left to
request.

## What to try, in order

1. A prompt line that tells the agent to always call the tool, when one
   existing tool already gives the needed context in a compact form. For
   example: "At the start of each request, call `get_account_status`."
   This is a prompt line, not tool text, and it is an exception to the
   preference for tool text over prompt rules. It is guidance about the
   agent's own workflow ("always call X"), not about how one tool works.
   The exception covers any "call X at the start" line, for an existing
   tool or a new one: that line goes in the prompt. The tool's own
   description says what the tool does and when it applies, and it can
   also say "call this first".
2. [Roll-up tool](references/improving_agents/techniques/roll-up-tool.md), when no such tool
   exists: the facts are spread across many tools, or a call to the tools
   on every session costs too many tokens. Build one tool that loads the
   context the agent needs at the start, in a compact form, and a prompt
   line that says to call it first.
3. [Cap and preview wrapper](references/improving_agents/techniques/cap-and-preview-wrapper.md),
   when the context tool returns much more than the facts the failures
   show. A context loader that returns everything floods the context.

## What not to do yet

- Do not give the agent many tools that each return mostly noise. The
  context loader returns only the facts that the failures show the agent
  needs.
- Do not put the facts of train items into the prompt. They change from
  item to item, and the generality check refuses them.
- Do not rely on a prompt rule alone ("check the account first") when no
  single tool gives the fact. The agent still has to find and chain the
  calls.

## Budget

The order does not change with the budget. Step 1 has a low cost: one
prompt line. Step 2 has a medium cost: a new code tool.
