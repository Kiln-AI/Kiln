---
status: complete
---

# Phase 5: Tier-2 clone wiring + client

## Overview

Final phase of the Artifact Provenance project. Phase 4 added the `provenance` field and
create-endpoint plumbing to all eight Tier-2 models (EvalConfig, Finetune, RagConfig, and the
five RAG document configs), but intentionally left the OpenAPI client (`api_schema.d.ts`) stale.

This phase:
1. Wires provenance stamping through the RagConfig create/clone form — the only Tier-2 clone
   path (functional_spec §7). On a clone the form sends
   `{ origin: "human", derived_from_ids: [<source RagConfig id>] }`; on a fresh create it sends
   `{ origin: "human" }`. `origin` is required whenever a provenance object is sent — never send
   a provenance object without `origin`.
2. Regenerates the full OpenAPI client so `api_schema.d.ts` picks up ALL Tier-2 provenance
   additions committed in Phase 4. `check_schema.sh` must go green.
3. Adds a vitest clone test for the RagConfig provenance stamping.

No provenance display UI anywhere (functional_spec §8) — invisible payload wiring only.

## Steps

1. **Regenerate OpenAPI client** — `cd app/web_ui/src/lib && ./generate_schema.sh` with
   `UV_NO_SYNC=1` and the tkinter-stub PYTHONPATH exported. Then `./check_schema.sh` must print
   "OpenAPI schema up to date". Verify `git diff api_schema.d.ts` is provenance-only (Tier-2
   `provenance?` fields + KilnArtifactProvenance refs), with NO `PromptCacheBreakpoint` /
   `FilePromptCacheBreakpoint` / `KilnBaseModel-Input`/`-Output` split (those would be
   dependency-drift artifacts → stop).

2. **RagConfig form wiring** — `create_rag_config/edit_rag_config_form.svelte`. Both create
   functions send provenance:
   - `create_rag_config()` (custom form; also the clone path via `initial_rag_config`): send
     `provenance = initial_rag_config?.id ? { origin: "human", derived_from_ids: [initial_rag_config.id] } : { origin: "human" }`.
   - `save_template()` (fresh template create): send `provenance = { origin: "human" }`.
   A single `clone_provenance()` helper (returns `KilnArtifactProvenance`) keeps both call sites
   DRY. `initial_rag_config` is only ever passed by the clone route, so `initial_rag_config?.id`
   is the source id.

3. **types.ts** — no change needed; `KilnArtifactProvenance` alias already exists (Phase 3), and
   the architecture calls for no additional Tier-2 aliases.

## Tests

- `edit_rag_config_form.test.ts`:
  - **Clone stamps derived_from_ids** — render the form with an `initial_rag_config` (id +
    prefilled sub-config ids + tool fields), submit, assert the POST body's `provenance ==
    { origin: "human", derived_from_ids: [<source id>] }`.
  - **Template fresh create stamps origin only** — render with a `template`, type tool name +
    description, submit; assert the POST body's `provenance == { origin: "human" }` (no
    derived_from_ids). Mocks `build_rag_config_sub_configs` to fixed ids; stubs heavy child
    dialogs / TagSelector / TemplatePropertyOverview.
