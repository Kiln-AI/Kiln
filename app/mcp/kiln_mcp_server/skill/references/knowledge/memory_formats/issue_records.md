---
name: issue_records
description: Read-only - the formats of the issue records that Kiln Harness Tuner's code writes - the overview and its state prefixes, the setup head above the delimiter line, the lines it appends, its smell and audit tags, and how to read each.
---

# Issue records

Kiln Harness Tuner's code seeds an `issue` for each eval, writes every
state prefix and appends the lines below. Its code parses these strings
back and is the authority on them. They are here so that you can read
them. What you may write on an issue is in
`references/knowledge/memory.md` (the `issue` row of "Tags", and "Issues
are derived children of evals").

## The overview

`[<STATE>: ]issue: <one line>`. The lead `issue: ` is on the issues that
Kiln Harness Tuner writes; its code does not require it when it reads.

| Prefix | What it means |
|---|---|
| none | Open: the default (a priority tag, nothing more) |
| `UNMEASURED: ` | Seeded from an eval but nobody has checked yet whether the baseline actually fails it (setup seeds every active eval one; measuring it is the planner's spend decision) |
| `UNMEASURABLE: ` | The eval it binds to is gone or has left the active set, so it cannot be experimented on at all — a status, never a decision and never a close (the finding may still be true; the cause line says which). Only when *none* of its bindings is active |
| `FIXED: ` | A landed fix front-loads it onto the overview, with a content one-liner citing it (`fixed 07-15 by rc_207, EXP 0715-w3-1`). A terminal state: the loop does not un-close it |
| `WONT_FIX: ` | Deliberate decision or not reproduced, reason in content (cite which). A terminal state: the loop does not un-close it |

One prefix at a time: setting a new one strips the old. Reopened = strip
the prefix + append the provenance line
(`- reopened when promoting baseline rc_213. Issue repros on rc_213.`) —
never a duplicate memory; a human re-opens a `FIXED:` or `WONT_FIX:` issue
this way.

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

Above it: the description, eval identity, priority and its source, and a
`status: … fp: … synced …` line (a sync-time snapshot; the overview prefix
is the authoritative state). Setup replaces that whole block when the
eval's rubric, config, spec or priority changes:

```
<description>
eval: <eval id> (<eval name>, <config kind>)
priority: p<n> (source: spec <spec id>)
status: <state> at sync · fp: <hex> · synced <YYYY-MM-DD>
```

With no spec, the source is `default`. The delimiter and everything below
are loop-owned and append-only: setup preserves them byte-for-byte and
never parses them for meaning. **Never edit above the delimiter by hand** —
the next sync overwrites it; findings and history go below. A record with
**no delimiter** (legacy, or written by an agent) is treated as entirely
loop-owned: setup prepends its head and touches nothing else.

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
