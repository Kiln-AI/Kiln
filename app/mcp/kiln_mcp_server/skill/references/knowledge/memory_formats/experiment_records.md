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
  falling pair of numbers is a gain. Inside the Kiln Harness Tuner loop
  that row's shape is frozen in its experiment-analysis skill, which owns
  it.
- **State suffixes** (lifecycle vocabulary — read them), in place of the
  verdict or after it:

| Suffix | What it means |
|---|---|
| ` — RUNNING` | Not measured yet. From a run that has ended, it is abandoned work, not a result |
| ` — REFUTED` | Measured: the change did not help |
| ` — FAILED (infra: <error class>)` | Killed by infra: neither win nor dead end, retryable |
| ` — ABANDONED (<why>)` | Aborted mid-run (tripwire, orchestrator restart): no verdict |
| ` — DEAD END (<why>)` | Ruled out before or during the measurement, for example `(generality: …)` or `(judge copy: …)` |
| ` — NOT LANDED (<detail>)` | A stop rule of the measurement engine ended the candidate before its train split was judged in full, so the rest was not paid for: `<k>/<n> targets fixed` when a named `target_items` item still failed; `<k>/<n> fixed, <b>/<g> guards broke` from the discriminating block (the parent's failures and a few passes, judged first), with the `residual gate:`, `residual still failing:` and `residual guards broke:` content lines naming the items per eval (below); `stopped at n=<n> by <rule>: <numbers>` for any other rule (clearly worse quality, futility, invalid output, not faster or cheaper); or `capped at <n> items: …`. The lever is untested, not disproven (a different build for the same targets is fair game; the same rc is not) |
| ` — CAPPED (<detail>)` | The measurement reached the candidate's spending cap: inconclusive, never a dead end or a failure. The detail is, for example, `capped at $<x> after <n> items: inconclusive — net +<a>/−<b> so far`, under speed or cost `capped at $<x> after <n> items: inconclusive — lost <k> of <n> baseline passes so far`, or `capped by the run budget ($<x> left) after <n> items: …`. The rows are kept, and a later candidate on the same rc with a larger cap goes on from them |

- **No suffix on an opening**: an overview in the opening's shape
  (`EXP <id> (<technique>…`) with no state suffix has lost its state. Its
  code reads it as unknown, never as a verdict.
- **Val stamps**, appended after the verdict, with the date as `MM-DD`:

| Stamp | What it means |
|---|---|
| ` — PROMOTED <MM-DD>` | Appended when the experiment's rc becomes the baseline |
| ` — REJECTED AT VAL <MM-DD>` | The confirmation on val compared the experiment's rc and passed it over. Never removed: the rc is never re-submitted unchanged, though it stays eligible as a merge ingredient; the same design re-enters as a new experiment |
| ` — HELD (constraint <id>) <MM-DD>` | The confirmation on val escalated on that `OPEN: ` record (`references/knowledge/memory_formats/open_questions.md`) instead of judging the numbers. The rc is resubmitted unchanged once the constraint is answered |

## The content

Content fields: hypothesis / lever / run_config ids (code appends
`rc: <id>` and `change: <summary>` the moment the build lands, and
`reused rc: <id>` when the candidate measures a prior run's build) / what
it cost — inside the Kiln Harness Tuner loop that slot is `bundle cost`
(the loop's one spend figure for an experiment — that label, never a bare
"spend"; defined in Kiln Harness Tuner's experiment-analysis skill), and
`spend` everywhere else / result / verdict + why / next.

## The content lines its code reads back

`key: value` lines: `hypothesis`, `predicted effect`, `parent rc`, `eval`,
`issue`, `technique`, `head_to_head_group`, `reused rc`, `wildcard`,
`merge of`, `conflict flags`, `rc`, `change`, `generality`, `judge copy`,
`reference check`. The verdict's content also has the analysis, its table
and `bundle cost: $<n>`. `bundle cost` is the spend of the loop's
measurement; elsewhere the spend is labelled `spend`.

- `generality:` is what the leak check between build and measurement found
  in the prompt or the skills, or why it could not check; `judge copy:` is
  its search for eval text in the build, the same way.
- `reference check:` names a skill or a tool that the build's text uses
  and its run config does not attach. A failure on the items that use that
  name can be the build's breakage, not the lever.
- The residual lines, after a `NOT LANDED` stop on the discriminating
  block: the result, the items still failing and the guards broken, as
  `eval: id, id; eval: id` (or `none`), so that the next plan can read
  those traces and target them with a different build:
  - `residual gate: <summary> (needed <required>; seed <seed>)`
  - `residual still failing: <eval>: <item id>, <item id>; <eval>: <item id>`
  - `residual guards broke: <eval>: <item id>, <item id>; <eval>: <item id>`

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
