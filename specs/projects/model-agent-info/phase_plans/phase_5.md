---
status: complete
---

# Phase 5: Revision 2 (2026-11-16 Audit)

## Overview

Apply the revision-2 rules from the functional spec: serving variants lose
`current` and get `Same weights:` lines, the `recommended` bar is enforced
with AA data, local-only models are selected for `top_on_device`, and the
sources log uses the per-set comparative format.

## Steps

### Code

1. `model_agent_info.py`: insert `"Same weights:"` into `MODEL_NOTE_LABELS`
   after `"Superseded by:"`.
2. `test_ml_model_list.py`: update `test_superseded_by_iff_not_current` so a
   non-current model with a note may have `Superseded by:` OR
   `Same weights:` (revision 2).
3. `test_model_agent_info.py`: update `test_valid_model_note_all_labels` to
   include the new `Same weights:` label.
4. `claude-maintain-models/SKILL.md`: add serving-variant rules to the
   `current` procedure, add the `recommended` bar, add local-only model
   selection guidance, update the sources-log rule to require per-set AA
   figures with comparative reasons.

### Data — serving variants

5. GLM 5.3 Fast: remove `current`, rewrite note with `Same weights:` line.
6. GLM 5.3: add `Same weights:` line naming GLM 5.3 Fast.
7. Kimi K3 Fast: remove `current`, rewrite note with `Same weights:` line.
8. Kimi K3: add `Same weights:` line naming Kimi K3 Fast.
9. MiMo-V2.6-Pro UltraSpeed: remove `current`, rewrite note with
   `Same weights:` line.
10. MiMo-V2.6-Pro: add `Same weights:` line naming UltraSpeed.

### Data — recommended rebuild

11. Gemini 3.5 Flash Lite: remove `recommended` (AA index 12 at $0.69/task;
    GPT-6 Luna gets index 28 at $0.15/task).
12. Mistral Large 4: remove `recommended` (AA index 26 at $2.06/task;
    GPT-6.1 Terra gets index 51 at $0.96/task).

### Data — set rechecks

13. Gemini 3.5 Flash Lite in `top_value`: keep (genuinely one of the
    cheapest usable models at $0.33/M blended).
14. Gemini 3.5 Flash Lite in `top_fast`: keep (312 tok/s, 4.82s TTFT).
15. Mistral Large 4 in `top_writing`: remove (AA index 26 among models
    with indices 50-65).
16. Serving variants for `top_fast`: none qualify (base models at 48-87
    tok/s; even doubled, below the set's 104-442 tok/s range).
17. `top_open` review: no changes needed.

### Data — local-only models for top_on_device

18. Gemma 4 4B: add notes and tags `["current", "top_on_device"]`.
19. Gemma 4 2B: add notes and tags `["current", "top_on_device"]`.
20. Qwen 3 4B: add notes and tags `["current", "top_on_device"]`.
21. Qwen 3 30B A3B 2507: add notes and tags
    `["current", "top_on_device"]`.

### Sources log

22. Rewrite `backfill_sources.md` with the revision-2 format: per-set
    rows with AA figures, comparative reasons, and AA URLs; per-model
    source URLs.

## Tests

- `test_model_agent_info.py`: existing tests pass with the new label.
- `test_ml_model_list.py`: all data tests pass (note format, superseded
  rule, set limits, recommended-is-current, tagged models have notes).
- Full `checks.sh` passes.
