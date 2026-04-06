---
status: implementing
---

# Phase 2: Pipeline Runner + Skill Builder

## Overview

This phase builds the core pipeline that converts extracted/chunked documents into agent skills. It includes the `DocSkillWorkflowRunner` (orchestrating extraction, chunking, and skill creation) and the `SkillBuilder` (name sanitization, SKILL.md generation, reference file writing, rollback).

## Steps

1. Create `app/desktop/studio_server/doc_skill_pipeline.py`:
   - `DocSkillProgress(BaseModel)` with extraction/chunking/skill counts and logs
   - `DocSkillWorkflowRunnerConfig` dataclass with doc_skill, project, extractor_config, chunker_config
   - `DocSkillWorkflowRunner` class with `async run() -> AsyncGenerator[DocSkillProgress, None]`
   - Reuses `RagExtractionStepRunner` and `RagChunkingStepRunner` with `tags` parameter
   - Document filtering via `_get_filtered_documents()`
   - Progress update methods mapping step runner progress to DocSkillProgress

2. Create `app/desktop/studio_server/doc_skill_skill_builder.py`:
   - `SkillBuilder` class with `async build() -> ID_TYPE`
   - `_sanitize_name(name) -> str`: lowercase, replace non-alphanumeric with hyphens, collapse, strip
   - `_strip_all_extensions(name) -> str`: remove all extensions from first dot
   - `_resolve_document_names(doc_chunks) -> dict[str, str]`: collision handling with -2, -3 suffixes
   - `_build_skill_md(doc_names, doc_chunks) -> str`: header, instructions, document index table
   - `_get_file_extension() -> str`: md or txt based on extractor output format
   - `_write_reference_files(skill, doc_names, doc_chunks)`: part files with continuation footers
   - `_generate_skill_description(doc_count) -> str`: auto-description for Skill.description
   - `_rollback_skill(skill)`: delete entire skill folder on failure
   - `_collect_document_chunks() -> dict[str, tuple[Document, list[str]]]`: gather chunks per doc

## Tests

### Skill Builder Tests (`app/desktop/studio_server/test_doc_skill_skill_builder.py`)
- `test_sanitize_name_*`: special chars, unicode, empty result → "unnamed", hyphens
- `test_strip_all_extensions_*`: single ext, double ext, no ext, hidden files
- `test_resolve_document_names_*`: collision handling (2 docs, 3+ collisions), name_override, strip extensions
- `test_build_skill_md_*`: correct format, sorted entries, correct part counts, ext variations
- `test_write_reference_files_*`: correct paths, continuation footers, end-of-document marker
- `test_max_parts_validation`: exactly 999 ok, 1000 raises error
- `test_rollback_on_failure`: verify skill folder deleted when build raises
- `test_generate_skill_description_*`: with tags, without tags, long tags truncation
- `test_collect_document_chunks_*`: skips docs without extraction, without chunks, with empty chunks
- `test_build_full_integration`: end-to-end with fixture documents producing complete Skill

### Pipeline Tests (`app/desktop/studio_server/test_doc_skill_pipeline.py`)
- `test_full_pipeline_run`: extraction + chunking + skill creation with mock step runners
- `test_pipeline_tag_filtering`: filtered documents passed correctly
- `test_pipeline_no_documents_error`: raises when no documents match tags
- `test_progress_updates`: extraction/chunking/skill progress yielded correctly
- `test_pipeline_sets_skill_id`: doc_skill.skill_id is set after successful run
