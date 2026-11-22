---
name: adding_skills
description: |
  Creating, editing, and wiring project-level skills to run configs. Covers API endpoints,
  name constraints, editing limitations, and attaching skills to run configs.
---

# Knowledge: Skills (Progressive Prompt Enhancement)

Skills are reusable, lazily-loaded instruction sets. The agent sees all skill names + descriptions in its system prompt and decides which to load. Only description + name inject into context by default; full instructions load on-demand via the `skill()` tool.

## When to use skills vs. alternatives

- **Skills** — conditional instructions/knowledge (guidelines, procedures, locale rules). Lazy-loaded; model decides when to pull.
- **Tools** — external actions (APIs, databases). Use `references/knowledge/tools.md`.
- **Sub-Agents** — multi-agent delegation. Use `references/knowledge/subagents.md`.
- **RAG** — large/unbounded document sets. Skills cap at ~50 docs.

## API Endpoints

Always load the endpoint doc before calling:

```
# read first: references/knowledge/api_docs/skills_api_list.md
```

Key endpoint docs:
- `references/knowledge/api_docs/post_api_projects_project_id_skills.md` — create skill (name, description, body required)
- `references/knowledge/api_docs/get_api_projects_project_id_skills.md` — list skills in a project
- `references/knowledge/api_docs/patch_api_projects_project_id_skills_skill_id.md` — archive/unarchive (is_archived only; **no body edit**)

## Name constraints

- Lowercase letters, numbers, hyphens only — no spaces, no uppercase.
- 1–64 chars for name; 1–1024 chars for description; body ≥1 char.
- Prefer gerund / action-shaped names: `creating-personas`, `validating-claims`, `summarizing-medical-notes` — names describe what the skill *does* for the agent, not what it *is*. (`reviewer` / `style-guide` are flat; `reviewing-pull-requests` / `applying-style-guide` route better.)

## Authoring a good `description` (this is the trigger)

The description is the only part of the skill content that always sits in the agent's system prompt — it's what the agent reads to decide whether to load the body. A weak description means the skill exists in the catalogue but never fires.

- **Third person, not first/second.** Describe the skill from outside: *"This skill should be used when..."*, not *"Use this skill when..."* and not *"I help with..."*. Inconsistent point-of-view causes the agent to misclassify the skill at routing time.
- **Name what it does AND when to load it.** Best descriptions have two halves: a one-line *what* (the procedure / knowledge owned), then explicit *trigger phrases* the user might say. *"This skill should be used when the user asks to 'rewrite a prompt for clarity', 'tighten my system prompt', mentions 'verbose output', or wants to convert an essay-style prompt into a checklist-style one."*
- **Push framing on close calls.** If the skill should fire even when the user doesn't name it explicitly, say so out loud: *"...even if they don't explicitly ask for X."* Quiet descriptions get skipped.
- **No filler.** *"Provides guidance on..."* / *"Knowledge for..."* don't add signal — every word should narrow the trigger.

## Authoring a good `body`

The body loads in full when the skill fires; treat it like a focused operating manual, not a kitchen sink.

- **Keep core instructions short and concrete.** If the body grows past ~200 lines or sprouts deep tangents, the skill is probably two skills — split before submitting (a skill cannot be edited after creation, so over-stuffing locks bad structure in place).
- **No all-caps `MUST` / `ALWAYS` / `NEVER` walls.** Reframe rigid rules as guidance with the *reason* attached (`"Skip the discovery step when the run already has a saved scorecard — it's redundant"` beats `"NEVER re-run discovery"`). Stripped-down imperatives make the agent follow the letter and miss edge cases.
- **Use examples sparingly and broadly.** A body tuned on three near-identical examples works only on those examples. Show 1–2 representative cases and a counter-example, not five variants of the same shape.
- **Lazy-reference, don't inline.** If the skill needs a long appendix (terminology, large rule set, archival examples), keep the body terse and have it tell the agent which Kiln resource (deep link, doc, knowledge file) to consult — the same progressive-disclosure shape this skill uses.

## Pre-submission checklist (skills are immutable)

Walk the user through this before POSTing. The agent should print it back and confirm each line:

1. Description is third-person and contains explicit trigger phrases (not just a summary).
2. Name is kebab-case, gerund-shaped, ≤64 chars, no consecutive hyphens.
3. Body has no all-caps imperative walls; every rule has its reason attached.
4. Body fits one focused archetype — no embedded second skill.
5. Examples are minimal and representative, not narrowly-tuned variants.
6. The user knows which run config the skill will be attached to after creation.

## Editing limitation

Skills **cannot be edited** after creation (body or description). To change one, create a new skill from its content (`GET /api/projects/{project_id}/skills/{skill_id}/content`, edit, then `POST`), or the user clones it in the app; the original stays intact so historical eval scores remain valid. Only archiving (`is_archived`) is API-writable post-creation.

## Workflow: create + wire

1. **Create via API** — POST to `/api/projects/{project_id}/skills` with name, description, body.
2. **Attach it to a run config** — a skill reaches the agent as a tool: its tool ID is in `GET /api/projects/{project_id}/available_tools` (the "Skills" set; the ID is `kiln_tool::skill::<skill_id>`). A run config cannot be edited (`PATCH .../run_configs/{rcid}` changes the name, starred and prompt name only), so create a new run config whose `tools_config.tools` lists the skill's tool ID, copying the rest of the parent (`references/knowledge/model_create_configs.md`). The user can also add a skill on the Run screen → Advanced → Skills (`http://localhost:8757/run?run_config_id={rcid}`).
3. **Report back** — after creation confirm: skill ID, name, and the deep-link to the skill detail page (`http://localhost:8757/skills/{project_id}/{sid}`).

## Deep links

- `http://localhost:8757/skills/{project_id}` — project skills list
- `http://localhost:8757/skills/{project_id}/{sid}` — skill detail page (after creation, link here to confirm)
- `http://localhost:8757/run?run_config_id={rcid}` — Run screen pre-loaded with a config (the user can add a skill under Advanced → Skills)
- `http://localhost:8757/optimize/{project_id}/{task_id}` — run configs list
