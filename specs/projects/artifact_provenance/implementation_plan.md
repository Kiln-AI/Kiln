---
status: complete
---

# Implementation Plan: Artifact Provenance

Phased build order. Details live in [functional_spec.md](functional_spec.md) and [architecture.md](architecture.md). Developed on `scosman/evals_v2`. Each phase must end green on `uv run ./checks.sh --agent-mode` and the web checks (including `check_schema.sh`).

## Phase 1 — Core + Tier 1

- [x] **Phase 1 — Submodel & helper (pure core).** `KilnArtifactProvenance` in `datamodel/provenance.py` (context-aware, lenient-on-load validators) + `validate_derived_from_ids` helper; export from `datamodel/__init__.py`; unit tests (`test_provenance.py`) covering the create-vs-load validator matrix and the helper.
- [x] **Phase 2 — Tier-1 backend.** Add the `provenance` field to Skill, Prompt (on `Prompt`, not `BasePrompt`), TaskRunConfig, CodeTool; wire create endpoints (accept + `validate_provenance_or_400`), leave PATCH models untouched, ensure reads return it (add to `CodeToolResponse`/`CodeToolCreateResponse`); datamodel load/back-compat tests + API tests. Covers TaskRunConfig's two create paths.
- [x] **Phase 3 — Tier-1 clone wiring + client.** Thread `provenance` (`origin:"human"` + `derived_from_ids:[source.id]`) through the four Tier-1 clone/create forms; regenerate OpenAPI schema; add `KilnArtifactProvenance` to `types.ts`; clone tests. No provenance display UI.

## Phase 2 — Tier 2

- [x] **Phase 4 — Tier-2 backend.** Add the `provenance` field + create-endpoint plumbing to EvalConfig, Finetune (thread through `create_and_start`), RagConfig, ExtractorConfig, ChunkerConfig, EmbeddingConfig, VectorStoreConfig, RerankerConfig; PATCH untouched; reads return it; tests.
- [x] **Phase 5 — Tier-2 clone wiring + client.** RagConfig clone wiring (the only Tier-2 clone path) + OpenAPI regen + clone test.

## Notes
- The Phase-1/2 clone-path inventory is already resolved (see architecture §3): clone paths exist for Skill, Prompt, TaskRunConfig, CodeTool (Tier 1) and RagConfig (Tier 2) only; the cross-scope case does not occur.
- Out of scope this project: any provenance **display** UI, structured `evidence_refs` (v2), lineage traversal/visualization, backfilling legacy artifacts.
