---
status: complete
---

# UI Design: Doc Skills

All pages follow existing design patterns established by the RAG/Search Tools UI. This document focuses on the specific layout and content of each page, highlighting differences from RAG where applicable.

## Entry Point

**Location:** Docs & Search page (`/docs/[project_id]`)

Add a third card to the existing `MultiIntro` grid alongside "Document Library" and "Search Tools (RAG)":

- **Title:** "Doc Skills"
- **Description:** "Convert your documents into agent skills. Agents can browse and read your documents on demand."
- **Action:** "Manage Doc Skills" button → `/docs/doc_skills/[project_id]`
- **Icon:** Appropriate icon (document + skill/star combo)

Same visual weight and card style as the existing two cards.

## List Page

**Route:** `/docs/doc_skills/[project_id]`

### Empty State

Centered `Intro` component (same pattern as `empty_rag_configs_intro.svelte`):
- **Title:** "Create a Doc Skill"
- **Description:** "Doc Skills turn your uploaded documents into skills that agents can browse and read. Upload documents in the Document Library, then create a Doc Skill to make them accessible to your agents."
- **Action:** "Create Doc Skill" button → template selection page

### Populated State

`AppPage` wrapper with breadcrumbs and "New Doc Skill" action button.

**Table columns:**

| Column | Content |
|--------|---------|
| Details | **Name** (bold), then gray sub-text: skill name, extractor name, chunker description, document tags as badges |
| Skill Name | Kebab-case skill name |
| Status | Status badge: "Complete" (green) / "Pending" (yellow) / "Running" (blue with progress) |

- Click row → detail page
- Archived section below active, collapsed by default (same as RAG)
- Status column uses progress from batch `/progress` endpoint for running items

## Template Selection

**Route:** `/docs/doc_skills/[project_id]/add_doc_skill`

Same layout as RAG's `add_search_tool` page. Grid of template cards:

| Template | Subtitle | Description |
|----------|----------|-------------|
| Small Context | ~1000 tokens per part | Small parts for focused retrieval. Good for structured documents. |
| Medium Context | ~2000 tokens per part | Balanced parts for general use. |
| Large Context | ~3000 tokens per part | Large parts for maximum context per retrieval. |

Plus a "Custom" card at the end for users who want to configure everything manually.

Each card shows provider requirements (Gemini or OpenRouter). Click → creation form with template pre-filled.

## Creation Form

**Route:** `/docs/doc_skills/[project_id]/create_doc_skill`

Receives template key (or `clone` ID) via URL params. Single-column form.

**Form fields (top to bottom):**

1. **Skill Name** — text input with kebab-case validation. Label: "Skill Name". Helper text: "Kebab-case name used by agents to load this skill (e.g., company-docs)."
2. **Skill Description** — textarea, optional. Label: "A description of when an agent should use this skill." Tooltip: "This is shown to the agent to help it decide when to load the skill. Keep it concise but informative."
3. **Document Tags** — tag selector (reuse from RAG). Label: "Document Tags". Helper text: "Filter documents by tag. Leave empty to include all documents."
4. **Skill Body Intro** — textarea (4-6 rows). Label: "Skill Body Intro". Helper text: "A longer description of this skill which will be inserted into the SKILL.md file". Pre-filled with default content header.
5. **Extractor** — dropdown/property display showing extractor config. Pre-filled from template.
6. **Chunker** — dropdown/property display showing chunk size. Pre-filled from template.
7. **Advanced Options** — collapsible section:
   - "Custom Document Skill Name" — text input, optional. Helper text: "A display name for this document skill". Tooltip: "Reference name for you and your team, not used by the agent."
   - "Remove file extensions from document names" — toggle, default on

**Submit button:** "Create Doc Skill"

**Clone flow:** When `?clone={id}` is present, fetch the source DocSkill and pre-fill all fields. User can edit before submitting.

**On submit:**
1. Find-or-create extractor/chunker configs
2. POST to create DocumentSkill
3. Open progress dialog with the new doc skill ID

## Progress Dialog

Modal dialog (same pattern as `run_rag_dialog.svelte`).

**Layout:**
- **Step indicators** (vertical list, top to bottom):
  1. "Extracting documents" — spinner → checkmark, with `N/M documents` count
  2. "Chunking documents" — spinner → checkmark, with `N/M documents` count  
  3. "Creating skill" — spinner → checkmark (fast, no count)

- **Error state:** Red error message. "Try Again" button (re-triggers `/run`).
- **Success state:** Green checkmark. "View Doc Skill" link to detail page.

SSE events update step indicators in real-time. The `data: complete` event triggers success state.

## Detail Page

**Route:** `/docs/doc_skills/[project_id]/[doc_skill_id]/doc_skill`

Two-column layout (same pattern as RAG detail page).

### Header

`AppPage` with breadcrumbs. Header actions:
- **Clone** button → navigates to creation form with `?clone={id}`
- **Archive** / **Unarchive** button

### Left Column (main content)

**Skill Link Card** (prominent, top of main content):
- If `skill_id` is set: Card with "Generated Skill" heading, skill name, and "View Skill →" link button
- If `skill_id` is null: Card with "Pending" status, "Run Pipeline" button to trigger `/run` and open progress dialog

### Right Sidebar (fixed width, same as RAG)

Stacked `PropertyList` sections:

**Configuration**
| Property | Value |
|----------|-------|
| Name | Display name |
| Skill Name | Kebab-case name |
| Description | Config description (if set) |

**Extractor**
| Property | Value |
|----------|-------|
| Extractor | Config name |
| Model | Provider + model name |
| Output Format | Markdown / Text |

**Chunker**
| Property | Value |
|----------|-------|
| Chunker | Config name |
| Chunk Size | N tokens |

**Documents**
| Property | Value |
|----------|-------|
| Tags | Tag badges (or "All documents") |
| Strip Extensions | Yes / No |

## Cross-Linking

### DocSkill Detail → Skill

The "Skill Link Card" in the left column (described above) provides the primary navigation.

### Skill Detail → DocSkill

On the existing skill detail page, add a small info banner at the top of the main content area (before other content):

- Call `GET /skills/{id}/doc_skill_source` on page load
- If source exists: Show a subtle banner: "Created from Documents · [Doc Skill Name]" with a link to the DocSkill detail page
- If no source: Show nothing (no empty state needed)

Banner style: neutral/info color, not prominent. Just contextual metadata.
