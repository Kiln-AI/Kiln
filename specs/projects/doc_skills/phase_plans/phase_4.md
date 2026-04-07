---
status: draft
---

# Phase 4: Frontend — templates, creation form, progress dialog

## Overview

Implements the frontend components for creating Doc Skills: template definitions with find-or-create logic, the template selection page, the creation options form, and the SSE progress dialog. These are the first frontend files for Doc Skills and establish the patterns for the remaining frontend phases.

Since the openapi schema hasn't been regenerated with the doc_skill API endpoints, we'll use manual fetch calls with the base_url pattern (similar to the SSE EventSource pattern already used by RAG progress store) for the doc skill-specific endpoints.

## Steps

1. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/add_doc_skill/doc_skill_templates.ts`
   - Define `DocSkillTemplate` type with `name`, `preview_description`, `preview_subtitle`, `required_provider`, `extractor` (reuse `ExtractorSubConfig` pattern), `chunker` (with `config_name`, `description`, `chunk_size`, `chunk_overlap`), `doc_skill_name`
   - Define three templates: `small_context` (1000 tokens), `medium_context` (2000 tokens), `large_context` (3000 tokens)
   - Implement `build_doc_skill_sub_configs()` function — find-or-create extractor and chunker configs, reusing the RAG template's `create_default_extractor_config` and `create_default_chunker_config` helper patterns but extracting them from rag_config_templates.ts
   - Export `DEFAULT_CONTENT_HEADER` constant

2. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/add_doc_skill/+page.ts`
   - `export const prerender = false`

3. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/add_doc_skill/+page.svelte`
   - Mirror RAG's `add_search_tool/+page.svelte` pattern
   - Template cards via `FeatureCarousel`
   - Custom option via `KilnSection`
   - API key check dialogs (Gemini/OpenRouter)
   - Breadcrumbs: Optimize > Docs & Search > Doc Skills > Add Doc Skill

4. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/create_doc_skill/+page.ts`
   - `export const prerender = false`

5. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/create_doc_skill/+page.svelte`
   - Read template key from URL params
   - Render `CreateDocSkillForm` component
   - AppPage with breadcrumbs

6. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/create_doc_skill/create_doc_skill_form.svelte`
   - Form fields: skill_name (kebab-case with `skill_name_validator`), name (display name), skill_content_header (textarea), document tags (reuse `TagSelector`), extractor/chunker config dropdowns (with create dialogs, reuse from RAG)
   - Advanced options collapse: strip_file_extensions toggle
   - Template mode: show `TemplatePropertyOverview` with customize option
   - On submit: find-or-create configs, POST to create doc skill, open progress dialog
   - Uses manual fetch to `base_url` for the doc skill POST endpoint

7. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/run_doc_skill_dialog.svelte`
   - SSE progress dialog, similar to `run_rag_dialog.svelte` but simpler (3 steps instead of 4)
   - Steps: Extract documents, Chunk documents, Create skill
   - Uses EventSource to `GET /doc_skills/{id}/run`
   - Parses progress events with extraction/chunking counts
   - Error state with retry button
   - Success state with link to detail page
   - Log display with copy/download

## Tests

- `doc_skill_templates.test.ts`: All templates have required fields, DEFAULT_CONTENT_HEADER is non-empty
- `create_doc_skill_form.test.ts`: Form validation for skill name format, required fields
