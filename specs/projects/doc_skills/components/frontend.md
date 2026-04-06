---
status: draft
---

# Component: Frontend

## File Locations

All under `app/web_ui/src/routes/(app)/docs/doc_skills/`.

```
doc_skills/
  [project_id]/
    +page.svelte                         # Doc Skills list page
    +page.ts                             # Page load
    add_doc_skill/
      +page.svelte                       # Template selection
      +page.ts
      doc_skill_templates.ts             # Template definitions + find-or-create
    create_doc_skill/
      +page.svelte                       # Creation options form
      +page.ts
      create_doc_skill_form.svelte       # Main form component
    [doc_skill_id]/
      doc_skill/
        +page.svelte                     # Detail page
        +page.ts
    run_doc_skill_dialog.svelte          # SSE progress dialog (shared)
    table_doc_skill_row.svelte           # List row component
    empty_doc_skills_intro.svelte        # Empty state
```

## Template Definitions

File: `doc_skill_templates.ts`

### Template Type

```typescript
type DocSkillChunkerSubConfig = {
  config_name: string
  description: string
  chunk_size: number
  chunk_overlap: number
}

type DocSkillTemplate = {
  name: string
  preview_description: string
  preview_subtitle: string
  preview_tooltip?: string
  required_provider: RequiredProvider
  required_models?: string[]
  required_commands?: string[]
  extractor: ExtractorSubConfig         // Reuse from RAG template types
  chunker: DocSkillChunkerSubConfig
  doc_skill_name: string
  notice_text?: string
  notice_tooltip?: string
}
```

### Template Definitions

```typescript
const doc_skill_templates: Record<string, DocSkillTemplate> = {
  small_context: {
    name: "Small Context",
    preview_subtitle: "~1000 tokens per part",
    preview_description: "Small parts for focused retrieval. Good for structured documents.",
    required_provider: "GeminiOrOpenRouter",
    extractor: gemini_2_5_flash_extractor,  // Reuse from RAG
    chunker: {
      config_name: "Fixed Window 1000 - No Overlap",
      description: "Size: 1000, Overlap: 0",
      chunker_type: "fixed_window",
      chunk_size: 1000,
      chunk_overlap: 0,
    },
    doc_skill_name: "Small Context - Gemini Flash",
  },
  medium_context: {
    name: "Medium Context",
    preview_subtitle: "~2000 tokens per part",
    preview_description: "Balanced parts for general use.",
    required_provider: "GeminiOrOpenRouter",
    extractor: gemini_2_5_flash_extractor,
    chunker: {
      config_name: "Fixed Window 2000 - No Overlap",
      description: "Size: 2000, Overlap: 0",
      chunker_type: "fixed_window",
      chunk_size: 2000,
      chunk_overlap: 0,
    },
    doc_skill_name: "Medium Context - Gemini Flash",
  },
  large_context: {
    name: "Large Context",
    preview_subtitle: "~3000 tokens per part",
    preview_description: "Large parts for maximum context per retrieval.",
    required_provider: "GeminiOrOpenRouter",
    extractor: gemini_2_5_flash_extractor,
    chunker: {
      config_name: "Fixed Window 3000 - No Overlap",
      description: "Size: 3000, Overlap: 0",
      chunker_type: "fixed_window",
      chunk_size: 3000,
      chunk_overlap: 0,
    },
    doc_skill_name: "Large Context - Gemini Flash",
  },
}
```

### Find-or-Create Function

```typescript
async function build_doc_skill_sub_configs(
  template: DocSkillTemplate,
  project_id: string,
  extractor_configs: ExtractorConfig[],
  chunker_configs: ChunkerConfig[],
): Promise<{
  extractor_config_id: string
  chunker_config_id: string
}> {
  // Same find-or-create pattern as RAG's build_rag_config_sub_configs
  // but only for extractor + chunker (fixed window only)

  // 1. Find or create extractor config (identical to RAG)
  // 2. Find or create chunker config (fixed window with chunk_size and chunk_overlap)
  // 3. Return IDs
}
```

## Page Components

### List Page (`+page.svelte`)

Mirrors RAG list page structure:
- Page header with "New Doc Skill" button
- Table with `table_doc_skill_row` components
- Empty state component when no doc skills
- Fetch doc skills via `GET /api/projects/{project_id}/doc_skills`

### Template Selection (`add_doc_skill/+page.svelte`)

Mirrors RAG's `add_search_tool` page:
- Grid of template cards
- Each card shows: name, subtitle, description, provider requirements
- "Custom" option at the end (navigates to create form with no pre-fill)
- Click template → navigate to `create_doc_skill?template={key}`

### Creation Form (`create_doc_skill/+page.svelte`)

Read template key from URL params. Pre-fill form from template.

Form fields:
1. **Skill name** — text input with kebab-case validation
2. **Skill content header** — textarea, pre-filled with default content header
3. **Document tags** — reuse `tag_selector.svelte` from RAG
4. **Extractor** — dropdown/display, pre-filled from template
5. **Chunker** — dropdown/display, pre-filled from template
6. **Advanced Options** — collapsible:
   - "Remove file extensions" toggle (default on)

**Submit flow:**
1. Call `build_doc_skill_sub_configs()` to find-or-create configs
2. POST to `/doc_skills` with the config IDs
3. On success, open `run_doc_skill_dialog` with the new doc skill ID
4. Dialog calls GET `/doc_skills/{id}/run` for SSE

### Progress Dialog (`run_doc_skill_dialog.svelte`)

Reusable dialog component, mirrors `run_rag_dialog.svelte`:
- Three step indicators: Extract → Chunk → Create Skill
- Progress bar/counts for extract and chunk steps
- Skill creation step shows spinner then checkmark
- Error state: show error message, "Try Again" button (re-triggers `/run`)
- Success state: "View Doc Skill" link to detail page

SSE event handling:
- Parse `data: {...}` events as `DocSkillProgress`
- Update step indicators based on counts
- `data: complete` → show success state

### Detail Page (`[doc_skill_id]/doc_skill/+page.svelte`)

Mirrors RAG detail page structure. Shows:
- **Header**: Doc skill name, archive button
- **Config section**: Extractor name, chunker type/size, document tags, file extension setting
- **Skill link**: "View Generated Skill →" button/link (if `skill_id` set)
- **Status**: "Complete" badge or "Pending" with "Run" button
- **Clone button**: Navigates to create form with `?clone={doc_skill_id}` URL param. Form fetches source DocSkill via GET and pre-fills all fields. User can edit before submitting — standard POST + run flow.

### Entry Point Modification

In `app/web_ui/src/routes/(app)/docs/[project_id]/+page.svelte`:
- Add a "Doc Skills" card alongside the existing "Search Tools (RAG)" card
- Same visual style and layout
- Links to `/docs/doc_skills/[project_id]`

### Cross-Linking

**DocSkill detail → Skill:** Link component with text "View Generated Skill" navigating to skill detail page.

**Skill detail → DocSkill:** On the existing skill detail page, call the backend endpoint to check if the skill was created by a DocSkill:
```typescript
// On skill detail page load
const { data } = await client.GET(
  "/api/projects/{project_id}/skills/{skill_id}/doc_skill_source"
)
// If data.doc_skill_id is set, render "Created from Documents" badge with link
```
This check runs in the backend (iterates all doc skills including archived), so archived DocSkills still show the link correctly.

## Tests

### Component Tests (Vitest)
- Template definitions: all templates have required fields
- `build_doc_skill_sub_configs`: mock API calls, verify find-or-create logic
- Form validation: skill name format, required fields

### E2E Tests (if applicable, follow existing patterns)
- Full creation flow: template → form → progress → detail page
- Archive/unarchive from detail page
- Clone flow
- Empty state display
