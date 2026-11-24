---
name: baseline_and_val_records
description: Read-only - the formats of the baseline record and the val record, which Kiln Harness Tuner's code writes, one of each per task - how to read the current baseline, the promotions and their val summary.
---

# The baseline and val records

Kiln Harness Tuner's code writes both records, one of each per task, and
its code is the authority on their format. They are here so that you can
read them. Never write, edit or delete either one
(`references/knowledge/memory.md`).

## The `baseline` record

- **Tags:** `baseline` and one `rc_<run config id>`, for example
  `["baseline", "rc_424242035642"]`. The id in that tag is the current
  baseline (the prefix is added to the id, never to an already-prefixed
  name). Read it from the tag, never from the prose.
- **Singleton by convention:** PATCHed at every promotion, never
  duplicated.
- **Overview:** free prose, **no format contract**, anyone may rewrite it.
  For example
  `Baseline: run config 424242035642 — promoted 07-15 by EXP 0715-w3-1`,
  or `Baseline: run config <id> — seeded <MM-DD> by kiln-harness-tuner setup (<rule>)`.
- **Content:** the promotion chain — **one rc id per line, newest first**,
  nothing else on the line required — deliberately dumb, because a bad
  parse costs a cache screen and nothing more. The first word of each line
  is the id.
- **It carries NO val metrics**: those numbers live in `val`, so the split
  boundary is a record rather than a substring of an overview.

### How it is written

**Created** on a cold task by the Kiln Harness Tuner setup phase's
pre-flight step: the task's `default_run_config_id` if it has one, else
the most recently created rc, with the rule named in the record's
provenance; zero run configs is an instructive fatal, never a sentinel
baseline. After that only the promotion apply step updates it — moving the
`rc_` tag, prepending the winner to the chain (in the Kiln Harness Tuner
loop both writers are orchestrator code; the loop never sets the
human-facing `default` rc flag, and a newer user-set default never moves
an existing baseline on its own). So the baseline and the task's default
run config can differ.

## The `val` record

- **Tag:** `val`. It is the only record with val numbers. Written by the
  promotion apply step, right after the `baseline` write — created at the
  first promotion, so a freshly seeded task has a `baseline` record and no
  `val` one. A failed write here is logged and skipped: it is reporting,
  and a promotion must not fail on it.
- **Overview**, always the same, with no number:
  `Validation metrics for each baseline promotion (val-grade; the numbers are in content, never here)`,
  so a listing is safe to fetch even when the content is not.
- **Content:** one line per promotion, newest first:
  `<new run config id> (<MM-DD>, <EXP label>) ← <old run config id> — <rationale>`.
  For example `424242213 (07-16, EXP 0716-w4-2) ← 424242207 — +9% mean win rate vs 424242207`.
  The ids have no `rc_` prefix.
- It holds summary numbers only, never an item or a trace. Nothing that
  you read in it goes into a change
  (`references/knowledge/train_val_test.md`).
