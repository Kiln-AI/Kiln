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
  baseline. Read it from the tag, never from the prose.
- **Overview:** prose, with no fixed format. For example
  `Baseline: run config 424242035642 — promoted 07-15 by EXP 0715-w3-1`,
  or `Baseline: run config <id> — seeded <MM-DD> by kiln-harness-tuner setup (<rule>)`.
- **Content:** the promotions, one run config id per line, newest first.
  The first word of each line is the id.
- It holds no val number.

## The `val` record

- **Tag:** `val`. It is the only record with val numbers. It is created at
  the first promotion, so a task can have a `baseline` record and no `val`
  record.
- **Overview**, always the same, with no number:
  `Validation metrics for each baseline promotion (val-grade; the numbers are in content, never here)`.
- **Content:** one line per promotion, newest first:
  `<new run config id> (<MM-DD>, <EXP label>) ← <old run config id> — <rationale>`.
  For example `424242213 (07-16, EXP 0716-w4-2) ← 424242207 — +9% mean win rate vs 424242207`.
  The ids have no `rc_` prefix.
- It holds summary numbers only, never an item or a trace. Nothing that
  you read in it goes into a change
  (`references/knowledge/train_val_test.md`).
