---
status: complete
---

# Phase 4: Backfill

## Overview

Populate agent notes and model tags for selected models, current tags per
lab and price level, set tags across all selected models, provider notes,
and the huggingface models_dev_id. Data only: no code, no tests, no skill
changes.

## Steps

1. Determine the selected models: featured_rank is set, or at least one
   non-deprecated provider entry has a models.dev release date within 12
   months of 2026-11-15. Record the selection in backfill_sources.md.

2. Fetch Artificial Analysis data for key models: intelligence index, output
   speed, TTFT, cost per task. Use this for set decisions and Strengths
   lines.

3. Lab by lab, write agent_notes for each selected model in the note format
   (Description, Lineup, Superseded by if not current, optional Useful for /
   Strengths / Behavior / Deployment). Assign current per lab per price
   level.

4. Build each set as one review across all selected models:
   - recommended (limit 20): current models that are good candidates for
     new agents
   - top_value (14): best quality for cost, using AA intelligence index
     and cost
   - top_fast (14): fastest by output speed and TTFT
   - top_on_device (14): best models that run on consumer hardware
   - top_open (14): best open-weight models
   - top_writing (14): best at prose

5. Write provider notes for every connectable provider (all except
   kiln_fine_tune and kiln_custom_registry).

6. Set huggingface models_dev_id to "huggingface" after confirming the
   models.dev entry matches Kiln's service.

7. Run data tests. Fix any failures.

8. Write backfill_sources.md with per-model sources and per-set membership.

## Tests

- All existing data tests pass (note format, tag rules, set limits,
  current/recommended invariant, superseded-by if and only if not current).
- No new tests in this phase (data-only change).
