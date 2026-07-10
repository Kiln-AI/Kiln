---
status: draft
---

# Functional Spec: Artifact Provenance

## Overview

Add a shared, immutable **provenance** record to Kiln's compiled/tunable artifacts. Provenance answers three questions about an artifact: *why it exists* (`notes`), *what it was derived from* (`derived_from_ids`), and *whose judgment created it* (`origin`). A single Pydantic submodel — `KilnArtifactProvenance` — is embedded as one optional field on each host model. Clone flows stamp lineage automatically; creation stamps origin automatically. Provenance is written once at creation and is immutable thereafter (enforced at the API layer).

This is compile-time metadata for **future agent sessions and humans reading the project on disk**. It is deliberately *not* a UI feature and *not* a runtime model surface: nothing about provenance is rendered in the web app (this release), and it is never injected into any tool/prompt/context sent to a runtime model.

Authoritative for field names and field descriptions: [`project_overview.md`](project_overview.md) ("Datamodel sketch"). This spec adds the behavioral contract, the API rules, the clone wiring, and a small set of corrections forced by the codebase (see [Appendix A](#appendix-a--deviations-from-the-overview)).

**Branch:** developed on top of `scosman/evals_v2` (which contains the Code Tools feature). Purely additive — no schema-version bump, no migration.

## 1. Models covered

Every host model is an on-disk `KilnParentedModel` stored as a child in a relationship folder, so each has **same-type siblings in the same parent scope** — the resolution domain for `derived_from_ids`. A "clone path" is a UI flow that duplicates an existing artifact (Kiln has no backend clone endpoints — see [§7](#7-clone-wiring)).

**Tier 1 (Phase 1) — the models the compile loop touches today:**

| Model | Datamodel | Parent scope | Sibling folder | Clone path? | Create / PATCH API |
|---|---|---|---|---|---|
| `Skill` | `datamodel/skill.py` | Project | `skills/` | ✅ | `studio_server/skill_api.py` |
| `Prompt` | `datamodel/prompt.py` | Task | `prompts/` | ✅ | `kiln_server/prompt_api.py` |
| `TaskRunConfig` | `datamodel/task.py` | Task | `run_configs/` | ✅ | `studio_server/eval_api.py` (+ `run_config_api.py` MCP path) |
| `CodeTool` | `datamodel/code_tool.py` | Project | `code_tools/` | ✅ | `studio_server/code_tool_api.py` |

**Tier 2 (Phase 2) — the tunable surface referenced by run configs:**

| Model | Datamodel | Parent scope | Sibling folder | Clone path? | Create / PATCH API |
|---|---|---|---|---|---|
| `EvalConfig` | `datamodel/eval.py` | Eval | `configs/` | ❌ | `studio_server/eval_api.py` (create only; no PATCH) |
| `Finetune` | `datamodel/finetune.py` | Task | `finetunes/` | ❌ | `studio_server/finetune_api.py` |
| `RagConfig` | `datamodel/rag.py` | Project | `rag_configs/` | ✅ | `kiln_server/document_api.py` |
| `ExtractorConfig` | `datamodel/extraction.py` | Project | `extractor_configs/` | ❌ | `kiln_server/document_api.py` |
| `ChunkerConfig` | `datamodel/chunk.py` | Project | `chunker_configs/` | ❌ | `kiln_server/document_api.py` (create only; no PATCH) |
| `EmbeddingConfig` | `datamodel/embedding.py` | Project | `embedding_configs/` | ❌ | `kiln_server/document_api.py` (create only; no PATCH) |
| `VectorStoreConfig` | `datamodel/vector_store.py` | Project | `vector_store_configs/` | ❌ | `kiln_server/document_api.py` (create only; no PATCH) |
| `RerankerConfig` | `datamodel/reranker.py` | Project | `reranker_configs/` | ❌ | `kiln_server/document_api.py` (create only; no PATCH) |

**Deliberately excluded** (per overview decision 10): `Eval` (the goal, immutable — its tunable `EvalConfig` is included) and `ExternalToolServer` (the tunable artifact is the tool list on the run config).

**Clone-path summary:** 5 of the 12 models have a clone path — **Skill, Prompt, TaskRunConfig, CodeTool** (all of Tier 1) and **RagConfig**. The other 7 gain the field + API plumbing but have no clone to wire; their provenance is populated only on explicit create (typically just the auto-stamped `origin`).

## 2. The `KilnArtifactProvenance` submodel

A new plain `pydantic.BaseModel` (mirrors `DataSource` — no `id`/`v`/`path`/`model_type` of its own), defined in `datamodel/provenance.py` and exported from `datamodel/__init__.py`. Fields exactly as the overview sketch:

```python
class KilnArtifactProvenance(BaseModel):
    notes: str | None = Field(default=None, max_length=2000, description=...)
    derived_from_ids: list[ID_TYPE] = Field(default_factory=list, description=...)
    origin: str | None = Field(default=None, description=...)
```

### 2.1 Validators (on the submodel)

| Field | Rule | Enforced |
|---|---|---|
| `notes` | Strip surrounding whitespace; coerce empty/whitespace-only → `None`; enforce the 2,000-char cap **after** stripping (raise `ValueError` if over). | Always |
| `derived_from_ids` | Reject empty/whitespace-only strings; reject duplicate ids. | Always |
| `origin` | If **not** loading from file: a non-`None` value must be exactly `"human"` or `"agent"` (raise `ValueError` otherwise). If loading from file: accept any string (forward-compat). `None` is always permitted. | Create vs. load |

Load-vs-create is detected with the existing `loading_from_file(info)` helper (`basemodel.py`) — the same mechanism `TaskOutput.validate_output_source` uses. This validation is **format-only**: no existence checks and no cross-sibling lookups happen in a validator (they break file loads — established Kiln rule). Existence/self-reference checks live at the API layer ([§5.2](#52-create-validation)).

> **Correction (see Appendix A):** `derived_from_ids` entries are **not** run through an "ID format validator" — no such validator exists in Kiln (`ID_TYPE = Optional[str]`, unconstrained). The enforceable rules are non-empty + no-duplicates.

> **Interpretation of decision 5:** the sketch declares `origin` with `default=None`, so `None` remains a legal model-level value (meaning "unspecified/legacy"). "Strict on create" therefore means *"a value that is present must be valid,"* not *"a value must be present."* The API layer is what guarantees a real value gets stamped ([§6](#6-origin-semantics--defaulting)).

## 3. Host field & back-compat

Each host model gains exactly one field:

```python
provenance: KilnArtifactProvenance | None = None
```

- For `Prompt`, the field is added to the stored `Prompt` class (whose body is currently `pass`), **not** to the shared `BasePrompt` — `BasePrompt` is embedded inside `TaskRunConfig`/`Finetune` and must not carry artifact provenance.
- Purely additive optional field, following the `is_archived` precedent: old `.kiln` files load untouched, no `v` bump, no migration. `provenance is None` = legacy / unknown / created-without-provenance.
- **Accepted known risk** (same as `is_archived`): an old client that load-mutate-saves a file written by a newer client silently drops the field.

## 4. Lifecycle behaviors

### 4.1 Creation
When an artifact is created through its create endpoint, provenance is **always stamped** (overview Q-decision: "stamp origin on all creates"):
- If the request omits `provenance`, the endpoint constructs `KilnArtifactProvenance(origin="human", derived_from_ids=[])`.
- If the request includes `provenance`, the endpoint validates it ([§5.2](#52-create-validation)) and, if `origin` is `None`, sets it to `"human"`.

Result: every newly created artifact of a covered type records at least its origin. See [§6](#6-origin-semantics--defaulting) for how `"human"` vs `"agent"` is chosen.

### 4.2 Cloning
Cloning is deriving a new artifact from an existing one. The clone flow additionally sets `derived_from_ids = [source.id]` on the new artifact's provenance (first element = primary parent). Multi-parent lineage (`derived_from_ids` with >1 entry, e.g. a GEPA-style merge) is supported by the data model and API but is not produced by any current UI clone flow. `notes` is left empty by UI clones (no note-input UI this release; empty is fine — the parent id is the value).

### 4.3 Immutability
Provenance describes creation and is never edited:
- It is **structurally absent** from every PATCH/update request model, so there is no field to change.
- Where a PATCH model uses `ConfigDict(extra="forbid")` (e.g. `CodeToolUpdateRequest`), sending `provenance` is additionally rejected with a 422.
- Post-creation learnings about an artifact belong in Part 2 memory (with a link) or in the next derived artifact's `notes` — not here.

### 4.4 Reading
Read and list endpoints return `provenance` as-is (including `None`). Agent access follows each model's existing access policy; nothing about provenance is secret. It is **not** displayed in the web UI ([§8](#8-ui-scope)).

## 5. API contracts

### 5.1 Request/response shape
- **Create request models** gain an optional `provenance: KilnArtifactProvenance | None = None`. The submodel is reused directly as the request component.
- **PATCH/update request models** do **not** gain the field (omission is the mechanism).
- **Read/list responses**: models that already serialize the datamodel directly get `provenance` for free; models with a dedicated response model (e.g. `CodeToolResponse`) gain the field explicitly.

### 5.2 Create validation
On create, when a `provenance` is supplied, the endpoint validates (in addition to the submodel's format validators):

1. **Self-reference:** no entry in `derived_from_ids` equals the new artifact's own `id`. → **400**
2. **Existence:** every entry in `derived_from_ids` resolves to an existing same-type sibling in the same parent scope, **archived included** (lineage may point at archived losers). Resolution uses the existing `from_id_and_parent_path` / sibling-scan helpers. → **400** per missing id.

Error copy for a rejected edit attempt (if an active guard is ever added rather than relying on structural omission) mirrors the CodeTool immutability doctrine: *"provenance is immutable — it describes creation."*

### 5.3 Per-model API notes
- **Finetune**: `create_finetune` delegates to `finetune_adapter_class.create_and_start(...)`; `provenance` must be threaded through that call to where the `Finetune` is constructed.
- **TaskRunConfig**: has **two** create paths — the primary `create_task_run_config` (`eval_api.py`) and the MCP path (`create_mcp_run_config` / `create_task_from_tool` in `run_config_api.py`). Both accept and stamp `provenance`.
- **EvalConfig / ChunkerConfig / EmbeddingConfig / VectorStoreConfig / RerankerConfig**: no PATCH endpoint exists, so immutability is automatically satisfied.
- **CodeTool**: `provenance` added to `CodeToolCreateRequest` and `CodeToolResponse`/`CodeToolCreateResponse`; `CodeToolUpdateRequest` (already `extra="forbid"`) is left untouched.

## 6. Origin semantics & defaulting

`origin` records **whose judgment** produced the artifact (not who typed):
- `"human"` — a person authored it directly, **or** an agent created it fulfilling a direct human request ("clone this skill", "write me a prompt that…").
- `"agent"` — an agent created it autonomously, on its own judgment during exploration/optimization.
- `None` — unknown/legacy.

**Defaulting rule (create endpoints):** when the caller does not specify `origin`, the endpoint stamps `"human"`. Autonomous agents override by sending `origin="agent"` in the request. Rationale:
- The web UI represents human action, so `"human"` is correct for every UI-driven create/clone with **zero** frontend changes to non-clone flows.
- `"human"` is the **safe default** for the downstream consumer: the auto-research agent treats human-origin artifacts as constraints (do not prune/re-test) and agent-origin ones as re-testable prior work. Defaulting an uncertain origin to `"human"` errs toward *preserving* work rather than wrongly pruning a real constraint.

**Known limitation (flagged):** an autonomous agent that creates an artifact via the shared create endpoint and forgets to set `origin="agent"` will be mislabeled `"human"`. Making agents set `origin` correctly is skill-library guidance owned by the O3 repo (out of scope here); this project provides the field, the strict-on-create validation, and the safe default.

The documented future upgrade path (if finer grain is ever needed) is ARA's four-tag taxonomy (`user` / `ai-suggested` / `ai-executed` / `user-revised`) — but consumers must always tolerate unknown `origin` values.

## 7. Clone wiring

**Architecture fact:** Kiln has **no backend clone endpoints**. Every clone is frontend-orchestrated — the UI loads the source artifact, prefills a create form/dialog (renaming to "Copy of…"), and calls the **normal create endpoint**. The **cross-scope assertion holds**: every clone stays in the same parent scope (verified across all clone paths), so `derived_from_ids` sibling resolution is always valid and the overview's cross-scope fallback is never needed.

Lineage is therefore stamped by **threading provenance through the existing create request** (chosen over adding dedicated clone endpoints): each clone flow adds `provenance.derived_from_ids = [source.id]` to the create POST body. `origin` is left to the API default (`"human"`). The five wired flows:

| Model | Clone entry point |
|---|---|
| Skill | `skills/[project_id]/clone/[skill_id]/` → `SkillForm(clone_mode)` → POST `/skills` |
| Prompt | `prompts/[project_id]/[task_id]/clone/[prompt_id]/` → `PromptForm(clone_mode)` → POST `/prompts` |
| TaskRunConfig | `create_new_run_config_dialog.svelte` `showClone()` → POST create run config |
| CodeTool | `code_tools/[code_tool_id]/` `handle_clone()` → prefilled `add_tools/code_tool` → POST `/code_tools` |
| RagConfig | `docs/rag_configs/[project_id]/[rag_config_id]/rag_config/clone/` → `EditRagConfigForm` → POST `create_rag_config` |

RagConfig clone references (does not duplicate) its five sub-configs; only the new `RagConfig` gets `derived_from_ids=[source_rag_config.id]`.

## 8. UI scope

**No provenance is displayed in the web UI this release**, and no read-only provenance block, origin badge, "derived from" chips, or note-input box is added. Provenance is agent- and disk-facing metadata; a human-facing UI is explicitly deferred.

The **only** frontend change is invisible clone wiring: the five clone flows above add `derived_from_ids` to their create POST bodies. Non-clone create flows need no frontend change (the backend stamps `origin="human"`). The OpenAPI schema is regenerated (`generate_schema.sh`) so the new field appears in `api_schema.d.ts`; a `KilnArtifactProvenance` type is added to `types.ts` for the clone-wiring code.

## 9. Edge cases & error handling

| Case | Behavior |
|---|---|
| Legacy artifact (no provenance in file) | Loads with `provenance = None`. Never backfilled. |
| `derived_from_ids` references a non-existent sibling | 400 on create. |
| `derived_from_ids` references the artifact's own id | 400 on create (self-reference). |
| `derived_from_ids` references an **archived** sibling | Allowed (lineage may point at archived losers). |
| `derived_from_ids` contains duplicates or empty strings | Rejected by the submodel validator (`ValueError` → 422). |
| `notes` over 2,000 chars (after strip) | Rejected by the submodel validator. |
| `notes` empty/whitespace | Coerced to `None`. |
| `origin` not in `{human, agent}` on create | Rejected (422/400). |
| `origin` an unknown string when loading an old/newer file | Accepted (forward-compat). |
| PATCH request includes `provenance` | Ignored (field not on the model) or rejected 422 where `extra="forbid"`. |
| Cross-scope clone | Does not occur in Kiln; asserted during implementation. If ever found: stop and flag (fallback: source in `notes`, `derived_from_ids` empty). |

## 10. Out of scope

Per overview: the general agent memory system (Part 2); structured `evidence_refs` (named v2); cross-type/cross-scope lineage and any universal ID scheme; lineage traversal/visualization/global indexes; backfilling legacy artifacts; consolidation/expiry/editing of provenance; enforcing that agents write good notes (O3 skill-library work). Additionally for this release: **any UI display of provenance** ([§8](#8-ui-scope)).

## Appendix A — Deviations from the overview

Forced by the `evals_v2` codebase; each should be confirmed at spec review:

1. **No `ID_TYPE` validator exists.** `ID_TYPE = Optional[str]` with no format/length validator. `derived_from_ids` validation is therefore non-empty + no-duplicates only (plus API-layer existence/self-ref). The overview's "validate with the existing `ID_TYPE` validator" refers to something that isn't in the code.
2. **CodeTool is an in-scope Tier-1 host model here.** The overview expected the Code Tools project to add the field ("verify, don't re-add"). On `evals_v2` the Code Tools feature is merged but its spec does **not** mention provenance and CodeTool has no provenance field — so this project adds it, coordinating with (not duplicating) the existing CodeTool. CodeTool also supplies the real immutable-artifact + clone-to-derive precedent the overview references.
3. **Clone stamps lineage via the create request, not clone endpoints.** No backend clone endpoints exist; "wire every Clone function/endpoint" becomes "thread `derived_from_ids` through the five clone UI flows' create calls."
4. **`origin` defaulting is a create-endpoint responsibility** (default `"human"`, agents override) so that "stamp origin on all creates" holds with no non-clone frontend changes.
5. **No UI display.** The overview's Phase-1 "read-only provenance block" and optional clone note-input are dropped; provenance is agent-facing only this release.
