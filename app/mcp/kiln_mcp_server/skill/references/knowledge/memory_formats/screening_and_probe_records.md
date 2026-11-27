---
name: screening_and_probe_records
description: Read-only - the formats of the screening and quick-check records that Kiln Harness Tuner's code writes - the SCREEN and PROBE overviews, their tags and content lines, and how to read a screening survivor under a speed or cost goal.
---

# Screening and quick-check records

Kiln Harness Tuner's code records every screened candidate's result in
task scope with the `screen` tag, so a later run starts from it. Its code
is the authority on their format. They are here so that you can read
them. Never write or edit one (`references/knowledge/memory.md`).

## Screening records

Tags: `screen`, with `lesson` for a survivor or a capped result, and
`dead_end` for a dead end.

| Overview | What it means |
|---|---|
| `SCREEN SURVIVOR: <label> — <passed>/<judged> vs baseline <b>` | It survived the screening |
| `SCREEN SURVIVOR: <label> — lost <k> of <n> baseline passes, no loss rate above <X>% at 95%` | It survived a screening for speed or cost |
| `SCREEN DEAD END: <label> — <reason>` | Ruled out. Do not propose it again unchanged |
| `SCREEN CAPPED: <label> — <capped line>` | The spend cap was hit: inconclusive, never a dead end |

A survivor under speed or cost is a bound on a loss, never "quality
held": the candidate can still lose up to `<X>%` of what the baseline
passes. Its fixes of baseline failures are at the noise level, and they
never make up for a loss.

The content is `key: value` lines, in this order: `candidate`,
`run config`, `label`, `overrides` (JSON), `parent rc`, `round` (the size
tier), `round no` (the run's round counter), `items`, `screened on evals`,
`verdict`, `reason`, `quality`
(`passed <p>/<n> vs baseline <b> (fixed <f>, broke <k>)`), `measured` (the
full measured line), `run` (the run id), `date`, `baseline rc`, `result`
(the result as one JSON line, which code reads back). An older dead end
can have only `candidate`, `run config`, `round`, `screened on evals`,
`reason` and `measured`, and code still reads them. Quality is against
that run's baseline; latency is from that run's window and is orientation
only in a later run.

## Quick-check records

A quick check's answer is a `lesson` with the tag `probe`. The overview is
`PROBE <item>: <question> → YES`, `→ NO` or `→ UNCLEAR`. The content is
`key: value` lines: `question`, `answer`, `method`, `evidence`, `drives`,
and when they apply `ephemeral rcs`, `for idea` and `notes`.
