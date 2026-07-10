---
status: draft
---

# Architecture: Artifact Provenance

Technical design for the [functional spec](functional_spec.md). Grounded in the `scosman/evals_v2` codebase. The work is one small new type plus uniform, repetitive plumbing across 12 models and ~5 API files, so this is a **single-file architecture** — no `components/` docs (no component has internal complexity beyond the submodel, which is fully specified below).

## 1. Data model

### 1.1 New module `libs/core/kiln_ai/datamodel/provenance.py`

A plain `pydantic.BaseModel` value object (mirrors `DataSource` — no `id`/`v`/`path`/`model_type`). It reads the validation context directly because, as a plain `BaseModel`, it has no `KilnBaseModel.loading_from_file()` helper.

```python
from pydantic import BaseModel, Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from kiln_ai.datamodel.basemodel import ID_TYPE

VALID_ORIGINS = {"human", "agent"}
NOTES_MAX_LENGTH = 2000


def _is_loading(info: ValidationInfo) -> bool:
    return bool(info.context and info.context.get("loading_from_file", False))


class KilnArtifactProvenance(BaseModel):
    """Why this artifact exists and what it was derived from.

    Written once at creation; immutable thereafter (enforced at the API layer).
    Compile-time metadata for future agent sessions and humans — never shown to
    runtime models (not part of any tool/prompt surface)."""

    notes: str | None = Field(
        default=None,
        description=(  # (full text from the overview sketch; ~2,000-char cap)
            "Why this artifact exists: the problem/hypothesis it addresses, what "
            "changed vs. the derived_from_ids parents, what validation/evidence "
            "supports it (cite eval/run_config/trace IDs inline), and known limits. "
            "First line = one-sentence summary. Record observations with conditions, "
            "never universal rules. Max ~2000 chars."
        ),
    )
    derived_from_ids: list[ID_TYPE] = Field(
        default_factory=list,
        description=(
            "IDs of same-type sibling artifacts this one was derived from. Ordered: "
            "first = primary parent (the artifact this replaces or is a new version "
            "of); further entries = additional sources merged in. Empty = not derived. "
            "IDs resolve among siblings in the same parent scope only."
        ),
    )
    origin: str | None = Field(
        default=None,
        description=(
            "Whose judgment created this artifact. 'human': a person authored it "
            "directly OR an agent created it fulfilling a direct human request. "
            "'agent': an agent created it autonomously. None: unknown/legacy. Required "
            "when this provenance is created; consumers must tolerate unknown values."
        ),
    )

    @field_validator("notes", mode="after")
    @classmethod
    def _validate_notes(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        # Cap is a create-time write-discipline check; lenient on load so a
        # future longer note never breaks loading an existing file.
        if not _is_loading(info) and len(v) > NOTES_MAX_LENGTH:
            raise ValueError(f"notes must be <= {NOTES_MAX_LENGTH} characters")
        return v

    @field_validator("derived_from_ids", mode="after")
    @classmethod
    def _validate_derived_from_ids(
        cls, v: list[ID_TYPE], info: ValidationInfo
    ) -> list[ID_TYPE]:
        if _is_loading(info):
            return v  # accept any historical/future list as-is
        seen: set[str] = set()
        for entry in v:
            if entry is None or not str(entry).strip():
                raise ValueError("derived_from_ids entries must be non-empty ids")
            if entry in seen:
                raise ValueError(f"duplicate id in derived_from_ids: {entry}")
            seen.add(entry)
        return v

    @field_validator("origin", mode="after")
    @classmethod
    def _validate_origin(cls, v: str | None, info: ValidationInfo) -> str | None:
        if _is_loading(info):
            return v  # any string or None accepted from disk (forward/back-compat)
        if v not in VALID_ORIGINS:
            raise ValueError(f"origin is required and must be one of {VALID_ORIGINS}")
        return v
```

Notes:
- **No `model_config = extra="forbid"`** — default `extra="ignore"` keeps forward-compat (a future extra provenance field in a file is ignored, not fatal).
- **No `Field(max_length=...)` on `notes`** — that constraint fires on load too; the cap lives in the validator (create-only) instead.
- `derived_from_ids: list[ID_TYPE]` is `list[Optional[str]]`; the validator rejects `None`/empty entries on create. There is intentionally **no id-format validator** — `ID_TYPE = Optional[str]` has none in Kiln.
- `origin` keeps `default=None` in its signature only so a file carrying a provenance object without `origin` still loads; on create, `None` is rejected.

### 1.2 Export

`datamodel/__init__.py`: add `from kiln_ai.datamodel.provenance import KilnArtifactProvenance` and insert `"KilnArtifactProvenance"` into `__all__` (alphabetical position).

### 1.3 Host field (one line per model)

Add to each host model:

```python
provenance: KilnArtifactProvenance | None = None
```

| Model | File | Note |
|---|---|---|
| Skill | `datamodel/skill.py` | — |
| Prompt | `datamodel/prompt.py` | Add to the `Prompt` class (body is `pass`), **not** `BasePrompt` (which is embedded in run configs / finetunes). |
| TaskRunConfig | `datamodel/task.py` | — |
| CodeTool | `datamodel/code_tool.py` | — |
| EvalConfig | `datamodel/eval.py` | — |
| Finetune | `datamodel/finetune.py` | — |
| RagConfig | `datamodel/rag.py` | — |
| ExtractorConfig | `datamodel/extraction.py` | — |
| ChunkerConfig | `datamodel/chunk.py` | — |
| EmbeddingConfig | `datamodel/embedding.py` | — |
| VectorStoreConfig | `datamodel/vector_store.py` | — |
| RerankerConfig | `datamodel/reranker.py` | — |

Additive, `default=None`, no `v` bump, no migration (the `is_archived` precedent). Nested-submodel validation context propagates automatically when the host is loaded via `KilnBaseModel.load_from_file` (which already calls `model_validate(..., context={"loading_from_file": True})`).

## 2. API layer

### 2.1 Shared validation helper

New helper in `libs/server/kiln_ai/...` (base server package, importable by both `kiln_server` and `studio_server`) — e.g. `libs/server/kiln_server/provenance_api.py`:

```python
from collections.abc import Callable
from fastapi import HTTPException
from kiln_ai.datamodel.provenance import KilnArtifactProvenance

def validate_provenance_on_create(
    provenance: KilnArtifactProvenance | None,
    new_id: str,
    resolve_sibling: Callable[[str], object | None],
) -> None:
    """API-layer semantic checks for a to-be-created artifact's provenance.
    Format checks already ran in the submodel validators (422). Raises 400."""
    if provenance is None:
        return
    for parent_id in provenance.derived_from_ids:
        if parent_id == new_id:
            raise HTTPException(400, "provenance.derived_from_ids cannot reference the new artifact itself")
        if resolve_sibling(parent_id) is None:
            raise HTTPException(400, f"provenance.derived_from_ids references unknown sibling: {parent_id}")
```

`resolve_sibling` is `lambda cid: HostModel.from_id_and_parent_path(cid, parent.path)` — the same targeted-lookup precedent as `create_rag_config` (reads archived siblings too, satisfying "archived included").

### 2.2 Per-model create flow

Uniform recipe for each create endpoint:

1. Add `provenance: KilnArtifactProvenance | None = None` to the **create request model**. (Format validators run when FastAPI parses the body → **422** on bad `origin`/dupes/over-length.)
2. Construct the datamodel with `provenance=req.provenance` (this generates the new `id`).
3. Call `validate_provenance_on_create(model.provenance, model.id, resolve_sibling)` → **400** on self-ref/missing.
4. `model.save_to_file()`.

Ordering matters: the `id` needed for the self-reference check is generated at construction (step 2), before validation (step 3).

Create request models / endpoints to touch:

| Model | Create request model | Endpoint / file | Special |
|---|---|---|---|
| Skill | `SkillCreationRequest` | `create_skill` — `studio_server/skill_api.py` | — |
| Prompt | `PromptCreateRequest` | `create_prompt` — `kiln_server/prompt_api.py` | — |
| TaskRunConfig | `CreateTaskRunConfigRequest` | `create_task_run_config` — `studio_server/eval_api.py` | **also** MCP path `CreateMcpRunConfigRequest` / `create_task_from_tool` — `run_config_api.py` |
| CodeTool | `CodeToolCreateRequest` | `create...` — `studio_server/code_tool_api.py` | add to `CodeToolResponse` + `CodeToolCreateResponse` |
| EvalConfig | `CreateEvalConfigRequest` | `create_eval_config` — `eval_api.py` | siblings = `eval.configs()` |
| Finetune | `CreateFinetuneRequest` | `create_finetune` — `finetune_api.py` | thread `provenance` through `finetune_adapter_class.create_and_start(...)` to the `Finetune(...)` construction |
| RagConfig | `CreateRagConfigRequest` | `create_rag_config` — `document_api.py` | — |
| ExtractorConfig | `CreateExtractorConfigRequest` | `create_extractor_config` — `document_api.py` | — |
| ChunkerConfig | `CreateChunkerConfigRequest` | `create_chunker_config` — `document_api.py` | — |
| EmbeddingConfig | `CreateEmbeddingConfigRequest` | `create_embedding_config` — `document_api.py` | — |
| VectorStoreConfig | `CreateVectorStoreConfigRequest` | `create_vector_store_config` — `document_api.py` | — |
| RerankerConfig | `CreateRerankerConfigRequest` | `create_reranker_config` — `document_api.py` | — |

### 2.3 PATCH (immutability)

**No change** to any PATCH/update request model — provenance is simply not a field on them (structural omission). `CodeToolUpdateRequest` already has `ConfigDict(extra="forbid")`, so a stray `provenance` on a CodeTool PATCH is actively rejected (422). EvalConfig / Chunker / Embedding / VectorStore / Reranker have no PATCH endpoint at all. No runtime guards are added; the immutability error copy ("provenance is immutable — it describes creation") is documented for reference only.

### 2.4 Reads

Endpoints that serialize the datamodel directly return `provenance` with no change. Endpoints with a **dedicated response model** must add the field:
- `CodeToolResponse` and `CodeToolCreateResponse` (`code_tool_api.py`) — add `provenance: KilnArtifactProvenance | None = None`.
- Audit each other model's read/list endpoint during implementation; add the field to any dedicated response model found. (Most Kiln endpoints return the datamodel directly.)

## 3. Clone wiring (frontend)

Kiln has no backend clone endpoints — clones are prefilled creates. For each clone flow, add `provenance` to the create POST body: `{ origin: "human", derived_from_ids: [<source id>] }`. Because create and clone usually share one form, the same edit also sets `origin: "human"` for fresh creates (the "goal", §8 of the functional spec). No display.

| Model | Form / dialog | Source id available as |
|---|---|---|
| Skill | `skills/skill_form.svelte` (`clone_mode`) | loaded source skill id |
| Prompt | `prompts/[project_id]/[task_id]/prompt_form.svelte` (`clone_mode`) | source prompt id |
| TaskRunConfig | `lib/ui/run_config_component/create_new_run_config_dialog.svelte` (`showClone`) → `run_config_component.svelte` `save_new_run_config` | `source_run_config.id` |
| CodeTool | `tools/[project_id]/add_tools/code_tool/+page.svelte` (clone-prefill params) | cloned-from code tool id |
| RagConfig | `docs/rag_configs/[project_id]/create_rag_config/edit_rag_config_form.svelte` | source rag config id |

Then regenerate the OpenAPI client: run `app/web_ui/src/lib/generate_schema.sh`, commit the updated `api_schema.d.ts`, and add `export type KilnArtifactProvenance = components["schemas"]["KilnArtifactProvenance"]` to `app/web_ui/src/lib/types.ts`. `check_schema.sh` (CI) must pass.

## 4. Technical challenges (designed here, not during coding)

1. **Context propagation into a nested plain-`BaseModel`.** The lenient-on-load behavior depends on Pydantic v2 propagating the host's `model_validate(context=...)` into `KilnArtifactProvenance`'s field validators. This is standard Pydantic v2 behavior but is load-bearing — it gets an explicit test (§5, load a host file with an unknown `origin` and assert success).
2. **Finetune create indirection.** `create_finetune` delegates to `create_and_start`; provenance must be a new parameter threaded down to where `Finetune(...)` is built and saved.
3. **TaskRunConfig dual create paths.** Both `eval_api.py` and the MCP `run_config_api.py` build `TaskRunConfig`; both accept + persist provenance.
4. **Self-reference timing.** The new id exists only after model construction, so the self-ref check runs post-construct, pre-save (§2.2 step 3).
5. **notes cap on load.** Must not use `Field(max_length)`; cap lives in the create-only validator so future longer notes load fine.

## 5. Testing strategy

pytest, co-located `test_*.py` (see the repo's `python_test_guide.md`); frontend `vitest`. Coverage:

**Submodel (`test_provenance.py`):**
- `notes`: strips; empty/whitespace → `None`; > 2000 → error on create; > 2000 accepted under `{"loading_from_file": True}` context.
- `derived_from_ids`: rejects `None`/empty/duplicate on create; accepts a duplicate/empty list under load context.
- `origin`: `None`/`"banana"` → error on create; `"human"`/`"agent"` ok; any string / `None` accepted under load context.
- Round-trip: a host model with provenance dumps and reloads equal; a host `.kiln` fixture with a provenance object but no `origin` / unknown `origin` **loads successfully**.
- Back-compat: a legacy `.kiln` fixture with no `provenance` key loads with `provenance is None`.

**API (per tier, in the existing `test_*_api.py`):**
- Create with valid provenance (referencing a real sibling) → persisted and returned on read.
- Create referencing a **nonexistent** sibling → 400; referencing an **archived** sibling → 200 (allowed).
- `validate_provenance_on_create` unit test: `new_id` present in `derived_from_ids` → 400 self-reference (defensive; the client can't normally force this since the id is server-generated).
- Create with invalid `origin` / over-length `notes` → 422.
- PATCH cannot change provenance: for CodeTool, PATCH with `provenance` → 422 (`extra="forbid"`); for others, confirm the update model has no such field and provenance is unchanged after an edit.
- Clone (Skill, Prompt, TaskRunConfig, CodeTool, RagConfig): the created artifact has `derived_from_ids == [source.id]` and `origin == "human"`.

**Coverage target:** match the surrounding modules (Kiln runs high line coverage); every new branch (each validator path, the helper's two 400s) is hit.

## 6. Error handling summary

| Layer | Failure | Result |
|---|---|---|
| Submodel validator (body parse) | bad `origin`, dupe/empty id, over-length note | 422 (Pydantic) |
| API helper | self-reference / unknown sibling | 400 (HTTPException) |
| PATCH model | attempt to set provenance | field absent (ignored) or 422 (`extra="forbid"`) |
| Load from file | any imperfect/future provenance | accepted (lenient) |

## 7. Rollout / sequencing

Phase 1 = submodel + Tier 1 (Skill, Prompt, TaskRunConfig, CodeTool: field + API + clone wiring for all four, which all have clone paths). Phase 2 = Tier 2 (EvalConfig, Finetune, RagConfig + 5 RAG components: field + API; clone wiring for RagConfig only). See [implementation_plan.md](implementation_plan.md). Each phase ends green on `uv run ./checks.sh --agent-mode` + web checks, including `check_schema.sh`.
