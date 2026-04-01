---
status: complete
---

# Functional Spec: OpenAPI Spec Improvements

Improve the OpenAPI specification for the Kiln AI API by adding missing documentation, fixing naming inconsistencies, and correcting HTTP method misuse. Changes span `libs/server/` and `app/desktop/`.

## Audience & Breaking Change Policy

The only consumer is the Svelte web UI. There are no external API consumers. Breaking changes (path renames, HTTP method changes) are acceptable — the web frontend will be updated in the same project.

## 1. Documentation-Only Changes

These changes add missing information to the OpenAPI spec. They do not alter API behavior, paths, or types. No individual approval required.

### 1.1 Operation Descriptions

Add descriptions to the ~150 operations currently lacking them. Descriptions are added as **Python docstrings** on the endpoint handler functions (FastAPI uses these as OpenAPI descriptions automatically).

**Style guide:**
- Most descriptions should be **one short sentence** or even a fragment. If the summary + HTTP method + path already make the behavior obvious, the description adds little — keep it minimal.
- Only write longer descriptions (2–3 sentences) when there is genuinely useful information not implied by the name/method — e.g., distinguishing two easily confused endpoints, documenting non-obvious side effects, or noting prerequisites.
- Never pad descriptions with filler like "This endpoint allows you to..." — get to the point.

**Examples — good:**
```
DELETE .../runs/{run_id}
  Summary: "Delete Run"
  Description: (none needed — summary says it all)

POST .../tasks/{task_id}/run
  Summary: "Run Task"
  Description: "Invokes an AI model to run the task. To store a pre-computed result without running a model, use the Create Run endpoint instead."

POST .../tasks/{task_id}/runs
  Summary: "Create Run"
  Description: "Stores a TaskRun without invoking a model."
```

**Examples — bad (too wordy):**
```
DELETE .../runs/{run_id}
  Description: "This endpoint deletes a specific task run identified by its unique run ID
  within the context of a project and task. The run will be permanently removed and
  cannot be recovered."
```

### 1.2 Parameter Descriptions

Add descriptions to all ~315 undescribed parameters using **`Path(description=...)`** annotations for path parameters and **`Query(description=...)`** for query parameters.

**ID parameters** — apply consistently across all occurrences:

| Parameter | Description |
|-----------|-------------|
| `project_id` | "The unique identifier of the project." |
| `task_id` | "The unique identifier of the task within the project." |
| `run_id` | "The unique identifier of the task run." |
| `eval_id` | "The unique identifier of the eval." |
| `eval_config_id` | "The unique identifier of the eval configuration." |
| `run_config_id` | "The unique identifier of the run configuration." |
| `prompt_id` | "The unique identifier of the prompt." |
| `spec_id` | "The unique identifier of the spec." |
| `tool_server_id` | "The unique identifier of the tool server." |
| `skill_id` | "The unique identifier of the skill." |
| `document_id` | "The unique identifier of the document." |

**Other parameters** — describe per-endpoint based on actual behavior (e.g., `tags`, `update_status`, `run_config_ids`, `all_run_configs`, etc.).

### 1.3 Schema & Property Descriptions

Add descriptions to the ~172 schemas and ~788 properties currently missing them. Prioritize schemas that appear in multiple endpoints or are key domain concepts (e.g., `TaskRun`, `Eval`, `RunConfig`, `Document`, `ChunkerConfig`, all `*Properties` eval schemas).

Schema descriptions are added via **Pydantic model docstrings** and **`Field(description=...)`** on model properties.

### 1.4 Clean Up `check_entitlements` Description

The `GET /api/check_entitlements` endpoint description contains raw Python docstring artifacts (`"Args:\n feat..."`). Rewrite the docstring as clean prose.

### 1.5 Operation Summary Improvements

Improve ambiguous or unclear summaries. Summaries are set via FastAPI decorator `summary=` parameter (not docstrings, which map to descriptions).

Key renames:

| Current Summary | Endpoint | New Summary |
|----------------|----------|-------------|
| "Edit Tags" | `POST .../runs/edit_tags` | "Edit Run Tags" |
| "Edit Tags" | `POST .../documents/edit_tags` | "Edit Document Tags" |

Additional summary improvements for eval endpoints (see Section 2.5 for details):

| Current Summary | Endpoint | New Summary |
|----------------|----------|-------------|
| "Run Eval Config" | `GET .../run_task_run_eval` | "Run Run Config Comparison" |
| "Run Eval Config Eval" | `GET .../run_eval_config_eval` | "Run Eval Config Comparison" |
| "Get Eval Config Score Summary" | `GET .../score_summary` | "Get Run Config Score Summary" |
| "Get Eval Configs Score Summary" | `GET .../eval_configs_score_summary` | "Get Eval Config Comparison Summary" |

Repair endpoint summaries (see Section 2.4 for details):

| Current Summary | Endpoint | New Summary |
|----------------|----------|-------------|
| "Run Repair" | `POST .../run_repair` | "Generate Repair" |
| "Post Repair Run" | `POST .../repair` | "Save Repair" |

### 1.6 OpenAPI Tags

Add tags to group endpoints in the OpenAPI spec. Tags are added via the `tags=` parameter on FastAPI route decorators.

**Tag grouping:**

| Tag | Endpoints |
|-----|-----------|
| Projects | Project CRUD, import |
| Tasks | Task CRUD |
| Prompts | Prompt CRUD, generation |
| Specs | Spec CRUD, copilot spec creation |
| Runs | Run CRUD, execution, bulk upload, tags |
| Evals | Eval CRUD, eval configs, running evals, score summaries |
| Run Configs | Run config CRUD |
| Documents | Document CRUD, tags, extraction, RAG |
| Synthetic Data | Category generation, sample generation, QnA |
| Fine-tuning | Finetune creation, providers |
| Providers & Models | Model lists, provider info, Ollama/Docker connect |
| Tools & MCP | Tool servers, MCP connections, Kiln task tools, search tools, demo tools |
| Skills | Skill CRUD, content |
| Copilot | Spec clarification, refinement, batch generation, questions |
| Settings & Utilities | File picker, folder opener, logs, entitlements |
| Prompt Optimization | Prompt optimization jobs |

Additional tags may be added if discovery during implementation reveals endpoints that don't fit neatly into these groups.

## 2. Functional Changes

These changes alter paths, HTTP methods, or summaries. Each is listed explicitly for approval.

### 2.1 Path Standardization: Singular → Plural

Standardize all paths to use **plural nouns** for both collection and item endpoints, matching REST conventions and the existing GET endpoints.

**Task paths** — change `/task` to `/tasks`:

| Current Path | New Path |
|-------------|----------|
| `POST /api/projects/{project_id}/task` | `POST /api/projects/{project_id}/tasks` |
| `PATCH /api/projects/{project_id}/task/{task_id}` | `PATCH /api/projects/{project_id}/tasks/{task_id}` |
| `DELETE /api/projects/{project_id}/task/{task_id}` | `DELETE /api/projects/{project_id}/tasks/{task_id}` |

**Prompt paths** — change `/task` to `/tasks` (prompt segment already consistent):

| Current Path | New Path |
|-------------|----------|
| `POST .../task/{task_id}/prompt` | `POST .../tasks/{task_id}/prompts` |
| `GET .../task/{task_id}/prompts` | `GET .../tasks/{task_id}/prompts` |
| `GET .../task/{task_id}/gen_prompt/{prompt_id}` | `GET .../tasks/{task_id}/gen_prompt/{prompt_id}` |

**Spec paths** — change `/spec` to `/specs`:

| Current Path | New Path |
|-------------|----------|
| `POST .../tasks/{task_id}/spec` | `POST .../tasks/{task_id}/specs` |

**Eval paths** — change `/eval` to `/evals` for singular usages:

| Current Path | New Path |
|-------------|----------|
| `POST .../tasks/{task_id}/eval` | `POST .../tasks/{task_id}/evals` |
| `GET .../tasks/{task_id}/eval/{eval_id}` | `GET .../tasks/{task_id}/evals/{eval_id}` |
| `DELETE .../tasks/{task_id}/eval/{eval_id}` | `DELETE .../tasks/{task_id}/evals/{eval_id}` |
| `PATCH .../tasks/{task_id}/eval/{eval_id}` | `PATCH .../tasks/{task_id}/evals/{eval_id}` |
| All sub-paths under `.../eval/{eval_id}/...` | `.../evals/{eval_id}/...` |

### 2.2 Path Standardization: Run Config Naming

Unify run config endpoint paths under a consistent `/run_configs` prefix:

| Current Path | New Path |
|-------------|----------|
| `GET .../run_configs/` | `GET .../run_configs` (remove trailing slash) |
| `POST .../task_run_config` | `POST .../run_configs` |
| `PATCH .../run_config/{run_config_id}` | `PATCH .../run_configs/{run_config_id}` |
| `POST .../mcp_run_config` | `POST .../run_configs/mcp` |

The default `POST /run_configs` creates a standard task run config. The `/run_configs/mcp` sub-path creates an MCP run config. The type distinction is clear from the sub-path and request body schema.

### 2.3 HTTP Method Changes: GET → POST for Non-SSE Mutations

The following non-SSE endpoints use GET but perform mutations. They should be changed to POST.

The implementer should confirm each endpoint is in fact a mutation before changing (the analysis below is based on code review, not runtime testing).

| Current | New | Notes |
|---------|-----|-------|
| `GET /api/provider/ollama/connect` | `POST` | Persists config when custom URL provided. |
| `GET /api/provider/docker_model_runner/connect` | `POST` | Persists config when custom URL provided. |

### 2.3a Documentation-Only: SSE Mutation Endpoints

The following endpoints use GET but trigger execution and write data. They remain GET because the browser's native `EventSource` API (used for SSE streaming) only supports GET. Add descriptions that clearly document the side effects.

| Endpoint | Side Effects |
|----------|-------------|
| `GET .../extractor_configs/{id}/run_extractor_config` | Runs extraction, writes extraction results to documents. |
| `GET .../rag_configs/{id}/run` | Runs full RAG workflow (extraction, chunking, embedding, indexing). |
| `GET .../eval_config/{id}/run_task_run_eval` | Runs task with selected run configs and scores outputs. Writes eval results. |
| `GET .../eval/{eval_id}/run_eval_config_eval` | Scores golden-dataset outputs with all eval configs. Writes eval results. |

Each description should note: (a) this is a mutation despite using GET, (b) GET is used due to browser EventSource/SSE constraints, and (c) what data is written.

### 2.4 Repair Endpoint Renames

These two endpoints serve different steps of the repair flow and need distinct names:

| Current Path | Current Summary | New Path | New Summary |
|-------------|----------------|----------|-------------|
| `POST .../runs/{run_id}/run_repair` | "Run Repair" | `POST .../runs/{run_id}/generate_repair` | "Generate Repair" |
| `POST .../runs/{run_id}/repair` | "Post Repair Run" | `POST .../runs/{run_id}/save_repair` | "Save Repair" |

**Context:** `generate_repair` calls an AI model to produce a repaired output (does not persist). `save_repair` accepts a repair (AI-generated or human-edited) and persists it to the run record.

### 2.5 Eval Endpoint Naming Improvements

These four endpoints have confusingly similar names. Investigation reveals they serve distinct purposes:

| Current Path Segment | Current Summary | Proposed Path Segment | Proposed Summary |
|---------------------|----------------|----------------------|-----------------|
| `.../run_task_run_eval` | "Run Eval Config" | `.../run_comparison` | "Run Run Config Comparison" |
| `.../run_eval_config_eval` | "Run Eval Config Eval" | `.../run_calibration` | "Run Eval Config Comparison" |

- **Run Run Config Comparison** (`run_comparison`): Runs the task with selected run configs (prompts/models), then scores outputs with one eval config. Compares run configs against each other.
- **Run Eval Config Comparison** (`run_calibration`): Scores existing golden-dataset outputs with all eval configs. Compares eval configs (judges) against human ratings.

The score summary endpoints keep their current paths but get improved summaries and descriptions (covered in Section 1.5).

### 2.6 Run vs. Runs — Description-Only Differentiation

These two endpoints have easily confused paths (`/run` vs `/runs`) but serve opposite purposes:

| Path | Purpose |
|------|---------|
| `POST .../tasks/{task_id}/run` | **Executes** a task by invoking an AI model and returning the result |
| `POST .../tasks/{task_id}/runs` | **Stores** a pre-computed TaskRun without invoking any model |

**Decision:** Keep both paths as-is. Add clear, prominent descriptions to both endpoints that explicitly distinguish them. The description for `/run` should note it invokes a model. The description for `/runs` should note it does NOT invoke a model.

## 3. Implementation Approach

### How to Add Documentation

| What | How |
|------|-----|
| Operation descriptions | Python docstrings on handler functions |
| Operation summaries | `summary=` parameter on `@app.get/post/patch/delete` decorators |
| Parameter descriptions | `Path(description=...)` and `Query(description=...)` annotations |
| Schema descriptions | Pydantic model docstrings |
| Property descriptions | `Field(description=...)` on Pydantic model fields |
| Tags | `tags=["Tag Name"]` on route decorators |

### Frontend Updates Required

Path renames and HTTP method changes require corresponding updates in the Svelte web UI:
- Update all API call URLs that reference renamed paths
- Update the 2 provider connect endpoints from GET to POST fetch calls

### What's Out of Scope

- Behavioral/logic changes to any endpoint
- Adding, removing, or consolidating endpoints
- Changing request/response schemas (beyond adding descriptions)
- API versioning or deprecation headers
- Changes to the Pydantic data models beyond documentation

## 4. Constraints

- All path parameters currently use plain function arguments. Migration to `Path(description=...)` must preserve existing behavior.
- Docstrings serve double duty: OpenAPI descriptions and pydoc. Write them to be useful in both contexts.
- The `generate_openapi.py` script and Scalar UI at `/scalar` should continue to work without modification.
