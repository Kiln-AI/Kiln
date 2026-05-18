---
status: complete
---

# Implementation Plan: Multiturn CSV Upload

## Phases

- [x] **Phase 1 — Backend importer + endpoint.** Add multiturn parsing, validation, and chain construction in `libs/core/kiln_ai/utils/dataset_import.py`; dispatch from `import_csv` on `task.turn_mode`. Introduce `ImportResult` dataclass and update `BulkUploadResponse` in `libs/server/kiln_server/run_api.py` with `imported_conversation_count`. Cover with the unit + endpoint tests listed in `architecture.md` §6.1–6.2. No frontend changes in this phase; backend ships and is testable in isolation.

- [ ] **Phase 2 — Frontend dialog + sample asset.** Regenerate the OpenAPI client (`app/web_ui/src/lib/generate_schema.sh`). Update `upload_dataset_dialog.svelte` with the turn-mode-aware help block, dialog title, and sample-download link. Add `app/web_ui/static/sample_multiturn.csv`. Cover with the Vitest cases in `architecture.md` §6.3.
