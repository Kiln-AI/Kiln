# KIL-443: Agent Skills Implementation Plan

## Overview

Add support for **Agent Skills** to Kiln — reusable instruction sets (following the [agentskills.io specification](https://agentskills.io/specification)) that can be attached to agent runs. Skills provide domain-specific guidance, workflows, and references that agents can load on demand during execution.

The implementation follows the spec's progressive disclosure model:

1. **Metadata** (~100 tokens): name + description listed in the skill tool's description for all skills
2. **Instructions** (< 5000 tokens): Full skill body loaded when the agent calls the skill tool
3. **Resources** (as needed): Files from `references/` and `assets/` loaded only when required

## Architecture Decisions

### Data Model

- New `Skill` model as a **project-level child** (like `RagConfig`, `ExternalToolServer`)
- `skill.kiln` stores Kiln metadata + `description`: `id`, `name`, `description`, `is_archived`, `created_by`, `created_at` — everything needed for fast listing/dropdown display
- `SKILL.md` stores full agentskills.io content: YAML frontmatter (`name`, `description`) + markdown body (instructions)
- `name` and `description` are duplicated across both files (kept in sync on save — `save_skill_md()` reads from `self.name`/`self.description`). This avoids parsing SKILL.md just to list skills.
- `body` lives only in SKILL.md, exposed as a `body()` method — only read when the agent loads the skill
- `references/` directory for additional documentation the agent can load on demand
- `assets/` directory for static resources (images, data files, templates)
- Fields follow agentskills.io spec constraints (name format, description length, etc.)

### Disk Layout

```
skills/<id> - <name>/
  skill.kiln           # Kiln metadata (id, name, created_by, etc.)
  SKILL.md             # Frontmatter (name, description) + markdown body
  references/          # Optional: additional docs (e.g. REFERENCE.md, finance.md)
  assets/              # Optional: static resources (images, schemas, templates)
```

### Tool Integration

- Skills are exposed to agents as a **tool** (following the OpenCode pattern — skill info in tool description, loaded via tool call)
- New tool ID format: `kiln_tool::skill::<skill_id>`
- A single `SkillTool` that lists available skills in its description and returns skill `body` when called
- A `resource` parameter allows loading files from `references/` and `assets/` on demand
- This is cleaner than system prompt injection: agents only load skills they need, and the skill listing is in the tool description rather than bloating the system prompt

### How it Works at Runtime

1. When skills are selected in run config, a `SkillTool` is added to the agent's available tools
2. The tool's description lists all available skills with their names and descriptions in XML format (matching the agentskills.io/OpenCode pattern)
3. When the agent calls `skill(name="skill-name")`, the tool returns the skill's body (markdown instructions from SKILL.md)
4. When the agent calls `skill(name="skill-name", resource="references/REFERENCE.md")`, the tool returns the referenced file's content
5. The agent uses the skill instructions and references to guide its work

### UI

- Skills management page under Settings (project-level, same pattern as tools management)
- Standard Intro → List → Create pattern
- Create page: name, description, body content, plus file upload for references and assets
- Detail/edit page: edit skill content, manage references and assets
- Skills selector in run config UI (separate dropdown from tools, always visible with "New Skill +" option)
- Skills tool only provided to agent when 1+ skills are selected

## Phases

### Phase 1: Data Model & Validation ✅

Core Pydantic model, disk persistence, agentskills.io spec validation.

### Phase 2: Skill Tool Implementation ✅

`SkillTool` implementing `KilnToolInterface`, tool registry integration, run config changes.

### Phase 3: Backend API ⏳

FastAPI CRUD endpoints for skills, available_tools integration.

### Phase 4: Frontend - Skills Management UI ⏳

Skills list page, create page, detail/edit page.

### Phase 5: SKILL.md Storage Refactor

Refactor Skill model: move `description` and `body` from Pydantic fields to methods reading from `SKILL.md`. Update SkillTool and API for the new interface.

### Phase 6: References & Assets — Backend

Skill model methods for references/assets directories, SkillTool `resource` parameter for on-demand loading, system prompt update for two-step pattern, file management API endpoints.

### Phase 7: References & Assets — Frontend

File upload UI on create and detail/edit pages, reference viewing/editing, asset management with drag-and-drop upload.

### Phase 8: Frontend - Run Config Integration

Skills selector dropdown in run config (separate from tools), skills store with last-selected persistence, model compatibility checks, fine-tune integration.

## Out of Scope (Future Work)

- `scripts/` directory support
- Import skill from external folder (P2 per ticket — requires native folder selector)
- Export skill as agentskills.io folder (generate SKILL.md + directories on button click)
- Skill permissions/allowed-tools enforcement
- Moving tools from Settings to Optimize (separate ticket candidate)
