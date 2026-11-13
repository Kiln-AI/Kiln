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
- [ ] Phase 2: Skills and guidance. `claude-maintain-models`,
  `kiln-model-sweep`, `kiln-conventions` `core.md`, and whatever else
  `docs-sync` finds.
- [ ] Phase 3: Backfill (standalone; runs on a separate machine with web
  access). Agent notes and tags for the selected models, provider-entry
  speed tags, provider notes, the `huggingface` `models_dev_id` check, and
  the sources log. Data only. Needs Phases 1 and 2 merged or on the branch.
  Follow "The backfill" in the functional spec and "Backfill design" in
  the architecture.
