---
status: complete
---

# Implementation Plan: Model Agent Info

## Phases

- [x] Phase 1: Code and tests. The vocabulary module, the provider list,
  the new model and provider-entry fields, `provider_name_from_id` reading
  the provider list, and `serialize_config` writing `provider_list`. All
  new fields empty except the provider list's friendly names and
  `models_dev_id` values. Includes the backward-compatibility test run.
- [x] Phase 2: Skills and guidance. `claude-maintain-models`,
  `kiln-model-sweep`, `kiln-conventions` `core.md`, and whatever else
  `docs-sync` finds.
- [x] Phase 3: Vocabulary v2 (the 2026-11-15 revision). Code, tests and
  skills only; no data. `model_agent_info.py`: `TagKind`, `TagInfo`, the
  new model-tag map with kinds and limits, empty provider-entry and
  provider-list maps, the note label tuples, the new docstring. The new
  data tests (note format, `Superseded by:` if and only if not `current`,
  set limits, `recommended` is `current`, tagged models have notes,
  provider note labels) and the updated vocabulary tests.
  `claude-maintain-models`: the rewritten "Agent notes and tags" section
  with the approved examples word for word, the `current` and set-review
  procedures, the sources rule, the Phase 3 step and the PR section.
  `kiln-model-sweep`: set changes at the top of its PR. Then `docs-sync`
  for anything else that names the old tags.
- [x] Phase 4: Backfill (needs web access; Phases 1 to 3 on the branch).
  Notes in the new format and tags for the selected models, `current` for
  each lab and price level, each set built as one review with Artificial
  Analysis data, provider notes, the `huggingface` `models_dev_id` check,
  and the sources log. Data only. Follow "The backfill" in the functional
  spec and "Backfill design" in the architecture.
