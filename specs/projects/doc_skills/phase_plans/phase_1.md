---
status: draft
---

# Phase 1: Data Model + Project Registration

## Overview

Create the `DocumentSkill` data model, register it in `Project.parent_of`, and add a `tags` parameter to `RagExtractionStepRunner` and `RagChunkingStepRunner` so they can filter by tags without requiring a full `RagConfig`.

## Steps

1. Create `libs/core/kiln_ai/datamodel/document_skill.py` with the `DocumentSkill` model:
   - Extends `KilnParentedModel`
   - Fields: `name`, `is_archived`, `description`, `skill_name`, `skill_content_header`, `extractor_config_id`, `chunker_config_id`, `document_tags`, `skill_id`, `strip_file_extensions`
   - `@model_validator(mode="after")` for tag validation, skill_name, skill_content_header
   - `parent_project()` convenience method

2. Register in `libs/core/kiln_ai/datamodel/project.py`:
   - Import `DocumentSkill`
   - Add `"document_skills": DocumentSkill` to `parent_of`
   - Add typed accessor `def document_skills(self, readonly: bool = False) -> list["DocumentSkill"]:`

3. Export from `libs/core/kiln_ai/datamodel/__init__.py`:
   - Import `document_skill` module
   - Import `DocumentSkill` class
   - Add to `__all__`

4. Add `tags` parameter to `RagExtractionStepRunner.__init__()` and `RagChunkingStepRunner.__init__()`:
   - New optional `tags: list[str] | None = None` parameter
   - In `collect_jobs`, filter documents by tags (use `filter_documents_by_tags`) when `self.tags` is set, falling back to `self.rag_config.tags` when `rag_config` is provided but `tags` is not explicitly set

## Tests

File: `libs/core/kiln_ai/datamodel/test_document_skill.py`

- `test_document_skill_valid_creation`: All fields set, verify values
- `test_document_skill_minimal_creation`: Only required fields, verify defaults
- `test_document_skill_tag_validation_empty_list`: Empty list raises ValueError
- `test_document_skill_tag_validation_empty_string`: Empty string in list raises ValueError
- `test_document_skill_tag_validation_spaces`: Tag with spaces raises ValueError
- `test_document_skill_tag_validation_valid`: Valid tags accepted, including None
- `test_document_skill_skill_name_validation`: Empty/whitespace-only raises ValueError
- `test_document_skill_skill_content_header_validation`: Empty/whitespace-only raises ValueError
- `test_document_skill_save_load_roundtrip`: Save and load via parent path
- `test_document_skill_parent_project`: Returns correct parent
- `test_document_skill_parent_project_none`: Returns None when no parent
- `test_document_skill_defaults`: skill_id is None, strip_file_extensions is True, is_archived is False
- `test_document_skill_listing_via_project`: project.document_skills() returns correct set

File: `libs/core/kiln_ai/adapters/rag/test_rag_runners_tags.py` (or inline in existing test file)

- `test_extraction_step_runner_tags_parameter`: Verify tags parameter filters documents independently of rag_config
- `test_chunking_step_runner_tags_parameter`: Same for chunking
