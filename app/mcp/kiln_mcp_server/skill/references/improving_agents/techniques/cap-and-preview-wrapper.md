---
title: Cap and preview wrapper
description: A wrapper that returns only what this agent needs from a large tool result - a trim that says when it cut and how to get more, a capped preview with a follow-up, or an error when it is too large.
reviewed: 2026-11-13
status: active
levers:
  - new_tool
applies_to:
  - tools
cost: medium
---

# Cap and preview wrapper

## When to use

- A tool returns a very large result: a list with every field, a long
  text field in each row, a full schema, many pages of rows.
- The agent reads a large result to find one small fact, for example one
  id to pass to the next call.
- The traces show a result so large that it pushes earlier context out,
  or a run that ends at a limit after such a result.
- A general query tool (SQL, GraphQL) can return any number of rows, and
  nothing stops a query that returns too many.

## When not to use

- **The results are small already.** A wrapper adds a tool and a
  measurement, and removes nothing.
- **The agent needs the whole result**, for example a document that it
  must quote in full. Then the problem is where the content lives:
  [document into a skill](references/improving_agents/techniques/document-into-a-skill.md).
- **The large result comes from many calls, not from one.** That is a
  loop of one call per item: [roll-up tool](references/improving_agents/techniques/roll-up-tool.md).
- **Do not try a prompt line alone** ("ask for fewer rows", "read only
  the first items"). The size of a result is a property of the tool. A
  rule in the prompt asks the model to avoid what the tool still does, on
  every call.

## Alternatives

- [Roll-up tool](references/improving_agents/techniques/roll-up-tool.md), when the agent calls a chain of tools,
  or one tool once for each item, and each result is small.
- [Errors the agent can act on](references/improving_agents/techniques/errors-the-agent-can-act-on.md), when the
  result is large because the tool returns a raw error body.
- [Guide skill for a tool set](references/improving_agents/techniques/guide-skill-for-a-tool-set.md), when the
  agent asks for too much because it does not know how to ask for less
  (the filters, the fields, the query forms).

## How

The change is a new code tool that wraps the large tool, on a new run
config. See the lever [new_tool](references/levers/new_tool.md) for how a wrapper
is built, dry-run and attached.

There are three forms. Choose the form from what the agent does with the
result in the traces.

1. **Trim to what this agent needs.** The wrapper calls the tool and
   returns a smaller result. The exact design depends on the wrapped tool
   and on the use case. Use your judgement, and let the dry run, the
   smoke and the evals check it. A good design has three parts:
   - **It trims, but not too much.** It drops what the agent does not
     use: ids that it never passes on, long text fields, nested objects.
     When the agent uses an id only to find a name, it returns the name.
     It keeps what the task can need, not only what one trace used.
   - **It keeps a way to get more.** For example, a `limit` parameter with
     a default of N that the agent can set higher, and an `offset` with a
     default of 0.
   - **It says clearly when there is more**, for example `was_truncated`
     and the `total`. Then the agent always sees that a result was cut.

   Form 1 cuts each row, and pages the rows. Form 2 returns a preview, and
   a separate call that gets one item in full.
2. **Preview and cap.** The wrapper returns the total count, the first N
   rows in the trimmed form, and how to get more: a cursor, or a filter.
   A follow-up query (a second wrapper, or a parameter of the same one)
   gets one item in full. The wrapper template `preview_and_cap.py` of the
   code-tool authoring skill has this shape. When a list has many pages,
   the template `paginate_all.py` fetches every page up to a cap and says
   that the list was cut.
3. **Refuse a result that is too large.** For a general query tool, the
   wrapper counts or limits the rows before it returns them. Over the
   limit, it returns an error that says how many rows the query would
   give and how to narrow it (a filter, a date range, an aggregate). This
   makes the agent write a narrower query, and the large result never
   reaches the context.

For each form:

- **The wrapper's description says when to prefer it** over the tool that
  it wraps, in the words that the agent uses.
- **Drop the wrapped tool on the same run config** when the wrapper
  replaces it. With both, the agent chooses, and the result does not tell
  which path it took.
- **Set the default cap from the traces**: the largest number of rows that the
  agent used in one answer, with a margin. Do not set it from a train
  item.
- A prompt line that tells the agent to prefer the wrapper is a second
  change. Measure it on its own, or state it as part of the hypothesis.

## Check that it took effect

Dry-run the wrapper on a read that returns a large result, and compare
its size with the size of the raw result. When the result was cut, find
the signal that says so, and get the rest with a second call (a higher
limit, or an offset). Then smoke two or three train items that called
the large tool. In each trace, find a call to the wrapper, no call to the
dropped tool, and a tool result that is smaller than the baseline's.

## Budget

Medium cost: one code tool, a dry run, and a measurement on its target
evals. When it fixes its target, the val gate measures every eval before a
promotion, the evals that the tool touches too. When a very large result
is in the traces, it is a good first step on any budget: other changes
measure little while one result can fill the context.

## If it does not move the evals

It depends. Keep it when the tokens or the latency per item fall and no
eval goes down, because a smaller result is cheaper on every call and
leaves room for the rest of the context. When the size of the results did
not fall, the wrapper did not take effect: drop it.

## Priors

None yet.

## Confidence

Medium, that a smaller tool result helps when the result is large. It is
field practice, and it follows from how a model reads its context: every
token of a result costs money and time, and a long result can push out
what the agent needs. Low, for which of the three forms is best: no case
here compares them.
