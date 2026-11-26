---
status: complete
---

# Phase 3: Vocabulary v2 (the 2026-11-15 revision)

## Overview

Replace the Phase 1 tag vocabulary (best_value, strong_*, verbose, fast,
very_fast) with the 2026-11-15 revision: TagKind, TagInfo, the seven model
tags with kinds and limits, empty provider-entry and provider-list maps,
and the note label tuples. Update all tests and rewrite the "Agent notes
and tags" section of claude-maintain-models with the approved examples,
the current and set-review procedures, and the sources rule. Add set-change
PR guidance to kiln-model-sweep. No data changes.

## Steps

1. **model_agent_info.py** — replace the module.
   - Add `TagKind(str, Enum)` with `lineage` and `set`.
   - Add `TagInfo` frozen dataclass: `meaning: str`, `kind: TagKind`,
     `max_models: int | None`.
   - Replace `MODEL_TAGS` from `Mapping[str, str]` to
     `Mapping[str, TagInfo]` with the seven tags from the spec, meanings
     word for word.
   - Replace `PROVIDER_ENTRY_TAGS` with an empty `Mapping[str, TagInfo]`.
   - Replace `PROVIDER_LIST_TAGS` with an empty `Mapping[str, TagInfo]`.
   - Add `MODEL_NOTE_LABELS` and `PROVIDER_NOTE_LABELS` tuples.
   - Rewrite the module docstring per the architecture.

2. **test_model_agent_info.py** — update tests.
   - Update `assert_valid_tags` signature: `allowed: Mapping[str, TagInfo]`.
   - Update `test_tag_map_entries_are_well_formed` to check `meaning` on
     `TagInfo`.
   - Replace `test_starting_tags` with the new seven model tags,
     empty provider-entry and provider-list maps.
   - Add `test_model_tag_map_has_one_lineage_tag`: exactly one lineage tag
     (`current`) with `max_models is None`; every set tag has
     `max_models >= 1`.
   - Add `test_no_tag_in_all_three_maps`: no tag appears in more than one
     map.
   - Add `test_note_labels_well_formed`: no duplicates, each ends with `:`.
   - Add `assert_note_format(note, labels, required)` helper.
   - Update parametrized valid/invalid tag tests for TagInfo.

3. **test_ml_model_list.py** — add data tests.
   - Import new symbols (`MODEL_NOTE_LABELS`, `TagKind`).
   - Add `test_model_note_format`: parametrized over models with notes,
     calls `assert_note_format`.
   - Add `test_superseded_by_iff_not_current`: model has `Superseded by:`
     line if and only if not tagged `current`.
   - Add `test_set_tag_limits`: parametrized over set tags, count across
     `built_in_models`, assert <= `max_models`.
   - Add `test_recommended_is_current`: every model with `recommended` also
     has `current`.
   - Add `test_tagged_models_have_notes`: every model with any tag has
     `agent_notes`.

4. **test_ml_provider_list.py** — add provider note format test.
   - Import `PROVIDER_NOTE_LABELS` and `assert_note_format`.
   - In `test_provider_info_follows_rules`, call `assert_note_format` on
     notes that are not None, with `PROVIDER_NOTE_LABELS` and no required
     labels.

5. **claude-maintain-models SKILL.md** — rewrite "Agent notes and tags".
   - Rewrite the section per the architecture's detailed outline: purpose,
     note format table, "never in a note" list, words relative to time rule,
     approved examples word for word, provider note format, tag kinds, the
     current procedure, the set-review procedure, sources rule, how to add
     a tag.
   - Update Phase 3 subsection (3g) to include current procedure and
     set-review procedure for each new model.
   - Add PR description rule: when any set changed, a section at the top
     lists each addition and removal per set with a short reason.

6. **kiln-model-sweep SKILL.md** — add set-change PR rule.
   - In the PR body section or the pre-answered gates, add that when a set
     changed, the PR description puts set changes at the top.

7. **docs-sync** — search for references to the old tags or old
   model_agent_info shape and fix any stale statements.

## Tests

- test_model_agent_info.py: tag map keys match pattern, meanings non-blank,
  exactly one lineage tag, set tags have limits, starting tags match spec,
  note labels well formed, assert_note_format helper.
- test_ml_model_list.py: note format, superseded-by rule, set limits,
  recommended-is-current, tagged-models-have-notes.
- test_ml_provider_list.py: provider note format.
- All existing tests still pass.
