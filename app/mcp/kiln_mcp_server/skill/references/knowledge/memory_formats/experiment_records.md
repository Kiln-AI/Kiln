---
name: experiment_records
description: Read-only - the formats of the experiment records that Kiln Harness Tuner's code writes - the id, the opening and the verdict, the state suffixes, the val stamps and lines, the content lines that its code reads back, and what each means for a reader.
---

# Experiment records

Kiln Harness Tuner's code writes every `experiment` record and parses
these strings back; its code is the authority on them. They are here so
that you can read them. Never write, edit or delete an `experiment`
record (`references/knowledge/memory.md`).

## The id

`EXP <MMDD>-w<k>-<n>`: the date the run started, its wave `k` and the item
`n`. Example: `EXP 0723-w4-2`.

## The overview

- **Opened:** `EXP <id> (<technique>): <hypothesis> — RUNNING`. The
  technique is a lever id (`references/levers/index.md`) or `merge`.
- **The verdict** replaces ` — RUNNING` with the numbers first, and drops
  `(<technique>)`: `EXP 0716-w4-2: retry-skill for 429s — accuracy: +18pp, base=62, cand=80, n=34, p=.04`.
  Several rows are joined by ` | `. A score name ending `↓` is
  `lower_is_better`: its delta is positive when the score falls, so a
  falling pair of numbers is a gain.
- **State suffixes**, in place of the verdict or after it:

| Suffix | What it means |
|---|---|
| ` — RUNNING` | Not measured yet. From a run that has ended, it is abandoned work, not a result |
| ` — REFUTED` | Measured: the change did not help |
| ` — FAILED (infra: <error class>)` | Stopped by an infrastructure failure: neither a win nor a dead end |
| ` — ABANDONED (<why>)` | Stopped part way: no verdict |
| ` — DEAD END (<why>)` | Ruled out before or during the measurement, for example `(generality: …)` or `(judge copy: …)` |
| ` — NOT LANDED (<detail>)` | Stopped before train was judged in full. The detail is, for example, `<k>/<n> targets fixed`, `<k>/<n> fixed, <b>/<g> guards broke`, `stopped at n=<n> by <rule>: <numbers>` or `capped at <n> items: …`. Untested, not disproven: another build for the same target is fair; the same run config again is not |
| ` — CAPPED (<detail>)` | A spend cap was hit: inconclusive, never a dead end. The detail is, for example, `capped at $<x> after <n> items: inconclusive — net +<a>/−<b> so far`, under speed or cost `capped at $<x> after <n> items: inconclusive — lost <k> of <n> baseline passes so far`, or `capped by the run budget ($<x> left) after <n> items: …`. The same run config with a larger cap goes on from its rows |

- **No suffix on an opening**: an overview in the opening's shape
  (`EXP <id> (<technique>…`) with no state suffix has lost its state. Its
  code reads it as unknown, never as a verdict.
- **Val stamps**, appended after the verdict, with the date as `MM-DD`:

| Stamp | What it means |
|---|---|
| ` — PROMOTED <MM-DD>` | Its run config became the baseline |
| ` — REJECTED AT VAL <MM-DD>` | The confirmation on val passed it over. Never removed. That run config is never submitted again unchanged; it can still be an ingredient of a merge |
| ` — HELD (constraint <id>) <MM-DD>` | Waiting on the `OPEN: ` record `<id>` (`references/knowledge/memory_formats/open_questions.md`). The same run config goes on, unchanged, once it is answered |

## The content lines its code reads back

`key: value` lines: `hypothesis`, `predicted effect`, `parent rc`, `eval`,
`issue`, `technique`, `head_to_head_group`, `reused rc`, `wildcard`,
`merge of`, `conflict flags`, `rc`, `change`, `generality`, `judge copy`,
`reference check`. The verdict's content also has the analysis, its table
and `bundle cost: $<n>`. `bundle cost` is the spend of the loop's
measurement; elsewhere the spend is labelled `spend`.

- `generality:` is the code's leak check of the build, and `judge copy:`
  its search for eval text in it. Each quotes a finding, or says why it
  could not check.
- `reference check:` names a skill or a tool that the build's text uses
  and its run config does not attach. A failure on the items that use that
  name can be the build's breakage, not the lever.

Line prefixes, also read back:

- `- ingredient: <memory id> (rc <run config id>)`: one line per
  ingredient of a merge.
- `- rejected at the val gate <MM-DD> vs baseline <run config id> — <reason>`.
  The reason is one of:
  - `passed over: not promoted; rc <run config id> was promoted instead.`
  - `an eval dropped at val: down beyond doubt on eval <eval id>[, <eval id>…].`
  - `no gain at val: no targeted eval improved.`
  - `a gain at val, not clear: a targeted eval improved, but not beyond doubt.`
  - `not promoted at val; details in the run report.`

  Older records end `— did not beat it; details in the run report.`
- `- held at the val gate <MM-DD> on OPEN constraint <id> — not judged on its numbers; resubmit this rc unchanged (existing_rc_id) once answered.`
- `- blocked at the val gate <MM-DD>: <reasons> — the run config copies eval text; remove the copied phrase before you build on it or merge it.`

These lines hold no val number: they are the outcome on val in words.
