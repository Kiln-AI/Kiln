---
status: complete
---

# Implementation Plan: Doc Skills

## Phases

- [x] Phase 1: Data model + Project registration
- [x] Phase 2: Pipeline runner + Skill builder
- [x] Phase 3: API layer
- [x] Phase 4: Frontend — templates, creation form, progress dialog
- [ ] Phase 5: Frontend — list page, detail page, entry point
- [ ] Phase 6: Cross-linking + Clone
- [ ] Phase 7: P2 — Document descriptions
- [ ] Phase 8: P2 — Semantic doc descriptions / chunk summaries

### Phase 1: Data model + Project registration
- `DocumentSkill` model in `libs/core/kiln_ai/datamodel/document_skill.py`
- Register in `Project.parent_of` with typed accessor
- Add `tags` parameter to `RagExtractionStepRunner` and `RagChunkingStepRunner`
- Unit tests for model validation, save/load, tag filtering change

### Phase 2: Pipeline runner + Skill builder
- `DocSkillProgress` model
- `DocSkillWorkflowRunner` in `app/desktop/studio_server/doc_skill_pipeline.py`
- `SkillBuilder` in `app/desktop/studio_server/doc_skill_skill_builder.py` (name sanitization, SKILL.md generation, reference files, rollback)
- Integration tests with fixture documents

### Phase 3: API layer
- `doc_skill_api.py` with all endpoints (CRUD, /run SSE, /progress batch, /doc_skill_source)
- Register in webhost
- API tests

### Phase 4: Frontend — templates, creation form, progress dialog
- Template definitions (`doc_skill_templates.ts`)
- Template selection page
- Creation form with find-or-create
- Progress dialog (SSE)

### Phase 5: Frontend — list page, detail page, entry point
- List page with table and empty state
- Detail page (two-column layout, skill link card, property lists)
- Entry point card on docs page

### Phase 6: Cross-linking + Clone
- DocSkill detail → Skill link (already in detail page, wire up)
- Skill detail → DocSkill banner (call `/doc_skill_source` endpoint)
- Clone flow: `?clone={id}` param on creation form

### Phase 7: P2 — Document descriptions
- Optional description field on Document model
- Display in DocSkill index table

### Phase 8: P2 — Semantic doc descriptions / chunk summaries
- AI-generated descriptions for documents and chunks
- Two-tier index (SKILL.md doc-level + per-document index.md)
