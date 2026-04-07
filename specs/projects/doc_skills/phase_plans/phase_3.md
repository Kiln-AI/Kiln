---
status: draft
---

# Phase 3: API Layer

## Overview

Implements all FastAPI endpoints for DocumentSkill CRUD, SSE pipeline execution, batch progress, and cross-linking source lookup. Registers the API in the desktop server. Follows the same patterns used by the existing skill_api.py and document_api.py (RAG SSE).

## Steps

1. Create `app/desktop/studio_server/doc_skill_api.py` with:
   - Request/response models: `CreateDocSkillRequest`, `UpdateDocSkillRequest`, `DocSkillResponse`, `DocSkillProgressRequest`, `DocSkillSourceResponse`
   - `connect_doc_skill_api(app)` registering all endpoints
   - `POST /api/projects/{project_id}/doc_skills` — create
   - `GET /api/projects/{project_id}/doc_skills` — list (excludes archived)
   - `GET /api/projects/{project_id}/doc_skills/{doc_skill_id}` — get single
   - `PATCH /api/projects/{project_id}/doc_skills/{doc_skill_id}` — archive/unarchive with cascade to Skill
   - `GET /api/projects/{project_id}/doc_skills/{doc_skill_id}/run` — SSE pipeline execution
   - `POST /api/projects/{project_id}/doc_skills/progress` — batch progress
   - `GET /api/projects/{project_id}/skills/{skill_id}/doc_skill_source` — cross-linking

2. Implement `run_doc_skill_workflow_with_status()` SSE wrapper following the RAG pattern from `document_api.py`

3. Implement `compute_doc_skill_progress()` for batch progress from disk state

4. Implement helper functions: `_get_doc_skill`, `_to_response`, `_build_workflow_runner`, `_get_filtered_documents`

5. Register in `app/desktop/desktop_server.py`:
   - Import `connect_doc_skill_api`
   - Call `connect_doc_skill_api(app)` before `connect_webhost`

6. Create `app/desktop/studio_server/test_doc_skill_api.py` with comprehensive tests

## Tests

- `TestCreateDocSkill::test_create_success` — valid request returns correct response
- `TestCreateDocSkill::test_create_missing_required_fields` — 422 on missing fields
- `TestCreateDocSkill::test_create_invalid_skill_name` — 422 on bad kebab-case
- `TestListDocSkills::test_list_empty` — empty list
- `TestListDocSkills::test_list_excludes_archived` — archived items not returned
- `TestListDocSkills::test_list_returns_fields` — correct field mapping
- `TestGetDocSkill::test_get_found` — returns correct doc skill
- `TestGetDocSkill::test_get_not_found` — 404
- `TestUpdateDocSkill::test_archive` — sets is_archived, cascades to Skill
- `TestUpdateDocSkill::test_unarchive` — restores both
- `TestUpdateDocSkill::test_not_found` — 404
- `TestRunDocSkill::test_already_built` — 422 when skill_id set
- `TestRunDocSkill::test_archived` — 422 when archived
- `TestRunDocSkill::test_extractor_not_found` — 422 on missing config
- `TestRunDocSkill::test_chunker_not_found` — 422 on missing config
- `TestProgressDocSkill::test_complete_state` — returns complete progress
- `TestProgressDocSkill::test_specific_ids` — filters to requested IDs
- `TestProgressDocSkill::test_all_in_project` — returns all when no IDs specified
- `TestDocSkillSource::test_with_source` — returns doc_skill info
- `TestDocSkillSource::test_without_source` — returns nulls
