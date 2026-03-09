# KIL-443: Agent Skills Implementation Plan

## Overview

Add support for **Agent Skills** to Kiln — reusable instruction sets (following the [agentskills.io specification](https://agentskills.io/specification)) that can be attached to agent runs. Skills provide domain-specific guidance, workflows, and references that agents can load on demand during execution.

The implementation follows the spec's progressive disclosure model:
1. **Metadata** (~100 tokens): name + description listed in the skill tool's description for all skills
2. **Instructions** (< 5000 tokens): Full skill body loaded when the agent calls the skill tool

## Architecture Decisions

### Data Model
- New `Skill` model as a **project-level child** (like `RagConfig`, `ExternalToolServer`)
- All skill data stored in `skill.kiln` (standard Kiln JSON model) — no separate content directory
- Fields follow agentskills.io spec constraints (name format, description length, etc.)

### Tool Integration
- Skills are exposed to agents as a **tool** (following the OpenCode pattern — skill info in tool description, loaded via tool call)
- New tool ID format: `kiln_tool::skill::<skill_id>`
- A single `SkillTool` that lists available skills in its description and returns skill `body` when called
- This is cleaner than system prompt injection: agents only load skills they need, and the skill listing is in the tool description rather than bloating the system prompt

### How it Works at Runtime
1. When skills are selected in run config, a `SkillTool` is added to the agent's available tools
2. The tool's description lists all available skills with their names and descriptions in XML format (matching the agentskills.io/OpenCode pattern)
3. When the agent calls `skill(name="skill-name")`, the tool returns the skill's `body` (markdown instructions)
4. The agent uses the skill instructions to guide its work

### UI
- Skills management page under Settings (project-level, same pattern as tools management)
- Standard Intro → List → Create pattern
- V1: Create skills via UI form (name, description, body content)
- Skills selector in run config UI (multi-select, same pattern as tools)
- Skills tool only provided to agent when 1+ skills are selected

## Phases

### Phase 1: Data Model & Validation
Core Pydantic model, disk persistence, agentskills.io spec validation.

### Phase 2: Skill Tool Implementation
`SkillTool` implementing `KilnToolInterface`, tool registry integration, run config changes.

### Phase 3: Backend API
FastAPI CRUD endpoints for skills, available_tools integration.

### Phase 4: Frontend - Skills Management UI
Skills list page, create page, detail/edit page.

### Phase 5: Frontend - Run Config Integration
Skills selector in run config, tools store updates.

## Out of Scope (Future Work)
- `scripts/`, `references/`, `assets/` directory support (add when import/export is built)
- Import skill from external folder (P2 per ticket — requires native folder selector)
- Export skill as agentskills.io folder (generate SKILL.md + directories on button click)
- Skill permissions/allowed-tools enforcement
- Moving tools from Settings to Optimize (separate ticket candidate)
