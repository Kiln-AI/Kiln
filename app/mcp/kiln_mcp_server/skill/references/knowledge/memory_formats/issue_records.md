---
name: issue_records
description: Read-only - the formats of the issue records that Kiln Harness Tuner's code writes - the overview and its state prefixes, the setup head above the delimiter line, the lines it appends, its smell and audit tags, and how to read each.
---

# Issue records

Kiln Harness Tuner's code seeds an `issue` for each eval, writes every
state prefix and appends the lines below. Its code parses these strings
back and is the authority on them. They are here so that you can read
them. What you may write on an issue is in
`references/knowledge/memory.md` ("Issues belong to evals").

## The overview

`[<STATE>: ]issue: <one line>`. The lead `issue: ` is on the issues that
Kiln Harness Tuner writes; its code does not require it when it reads.

| Prefix | What it means |
|---|---|
| none | Open |
| `UNMEASURED: ` | Nobody has checked yet whether the baseline fails its eval |
| `UNMEASURABLE: ` | None of its evals is left, or each has left the active set. A status, never a close: the finding can still be true |
| `FIXED: ` | Closed by a fix. Never reopened by an agent |
| `WONT_FIX: ` | Closed by a decision, or not reproduced. Never reopened by an agent |

A list returns closed issues too: skip them by their prefix.

## The tags

- `issue`, a priority `p0` to `p3`, and `eval_<eval_id>` for each eval
  that measures it. The priority comes from its source (the spec's
  priority, else `p1`), and the next re-sync replaces the tag: a change by
  an agent does not last.
- An issue from the review of the baseline's design carries `smell`,
  `smell_<smell id>` and `audited_rc_<run config id>`. An issue from the
  leak audit of the baseline carries `baseline_audit` or
  `baseline_judge_copy`, and `audited_rc_<run config id>`. These are about
  the agent's design, not an eval: they are bound to no eval on purpose.

## The content

The content has two owners, split by this line, on a line of its own:

```
— setup wrote everything above; lines below belong to the loop —
```

Above it, the head, which Kiln Harness Tuner rewrites when the eval
changes:

```
<description>
eval: <eval id> (<eval name>, <config kind>)
priority: p<n> (source: spec <spec id>)
status: <state> at sync · fp: <hex> · synced <YYYY-MM-DD>
```

With no spec, the source is `default`. The `status:` line is a
snapshot: the overview prefix is the state. Never edit above the line.
Below it is history, appended only. An issue with no such line is all
history.

The lines its code appends below it, with the date as `MM-DD`:

- `- eval: <eval id> (built <MM-DD>, reproduced)`, or
  `- eval: <eval id> (linked by kiln-harness-tuner setup <MM-DD>)`: the
  link to its eval, for people. The tag is the binding.
- `- fixed <MM-DD> by <citation>`
- `- WONT_FIX (<MM-DD>): <reason>`
- `- reopened when promoting baseline <run config id>. Issue repros on <run config id>.`
- `- repros on baseline <run config id> (noted at promotion).`
- `- landed in merge <run config id> — reduced, not closed; still repros.`
- `- reproduced on baseline <run config id> <MM-DD> (<summary>)`, or
  `- not reproduced on baseline …`
- `- eval rubric changed; description resynced <MM-DD>`
- `- <cause> (noted <MM-DD>)`: why it became `UNMEASURABLE: `.

None of these lines holds a val number.
