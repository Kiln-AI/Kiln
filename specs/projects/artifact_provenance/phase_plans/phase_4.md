---
status: complete
---

# Phase 4: Tier-2 Backend Wiring

## Overview

Phase 2 wired `KilnArtifactProvenance` + `validate_provenance_or_400` into the four
Tier-1 host models. This phase applies the identical pattern to the eight Tier-2
host models and their create endpoints:

- Add `provenance: KilnArtifactProvenance | None = None` to `EvalConfig`, `Finetune`,
  `RagConfig`, `ExtractorConfig`, `ChunkerConfig`, `EmbeddingConfig`,
  `VectorStoreConfig`, `RerankerConfig`. Additive/optional — no `v` bump, no migration.
- Accept + validate `provenance` on each create endpoint, reusing the existing
  `kiln_server.provenance_api.validate_provenance_or_400` wrapper (maps the core
  helper's `ValueError` → HTTP 400). Sibling scope is the parent
  project/task/eval, resolved with the archived-inclusive `from_id_and_parent_path`.
- Leave every PATCH/update request model untouched (immutability by structural
  omission). None of the Tier-2 update/read paths do a create-mode
  `model_validate(dict)`, so no `loading_from_file` context fix is needed (reads
  load via `from_id_and_parent_path`/`configs()` under the load context; updates
  mutate attributes in place and save). Forward/back-compat provenance therefore
  never 500s on read or update.
- Reads return provenance for free: every Tier-2 endpoint returns the datamodel
  directly (no dedicated response model).

No frontend / OpenAPI / `types.ts` work (that is Phase 5). Adding provenance to the
Tier-2 create/response models changes the generated OpenAPI schema, so
`check_schema.sh` is expected to fail until Phase 5 regenerates it — that staleness
is deliberate, not a defect.

## Steps

1. **Host field on the eight Tier-2 models** — add
   `provenance: KilnArtifactProvenance | None = Field(default=None, description="Why this artifact exists and what it was derived from. Written once at creation; immutable thereafter.")`
   and `from kiln_ai.datamodel.provenance import KilnArtifactProvenance`:
   - `datamodel/eval.py` — `EvalConfig` (after `properties`).
   - `datamodel/finetune.py` — `Finetune` (after `run_config`).
   - `datamodel/rag.py` — `RagConfig` (after `tags`).
   - `datamodel/extraction.py` — `ExtractorConfig` (after `properties`).
   - `datamodel/chunk.py` — `ChunkerConfig` (after `properties`).
   - `datamodel/embedding.py` — `EmbeddingConfig` (after `properties`).
   - `datamodel/vector_store.py` — `VectorStoreConfig` (after `properties`).
   - `datamodel/reranker.py` — `RerankerConfig` (after `properties`).

2. **EvalConfig create** (`app/desktop/studio_server/eval_api.py`, `create_eval_config`
   / `CreateEvalConfigRequest`; imports already present from Phase 2):
   - Add `provenance` to `CreateEvalConfigRequest`.
   - Pass `provenance=request.provenance` to the `EvalConfig(...)` constructor.
   - Before `save_to_file()`, call
     `validate_provenance_or_400(eval_config.provenance, eval_config.id, lambda cid: EvalConfig.from_id_and_parent_path(cid, eval.path) is not None)`.

3. **Finetune create** (`app/desktop/studio_server/finetune_api.py` +
   `libs/core/kiln_ai/adapters/fine_tune/base_finetune.py`):
   - `base_finetune.py::create_and_start`: add a `provenance: KilnArtifactProvenance | None = None`
     keyword param, import `KilnArtifactProvenance`, pass it to the `FinetuneModel(...)`
     constructor so it persists.
   - `finetune_api.py`: add `provenance` to `CreateFinetuneRequest`; import
     `KilnArtifactProvenance` and `validate_provenance_or_400`. In `create_finetune`,
     validate at the endpoint (before `create_and_start`, since the finetune id is
     generated inside `create_and_start`) with
     `validate_provenance_or_400(request.provenance, None, lambda cid: Finetune.from_id_and_parent_path(cid, task.path) is not None)`
     — `self_id=None` because the id isn't available pre-construction and the
     self-reference check is P3/defensive (server-generated id, per functional spec
     §5.2). Thread `provenance=request.provenance` into the `create_and_start(...)` call.
   - Update the existing `test_create_finetune` `assert_awaited_once_with(...)` to
     include `provenance=None`.

4. **Document configs** (`libs/server/kiln_server/document_api.py`): import
   `KilnArtifactProvenance` and `validate_provenance_or_400`. For each of the six
   create endpoints, add `provenance` to the request model, pass
   `provenance=request.provenance` to the constructor, and call
   `validate_provenance_or_400(config.provenance, config.id, lambda cid: Model.from_id_and_parent_path(cid, project.path) is not None)`
   before `save_to_file()`:
   - `create_extractor_config` / `CreateExtractorConfigRequest` → `ExtractorConfig`.
   - `create_chunker_config` / `CreateChunkerConfigRequest` → `ChunkerConfig`.
   - `create_embedding_config` / `CreateEmbeddingConfigRequest` → `EmbeddingConfig`.
   - `create_reranker_config` / `CreateRerankerConfigRequest` → `RerankerConfig`.
   - `create_vector_store_config` / `CreateVectorStoreConfigRequest` → `VectorStoreConfig`.
   - `create_rag_config` / `CreateRagConfigRequest` → `RagConfig`.

5. **PATCH/update models** — left untouched. EvalConfig / Chunker / Embedding /
   VectorStore / Reranker have no PATCH endpoint. Finetune (`UpdateFinetuneRequest`),
   RagConfig (`UpdateRagConfigRequest`), and ExtractorConfig update paths rely on
   structural omission and mutate attributes in place, so stored provenance is
   preserved and never re-validated in create mode.

## Tests

**Datamodel (`libs/core/kiln_ai/datamodel/test_provenance.py`):**
- Parametrized: `provenance` is a field on all eight Tier-2 host models.
- Round-trip: an `EmbeddingConfig` with a full provenance dumps and reloads equal.
- Back-compat: an `EmbeddingConfig` dict with no `provenance` key → `provenance is None`.
- Lenient load: an `EmbeddingConfig` with unknown `origin` + duplicate/empty
  `derived_from_ids` + over-length notes loads under `{"loading_from_file": True}`
  (context propagation into the nested submodel).

**Finetune core (`libs/core/kiln_ai/adapters/fine_tune/test_base_finetune.py`):**
- `create_and_start` threads provenance onto the constructed + saved `Finetune`.

**API — EvalConfig (`test_eval_api.py`):** valid provenance (real sibling config) →
200, persisted; unknown sibling → 400; invalid origin → 422; forward-compat list
read does not 500; `UpdateRunConfigRequest`-style: assert no eval-config update model.

**API — Finetune (`test_finetune_api.py`):** request provenance is threaded into
`create_and_start` (valid sibling → 200, adapter awaited with `provenance`); unknown
sibling → 400 (validated at the endpoint); invalid origin → 422;
`UpdateFinetuneRequest` has no `provenance` field.

**API — Document configs (`test_document_api.py`):** for embedding / reranker /
vector store / chunker / extractor / rag: valid provenance persists + returned on
read; unknown sibling → 400; invalid origin → 422. Confirm `UpdateRagConfigRequest`
has no `provenance` field and a forward-compat rag config read does not 500.
