---
status: complete
---

# Functional Spec: Doc Skills

## Overview

Doc Skills converts uploaded documents into agent skills. It reuses the existing document infrastructure (upload, manage, extract, chunk) and the existing skill system (SKILL.md + references), bridging them with a new `DocumentSkill` datamodel and creation pipeline.

The result is a skill that agents can use via the existing skill tool — no new tool integration needed. The SKILL.md contains a table-of-contents index of the documents, and each chunk is stored as a reference file the agent can load on demand.

## 1. DocumentSkill Data Model

`DocumentSkill` is a new `KilnParentedModel` under `Project`, analogous to `RagConfig`.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | `FilenameString` | Display name for the doc skill config |
| `is_archived` | `bool` | Default `False`. Archived doc skills hidden from UI |
| `description` | `str \| None` | User-facing description of this config (not used in prompts) |
| `skill_name` | `SkillNameString` | Name of the generated skill (kebab-case) |
| `skill_content_header` | `str` | User-authored text placed at the top of the SKILL.md body, describing what the documents contain and when to use them. Max 16384 chars |
| `extractor_config_id` | `ID_TYPE` | Extractor config used for document extraction |
| `chunker_config_id` | `ID_TYPE` | Chunker config used for chunking |
| `document_tags` | `list[str] \| None` | Document tag filter. `None` = all project documents |
| `skill_id` | `ID_TYPE \| None` | ID of the generated `Skill`. `None` before pipeline completes |
| `strip_file_extensions` | `bool` | Default `True`. Strip file extensions from document names in skill output |

### Validation

- `document_tags`: Same validation as `RagConfig.tags` (non-empty list, no empty strings, no spaces)
- `skill_name`: Must be valid `SkillNameString` (kebab-case)
- `skill_content_header`: Non-empty, max 16384 chars

### Relationships

- Parent: `Project`
- References: `ExtractorConfig`, `ChunkerConfig`, `Skill` (all by ID)
- Shares the same extractor and chunker config pool as RAG

### Immutability

DocumentSkills are immutable after successful pipeline completion (`skill_id` is set). This ensures downstream evals remain consistent. Users cannot edit the config fields or the generated skill.

To "update" a doc skill (e.g., after documents change), users clone it — creating a new DocumentSkill with the same settings that re-runs the pipeline and produces a new Skill with a new ID. See Clone in Section 6.

## 2. Creation Pipeline

The creation pipeline has three steps, executed sequentially with progress feedback via SSE (same pattern as RAG workflow).

### Step 1: Extract Documents

- Filter project documents by `document_tags` (or use all if `None`)
- Run extraction using the referenced `extractor_config_id`
- Skip documents that already have an extraction for this extractor config
- Report progress: `N/M documents extracted`

This is identical to the RAG extraction step. Maximize reuse.

### Step 2: Chunk Documents

- Chunk each extraction using the referenced `chunker_config_id`
- Skip documents that already have chunks for this chunker config
- Report progress: `N/M documents chunked`

This is identical to the RAG chunking step. Maximize reuse.

### Step 3: Create Skill

After extraction and chunking are complete, build the skill:

#### 3a. Determine document names

For each document included:
- Use `name_override` if set, otherwise use `name`
- If `strip_file_extensions` is `True`, remove all file extensions (e.g., `archive.tar.gz` → `archive`)
- Sanitize for filesystem safety (replace path-unsafe characters)
- Handle name collisions by appending a numeric suffix: `doc-name`, `doc-name-2`, `doc-name-3`

#### 3b. Create reference files

For each document, for each chunk:
- Write to: `references/{sanitized_doc_name}/part{N}.md` (or `.txt` based on extractor output format)
- `N` is 1-indexed, zero-padded to 3 (e.g., `part001.md`, `part011.md`, `part111.md`)
- Each file contains the chunk content
- Append a continuation footer to all parts except the last: `\n\n<< Document continues in references/{doc_name}/part{N+1}.md >>`. Last should include `\n\n<End of Document>`

#### 3c. Build SKILL.md

The SKILL.md body contains:
1. The skill name as header: `# Skill: [name]`
2. The content header (from `skill_content_header`)
3. Instructions for accessing the docs
4. A document index table

**Instructions**

```md
## How to Use This Skill

This skill contains reference documents split into numbered parts. To read a document, load its parts using the skill tool's resource parameter:

skill(name="[this-skill-name]", resource="references/[doc-name]/part001.md")

Parts are 1-indexed and zero-padded to 3 digits (part001, part002, ... part999). Start with part001. Each part ends with a pointer to the next part, or `<End of Document>` for the final part.
```

**Document Index Table Format:**

```markdown
## Document Index

|Document|Part Count|Location|
|-|-|-|
|Annual Report 2024|12|`references/annual-report-2024/part[NNN].md`|
|API Guidelines|3|`references/api-guidelines/part[NNN].txt`|
```

One row per document. Sorted alphabetically by sanitized document name.

#### 3d. Save the skill

- Create a `Skill` model with `name=skill_name`, `description` auto-generated (see below)
- Call `save_skill_md(body)` with the generated SKILL.md body
- Write all reference files to the skill's references directory
- Create DocumentSkill and set `DocumentSkill.skill_id` to point to the created skill

**Auto-generated `Skill.description`:** The `Skill.description` field (used for tool discovery, max 1024 chars) is not user-editable on the DocSkill form. It is auto-generated: `"Document skill generated by Kiln from [N] documents"` — or if tags are set: `"Document skill generated by Kiln from documents tagged [tag1, tag2]"`.

#### 3e. Atomic skill creation with rollback

The Skill and its files must be created atomically. If any step in 3a-3d fails:
- Delete the new Skill folder (.kiln file, SKILL.md and reference files)
- Leave the DocumentSkill with `skill_id=None` — it's the config the user created and can be re-run

To minimize failures, validate models before writing to disk. Save the Skill first, then set `DocumentSkill.skill_id`, with proper rollback try/catch.

On failure, the UI shows the error. The user can re-run the pipeline from the detail page (re-triggers `/run` on the same DocumentSkill while `skill_id` is still `None`).

Note: Extraction and chunking outputs (steps 1-2) are shared infrastructure and are NOT rolled back — they're reusable by RAG and future doc skills. Only the DocumentSkill and Skill artifacts are cleaned up.

## 3. Templates

Three templates for the "New Doc Skill" creation flow, similar to RAG templates. Templates configure the extractor and chunker; no embedding/vector store/reranker needed.

| Template | Chunk Type | Chunk Size | Overlap | Extractor |
|----------|-----------|------------|---------|-----------|
| Small Context | Fixed Window | 1000 tokens | 0 | Gemini 2.5 Flash |
| Medium Context | Fixed Window | 2000 tokens | 0 | Gemini 2.5 Flash |
| Large Context | Fixed Window | 3000 tokens | 0 | Gemini 2.5 Flash |

Template structure mirrors RAG templates but is simpler — only `extractor` and `chunker` sub-configs. Each template also includes provider variants (Gemini direct vs OpenRouter fallback).

Doc Skills uses fixed-window chunking only. Semantic chunking is not supported.

## 4. API Endpoints

All endpoints under `/api/projects/{project_id}/doc_skills`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/doc_skills` | Create a DocumentSkill config |
| `GET` | `/doc_skills` | List DocumentSkills (excludes archived) |
| `GET` | `/doc_skills/{doc_skill_id}` | Get a specific DocumentSkill |
| `PATCH` | `/doc_skills/{doc_skill_id}` | Archive/unarchive only (all other fields are immutable). Archiving a DocumentSkill also archives the generated Skill. Unarchiving restores both |
| `GET` | `/doc_skills/{doc_skill_id}/run` | Run the creation pipeline (SSE) |
| `POST` | `/doc_skills/progress` | Get progress for doc skills (batch, same pattern as RAG) |

### Create Request

```
{
  name: string
  skill_name: string
  skill_content_header: string
  description?: string
  extractor_config_id: string
  chunker_config_id: string
  document_tags?: string[]
  strip_file_extensions?: bool  // default true
}
```

### Run Endpoint (SSE)

Returns a `StreamingResponse` with progress events, same pattern as RAG's `/run` endpoint. Uses GET (not POST) because the JS `EventSource` API only supports GET — same convention as RAG.

Locking: same concurrency/locking strategy as RAG's `/run` endpoint (details in architecture spec).

Steps reported:

1. `extracting` — with document count progress
2. `chunking` — with document count progress
3. `creating_skill` — single step, complete/error
4. `complete` — final event with `skill_id`

### Progress Endpoint

Batch endpoint following RAG's `/rag_configs/progress` pattern. Accepts a list of `doc_skill_ids` in the request body (or empty for all in project). Returns a map of doc_skill_id → progress. Computes current extraction/chunking progress from disk.

A DocumentSkill with `skill_id` set is always `"complete"`. The skill creation step (step 3) is fast/local and not tracked by progress — it either succeeds or fails atomically.

## 5. UI Screens

### 5a. Entry Point

On the Docs & Search page (`/docs/[project_id]`), add a "Doc Skills" card/section alongside the existing "Search Tools (RAG)" entry point. Same visual weight and layout pattern.

### 5b. Doc Skills List Page

Route: `/docs/doc_skills/[project_id]`

Heavy inspiration from RAG list page. Shows:
- Table of DocumentSkills with columns: Name, Skill Name, Status (has skill / pending), Created date
- "New Doc Skill" button
- Click row → detail page
- Empty state with explanation of what doc skills are

### 5c. New Doc Skill — Template Selection

Route: `/docs/doc_skills/[project_id]/add_doc_skill`

Same layout pattern as RAG's `add_search_tool` page. Cards for each template with:
- Template name and description
- Provider requirements
- "Use Template" action → creation options page
- custom option (no template)

### 5d. New Doc Skill — Creation Options

Route: `/docs/doc_skills/[project_id]/create_doc_skill`

Similar to RAG's `create_rag_config` page but simpler. Fields:
- **Skill name** (kebab-case input, validated)
- **Skill content header** (textarea, pre-filled with template default — describes what the documents contain)
- **Document tags** (tag selector component, reused from RAG)
- **Extractor** (pre-filled from template, editable)
- **Chunker** (pre-filled from template, editable)
- **Advanced Options** collapsible section:
  - "Remove file extensions" toggle (default on)
- **Create** button

### 5e. Creation Progress

After clicking Create, show a progress dialog (same pattern as RAG's `run_rag_dialog`):
- Step indicators: Extract → Chunk → Create Skill
- Progress counts per step
- Error display with option to retry (Skill artifacts rolled back, DocumentSkill persists with `skill_id=None` for re-run)
- On completion: link to the created doc skill detail page

### 5f. Doc Skill Detail Page

Route: `/docs/doc_skills/[project_id]/[doc_skill_id]/doc_skill`

Design in UI design phase. Key information to display:
- Config details (name, description, extractor, chunker, tags, settings)
- Link to generated Skill (navigates to skill detail page)
- Status indicator
- Archive action

### 5g. Cross-Linking

- **DocSkill detail → Skill**: Link with context "View Generated Skill"
- **Skill detail → DocSkill**: If a skill was created by a DocSkill, show a badge/link: "Created from Documents" that navigates to the DocSkill detail page. This requires the Skill detail page to check if any DocumentSkill references this skill's ID.

## 6. Edge Cases & Error Handling

### No Documents Match Tags

If the tag filter matches zero documents, fail before running the pipeline. Show an error in the UI: "No documents found with the selected tags."

### Empty Extraction

If a document's extraction produces empty content, skip it and continue. Log a warning. If ALL documents produce empty extractions, fail with an error.

### Document Added After Creation

Since DocumentSkills are immutable, new documents added after creation are not included. The user must clone the DocSkill to include them.

### Skill Name Collision

Duplicate skill names are allowed. The "run" UI will ensure only one of each name is selected at a time.

### Extractor/Chunker Config Deleted

If the referenced extractor or chunker config is deleted after the DocumentSkill is created, the DocumentSkill still displays correctly (it stores IDs, the configs may show as "deleted" in the UI). The generated skill is unaffected since it's self-contained files.

### Large Document Sets

No artificial limits on document count. The SSE progress events keep the UI responsive. The pipeline processes documents sequentially per step (same as RAG).

### Max Parts

Error if >999 parts in a single document. This aborts the entire pipeline — no partial skill is created.

### Clone

Add a "Clone" action to the DocSkill detail page. Creates a new DocumentSkill with the same settings, runs the full pipeline again, and produces a new Skill. This is how users "update" a doc skill after document changes or if they want to edit name/description.

## 7. P2 Features

These should be the last stages in the implementation plan. Design for them from from the start, but we may or may not ship them.

### P2: Document Descriptions

The document manager UI gains an optional short description field per document. When present, these appear in the DocSkill's document index table as a description column.

### P2: Semantic Doc Descriptions / Chunk Summaries

AI-generated descriptions for documents and chunks. Two-tier index:
- `SKILL.md` gets doc-level descriptions in the index table
- Per-document `references/{doc_name}/index.md` with chunk-level descriptions

The current design supports this by:
- Using a per-document directory structure (`references/{doc_name}/`)
- Having an extensible index table format
- Keeping SKILL.md body generation as a distinct step that can be enhanced

## 8. Default Content Header

All templates pre-fill `skill_content_header` with the same default (user can edit):

> This skill provides access to reference documents, listed below. Use the document index below to find relevant documents, then load individual parts as needed.
