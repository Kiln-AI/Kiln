---
status: complete
---

# Phase 2: Tier-1 Backend Wiring

## Overview

Phase 1 delivered the pure-core `KilnArtifactProvenance` submodel and the
`validate_derived_from_ids` create-time helper. This phase wires those into the
four Tier-1 host models and their create/read API endpoints:

- Add `provenance: KilnArtifactProvenance | None = None` to `Skill`, `Prompt`
  (on the stored `Prompt`, **not** `BasePrompt`), `TaskRunConfig`, and `CodeTool`.
- Introduce the server-layer wrapper `validate_provenance_or_400` (maps the core
  helper's `ValueError` → HTTP 400) once, in `kiln_server`, and reuse it.
- Accept + validate `provenance` on every Tier-1 create endpoint (Skill, Prompt,
  the two TaskRunConfig paths in `eval_api.py` + `run_config_api.py`, CodeTool).
- Ensure reads return provenance: datamodel-serialized endpoints get it for free;
  dedicated response models (`SkillResponse`, `ApiPrompt`, `CodeToolResponse`,
  `CodeToolCreateResponse`) gain the field explicitly.
- Leave every PATCH/update request model untouched (immutability by structural
  omission; `CodeToolUpdateRequest` additionally `extra="forbid"`).

No frontend / OpenAPI / `types.ts` work (that is Phase 3). Purely additive
optional field — no `v` bump, no migration (the `is_archived` precedent).

## Steps

1. **Host field on the four Tier-1 models** — add `provenance: KilnArtifactProvenance | None = None`:
   - `libs/core/kiln_ai/datamodel/skill.py` — `Skill`.
   - `libs/core/kiln_ai/datamodel/prompt.py` — the `Prompt` class (body is `pass`),
     **not** `BasePrompt` (which is embedded in run configs / finetunes).
   - `libs/core/kiln_ai/datamodel/task.py` — `TaskRunConfig`.
   - `libs/core/kiln_ai/datamodel/code_tool.py` — `CodeTool`.
   Import `KilnArtifactProvenance` from `kiln_ai.datamodel.provenance`.

2. **Server wrapper** — new module `libs/server/kiln_server/provenance_api.py`:
   ```python
   def validate_provenance_or_400(provenance, self_id, sibling_exists) -> None:
       try:
           validate_derived_from_ids(provenance, self_id, sibling_exists)
       except ValueError as e:
           raise HTTPException(status_code=400, detail=str(e)) from e
   ```
   Keeps FastAPI out of `libs/core`; both `kiln_server` and `studio_server`
   endpoints import it.

3. **Skill create** (`app/desktop/studio_server/skill_api.py`):
   - Add `provenance` to `SkillCreationRequest` and to `SkillResponse` (read).
   - In `create_skill`: construct `Skill(..., provenance=skill_data.provenance)`,
     then `validate_provenance_or_400(skill.provenance, skill.id, lambda cid: Skill.from_id_and_parent_path(cid, project.path) is not None)` before `save_to_file()`.

4. **Prompt create** (`libs/server/kiln_server/prompt_api.py`):
   - Add `provenance` to `PromptCreateRequest` and to `ApiPrompt` (read DTO).
   - In `create_prompt`: construct `Prompt(..., provenance=prompt_data.provenance)`,
     then validate against `Prompt.from_id_and_parent_path(cid, parent_task.path)`
     before `save_to_file()`. `**properties` already carries provenance into the
     returned `ApiPrompt`.

5. **TaskRunConfig create — primary** (`app/desktop/studio_server/eval_api.py`,
   `create_task_run_config` / `CreateTaskRunConfigRequest`):
   - Add `provenance` to the request; pass to the `TaskRunConfig(...)` constructor;
     validate against `TaskRunConfig.from_id_and_parent_path(cid, task.path)` just
     before `save_to_file()`. Returns the datamodel directly → provenance serialized.

6. **TaskRunConfig create — MCP paths** (`app/desktop/studio_server/run_config_api.py`):
   - `create_mcp_run_config` / `CreateMcpRunConfigRequest`: add `provenance`, stamp
     onto the `TaskRunConfig(...)`, validate before save.
   - `create_task_from_tool` / `CreateTaskFromToolRequest`: per functional spec §5.3
     ("Both accept and stamp provenance") + architecture §2.2 table, add `provenance`
     and stamp onto the internally-built `TaskRunConfig` (validated before its save).

7. **CodeTool create** (`app/desktop/studio_server/code_tool_api.py`):
   - Add `provenance` to `CodeToolCreateRequest`, `CodeToolResponse`,
     `CodeToolCreateResponse`; set it in `_code_tool_to_response`.
   - In `create_code_tool`: pass `provenance=request.provenance` to the `CodeTool(...)`
     constructor (already inside the `ValueError`/`PydanticValidationError` → 400
     guard), then `validate_provenance_or_400(...)` against
     `CodeTool.from_id_and_parent_path(cid, project.path)` before `save_to_file()`.

8. **PATCH models** — left untouched. `CodeToolUpdateRequest` is already
   `extra="forbid"` (a stray `provenance` → 422). `SkillUpdateRequest`,
   `PromptUpdateRequest`, `UpdateRunConfigRequest` rely on structural omission
   (default `extra="ignore"`); their update logic never copies a provenance from
   the request, so stored provenance is unchanged.

## Tests

**Datamodel (`libs/core/kiln_ai/datamodel/test_provenance.py`), host-model level:**
- Host round-trip: a `Skill` with a full provenance dumps and reloads (under load
  context) equal.
- Back-compat: a host dict with **no** `provenance` key validates with
  `provenance is None`; a host file whose provenance has an **unknown `origin`**
  loads successfully under `{"loading_from_file": True}` (context propagation).
- `Prompt` carries `provenance`; `BasePrompt` does **not** (assert the field is
  absent on `BasePrompt`).

**API — Skill (`test_skill_api.py`):**
- Create with valid `provenance` (real sibling in `derived_from_ids`) → 200,
  persisted, returned on read.
- Create referencing a nonexistent sibling → 400; an **archived** sibling → 200.
- Create with invalid `origin` / missing `origin` / over-length `notes` → 422.
- PATCH body carrying `provenance` → stored provenance unchanged (structural
  omission); `provenance` not a field of `SkillUpdateRequest`.

**API — Prompt (`test_prompt_api.py`):** valid provenance persists + returns;
nonexistent sibling → 400; invalid origin → 422.

**API — TaskRunConfig (`test_eval_api.py` + `test_run_config_api.py`):** valid
provenance persists + returns on both the eval_api create path and the MCP
`create_mcp_run_config` path; `create_task_from_tool` stamps provenance on the run
config; nonexistent sibling → 400; invalid origin → 422.

**API — CodeTool (`test_code_tool_api.py`):** valid provenance persists + returns
on create + read; nonexistent sibling → 400; archived sibling → 200; invalid
origin → 422; PATCH with `provenance` → 422 (`extra="forbid"`).
