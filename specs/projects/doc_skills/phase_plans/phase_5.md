---
status: draft
---

# Phase 5: Frontend — list page, detail page, entry point

## Overview

Implements the remaining frontend pages for Doc Skills: the list page with table rows and empty state, the detail page with two-column layout showing config properties and skill link, and the entry point card on the Docs & Search page.

## Steps

1. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/empty_doc_skills_intro.svelte`
   - Reuse `Intro` component pattern from `empty_rag_configs_intro.svelte`
   - Title: "Create a Doc Skill"
   - Description explaining what doc skills do
   - CTA button linking to template selection page

2. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/table_doc_skill_row.svelte`
   - Table row component accepting `doc_skill` and `project_id` props
   - Columns: Details (name bold + gray sub-text with skill name, extractor, chunker, tags), Skill Name, Status
   - Status badge: "Complete" (primary), "Pending" (warning), "Archived" (secondary)
   - Click row navigates to detail page

3. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/+page.ts`
   - `export const prerender = false`

4. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/+page.svelte`
   - List page mirroring RAG list page structure
   - Fetch doc skills via manual fetch to `base_url` (no openapi types)
   - AppPage with breadcrumbs, "New Doc Skill" action button
   - Table with `table_doc_skill_row` components
   - Separate active/archived sections
   - Empty state with `empty_doc_skills_intro`

5. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/[doc_skill_id]/doc_skill/+page.ts`
   - `export const prerender = false`

6. Create `app/web_ui/src/routes/(app)/docs/doc_skills/[project_id]/[doc_skill_id]/doc_skill/+page.svelte`
   - Detail page with two-column layout (mirroring RAG detail page)
   - Left column: Skill Link Card (View Generated Skill link or Run Pipeline button with progress dialog)
   - Right sidebar: PropertyList sections for Configuration, Extractor, Chunker, Documents
   - Header actions: Archive/Unarchive
   - Archived warning banner
   - Fetch doc skill, extractor configs, chunker configs via API

7. Modify `app/web_ui/src/routes/(app)/docs/[project_id]/+page.svelte`
   - Add "Doc Skills" card to the MultiIntro grid as a third entry
   - Include appropriate icon (use file.svg as doc+skill combo icon)

## Tests

- No new component tests for this phase — the pages are primarily composition of existing components (AppPage, PropertyList, Intro, etc.) with data fetching. The template/form tests were written in Phase 4.
