---
status: draft
---

# Architecture: Doc Skills

## Overview

Doc Skills bridges the existing document infrastructure (upload, extract, chunk) with the skill system (SKILL.md + references) through a new `DocumentSkill` model and creation pipeline. The architecture maximizes reuse of existing RAG pipeline components while adding a new skill-building step.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Frontend (Svelte)                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────┐  │
│  │ Template      │ │ Create Form  │ │ List / Detail   │  │
│  │ Selection     │ │ + Progress   │ │ Pages           │  │
│  └──────┬───────┘ └──────┬───────┘ └────────┬────────┘  │
│         │                │                   │           │
│         └────────────────┼───────────────────┘           │
│                          │ REST + SSE                    │
├──────────────────────────┼──────────────────────────────┤
│ API Layer (FastAPI)      │                               │
│  ┌───────────────────────┴────────────────────────────┐  │
│  │ doc_skill_api.py                                   │  │
│  │ CRUD + /run (SSE) + /progress                      │  │
│  └───────────────────────┬────────────────────────────┘  │
│                          │                               │
├──────────────────────────┼──────────────────────────────┤
│ Pipeline (App)           │                               │
│  ┌───────────────────────┴────────────────────────────┐  │
│  │ DocSkillWorkflowRunner                             │  │
│  │  ├─ RagExtractionStepRunner (reused from core)     │  │
│  │  ├─ RagChunkingStepRunner (reused from core)       │  │
│  │  └─ SkillBuildStep (new)                           │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
├──────────────────────────────────────────────────────────┤
│ Data Layer (Core)                                        │
│  ┌──────────────┐ ┌──────────┐ ┌────────────────────┐   │
│  │ DocumentSkill│ │ Skill    │ │ Document/Extraction │   │
│  │ (new model)  │ │ (exists) │ │ /Chunk (exists)     │   │
│  └──────────────┘ └──────────┘ └────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

## Component Breakdown

### Component 1: Data Model (`DocumentSkill`)

New `KilnParentedModel` registered in `Project.parent_of`. Includes validation and tag handling.

→ Detailed design in [components/data_model.md](components/data_model.md)

### Component 2: Pipeline Runner

`DocSkillWorkflowRunner` orchestrating extraction → chunking → skill building. Reuses `RagExtractionStepRunner` and `RagChunkingStepRunner` from core. New `SkillBuildStep` handles name sanitization, reference file creation, SKILL.md generation, and atomic save with rollback. Lives in `app/desktop/studio_server/` (not libs/core).

→ Detailed design in [components/pipeline.md](components/pipeline.md)

### Component 3: API Layer

FastAPI endpoints for CRUD, SSE `/run`, and `/progress`. Lives in `app/desktop/studio_server/doc_skill_api.py`.

→ Detailed design in [components/api.md](components/api.md)

### Component 4: Frontend

Template selection, creation form, progress dialog, list page, and detail page. Heavy reuse of RAG page patterns and shared components (tag selector, progress dialog).

→ Detailed design in [components/frontend.md](components/frontend.md)

## Cross-Cutting Concerns

### Locking Strategy

Same lock manager (`shared_async_lock_manager`) and pattern as RAG:

| Lock | Key | Scope |
|------|-----|-------|
| Pipeline run | `doc_skill:run:{doc_skill.id}` | Prevents concurrent runs of same DocumentSkill |
| Extraction | `docs:extract:{extractor_config.id}` | Shared with RAG — same extractor lock |
| Chunking | `docs:chunk:{chunker_config.id}` | Shared with RAG — same chunker lock |

Timeout: 1 hour (`LOCK_TIMEOUT_SECONDS`), same as RAG. Extraction and chunking locks are shared because the configs are shared — a RAG run and a DocSkill run using the same extractor will correctly serialize.

### Error Handling Strategy

Three tiers:

1. **Validation errors** (before pipeline runs): Synchronous. Return HTTP 422 with error message. Examples: no documents match tags, skill name validation fails, >999 chunks in a document.

2. **Pipeline errors** (during extraction/chunking): Handled by existing step runners. Per-document errors are collected via `GenericErrorCollector` and flushed to SSE logs. Pipeline continues past individual document failures. Fatal if ALL documents fail.

3. **Skill creation errors** (step 3): Trigger rollback — delete Skill folder if created. DocumentSkill remains with `skill_id=None`. Error reported via SSE as final event.

### Archive Cascade

When a DocumentSkill is archived via PATCH:
1. Set `doc_skill.is_archived = True`, save
2. If `doc_skill.skill_id` is set, load the Skill, set `skill.is_archived = True`, save

Unarchive reverses both. This is a simple sequential operation in the PATCH handler — no transaction needed since both saves are independent and idempotent.

### Shared Config Pool

Extractor and chunker configs are shared with RAG. No new config types needed. The find-or-create pattern in templates works identically — templates create configs via the existing `/create_extractor_config` and `/create_chunker_config` endpoints.

### Chunking

Doc Skills uses fixed-window chunking only. Semantic chunking is not supported — the complexity (embedding model selection, variable part sizes) doesn't fit this use case.

### Testing Strategy

| Layer | Approach | Framework |
|-------|----------|-----------|
| Data model | Unit tests for validation, save/load round-trip | pytest |
| Pipeline runner | Integration tests with fixture documents | pytest + async |
| Skill builder | Unit tests for name sanitization, SKILL.md generation, reference file creation, rollback | pytest |
| API endpoints | Integration tests via FastAPI test client | pytest + httpx |
| Frontend | Component tests for forms, template selection; E2E for creation flow | Playwright/Vitest as per existing patterns |

Key test scenarios:
- Name sanitization edge cases (special chars, collisions, extension stripping)
- SKILL.md generation with various document counts
- Rollback on skill creation failure (verify no orphan files)
- Archive cascade (both directions)
- Progress computation for in-progress and complete states
- Concurrent run attempts (verify locking)
- Template find-or-create with existing vs missing configs

## Implementation Notes

### Files to Modify (Existing)

| File | Change |
|------|--------|
| `libs/core/kiln_ai/datamodel/project.py` | Add `"document_skills": DocumentSkill` to `parent_of`, add typed accessor |
| `libs/core/kiln_ai/adapters/rag/rag_runners.py` | Add optional `tags: list[str] \| None` parameter to `RagExtractionStepRunner` and `RagChunkingStepRunner` constructors for tag filtering without a `RagConfig` |
| `app/web_ui/src/routes/(app)/docs/[project_id]/+page.svelte` | Add Doc Skills entry point card |

### New Files

| File | Purpose |
|------|---------|
| `libs/core/kiln_ai/datamodel/document_skill.py` | `DocumentSkill` model |
| `app/desktop/studio_server/doc_skill_api.py` | API endpoints |
| `app/desktop/studio_server/doc_skill_pipeline.py` | `DocSkillWorkflowRunner`, `SkillBuildStep`, progress model |
| `app/desktop/studio_server/doc_skill_skill_builder.py` | Name sanitization, SKILL.md generation, reference file writing, rollback |
| `app/web_ui/src/routes/(app)/docs/doc_skills/` | Frontend pages |

### Component Design Decision

This project has four distinct areas with enough internal complexity to warrant separate component docs:
1. **Data model** — model definition, project registration, validation
2. **Pipeline** — workflow runner, skill builder, name sanitization, rollback
3. **API** — endpoints, request/response models, SSE streaming, progress
4. **Frontend** — templates, pages, components, routing
