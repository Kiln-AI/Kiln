---
status: complete
---

# Phase 3: Tier-1 clone wiring + client

## Overview

Phases 1 and 2 built the `KilnArtifactProvenance` submodel and the Tier-1 backend
(the `provenance` field on Skill / Prompt / TaskRunConfig / CodeTool, create-endpoint
validation, and reads returning it). This phase makes the frontend stamp lineage.

Per functional spec §7/§8 and architecture §3, Kiln has **no backend clone endpoints** —
every clone is a frontend-orchestrated prefilled create. So we thread a `provenance`
object through the four Tier-1 clone/create forms' create POST bodies:

- On a **clone** create: `provenance = { origin: "human", derived_from_ids: [<source id>] }`
- On a **fresh (non-clone)** create through these forms: `provenance = { origin: "human" }`

`origin` is REQUIRED whenever a provenance object is sent — never send a provenance
object without `origin`. **No provenance display UI is added anywhere** — this is
invisible create-payload wiring only.

The OpenAPI client is regenerated so `KilnArtifactProvenance` appears in `api_schema.d.ts`,
and a `KilnArtifactProvenance` alias is added to `types.ts`.

## Steps

1. **Regenerate OpenAPI schema** (`app/web_ui/src/lib/generate_schema.sh`) so
   `api_schema.d.ts` carries `KilnArtifactProvenance` and the `provenance?` field on the
   four Tier-1 create request bodies. Verify `check_schema.sh` prints "OpenAPI schema up
   to date". [DONE]

2. **types.ts**: add
   `export type KilnArtifactProvenance = components["schemas"]["KilnArtifactProvenance"]`.
   [DONE]

3. **Skill** — `app/web_ui/src/routes/(app)/skills/skill_form.svelte`:
   `handleSubmit()` POSTs `/skills`. Add `provenance` to the body:
   `clone_mode && skill_id ? { origin: "human", derived_from_ids: [skill_id] } : { origin: "human" }`.

4. **Prompt** — `app/web_ui/src/routes/(app)/prompts/[project_id]/[task_id]/prompt_form.svelte`:
   `handleSubmit()` POSTs `/prompts`. The clone source id is not currently a prop; add a
   `clone_source_prompt_id: string | null` prop (the clone route passes the source prompt
   id) and set `provenance` in the body:
   `clone_mode && clone_source_prompt_id ? { origin: "human", derived_from_ids: [clone_source_prompt_id] } : { origin: "human" }`.
   Wire the clone route page to pass the source id.

5. **TaskRunConfig** — the create POST lives in
   `run_config_component.svelte::save_new_run_config` → `save_new_task_run_config`
   (`run_configs_store.ts`). Thread a `provenance` argument down:
   - `save_new_task_run_config(...)` gains a `provenance` param and includes it in the POST body.
   - `run_config_component.save_new_run_config()` gains an optional `clone_source_id` /
     builds provenance and passes it through.
   - `create_new_run_config_dialog.svelte` passes `source_run_config?.id` (set only in
     clone mode via `showClone`) so provenance is
     `{ origin: "human", derived_from_ids: [source.id] }` on clone,
     `{ origin: "human" }` on create.

6. **CodeTool** — `app/web_ui/src/routes/(app)/tools/[project_id]/add_tools/code_tool/+page.svelte`:
   `do_create()` POSTs `/code_tools`. The clone flow (`handle_clone` in the code tool
   detail page) navigates here with a `pushState` `state` object. Add `clone_source_id`
   (the source code tool id) to that state, read it here, and set `provenance`:
   `clone_source_id ? { origin: "human", derived_from_ids: [clone_source_id] } : { origin: "human" }`.

## Tests

vitest, co-located `*.test.ts`, mocking `$lib/api_client`:

- **skill_form.test.ts**: fresh create sends `provenance = { origin: "human" }` (no
  `derived_from_ids`); clone create sends
  `provenance = { origin: "human", derived_from_ids: [skill_id] }`.
- **prompt_form.test.ts**: fresh create sends `{ origin: "human" }`; clone create sends
  `{ origin: "human", derived_from_ids: [source_prompt_id] }`.
- **run_configs_store.test.ts**: `save_new_task_run_config` forwards the `provenance`
  argument into the POST body (fresh `{ origin: "human" }` and clone with
  `derived_from_ids`).
- **code_tool create +page.test.ts**: fresh create sends `{ origin: "human" }`; a
  clone-prefilled create (state carries `clone_source_id`) sends
  `{ origin: "human", derived_from_ids: [source_id] }`.

## Non-goals

- No provenance display UI (no badge, no "derived from" chips, no note box).
- No datamodel or API endpoint changes (Phase 2 already did the backend).
