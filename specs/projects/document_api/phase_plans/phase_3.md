---
status: complete
---

# Phase 3: Schema and Property Descriptions

## Overview

Add docstrings to Pydantic model classes and `Field(description=...)` to properties across `libs/core/kiln_ai/datamodel/` and related model files. These descriptions flow into the OpenAPI spec via Pydantic's JSON Schema generation.

Only add descriptions where the property name + type aren't fully self-evident. Add `description=` to existing `Field()` calls rather than creating new ones.

## Steps

### Step 1: Core models in `basemodel.py`
Add descriptions to KilnBaseModel fields (v, id, path, created_at, created_by) — these appear in every schema.

### Step 2: High-value domain models
- `task_run.py` — Usage class docstring
- `eval.py` — Eval, EvalConfigType, EvalDataType docstrings
- `task.py` — TaskRequirement fields, Task output/input schema fields
- `task_output.py` — TaskOutputRating.type, DataSource.type descriptions
- `project.py` — already complete

### Step 3: Extraction and document models
- `extraction.py` — Document, FileInfo, Extraction, ExtractorConfig, ExtractionModel, Kind, OutputFormat, ExtractorType, ExtractionSource docstrings; missing Field descriptions
- `chunk.py` — ChunkerConfig, Chunk, ChunkedDocument docstrings; ChunkerType
- `embedding.py` — EmbeddingConfig, Embedding, ChunkEmbeddings docstrings
- `vector_store.py` — VectorStoreConfig docstring; VectorStoreType
- `reranker.py` — RerankerConfig docstring; RerankerType
- `rag.py` — RagConfig docstring

### Step 4: Spec and prompt models
- `spec.py` — already has good docstrings and descriptions
- `spec_properties.py` — SpecType members already have docstrings; TypedDicts don't render in OpenAPI
- `prompt.py` — already has good descriptions
- `prompt_optimization_job.py` — already has good descriptions
- `prompt_id.py` — PromptGenerators docstring
- `tool_id.py` — KilnBuiltInToolId docstring

### Step 5: Remaining datamodel files
- `dataset_split.py` — already has good docstrings
- `dataset_filters.py` — StaticDatasetFilters, DatasetFilter protocol docstrings
- `finetune.py` — already has good descriptions
- `skill.py` — already has good descriptions
- `external_tool_server.py` — ToolServerType already has docstring
- `datamodel_enums.py` — some enums have docstrings already
- `json_schema.py` — no Pydantic models to document

### Step 6: Server API request/response models
- `libs/server/kiln_server/run_api.py` — RunTaskRequest, RunSummary, BulkUploadResponse, CreateTaskRunRequest docstrings and field descriptions
- `libs/server/kiln_server/document_api.py` — ~20 request/response models
- `libs/server/kiln_server/prompt_api.py` — PromptCreateRequest, PromptGenerator, etc.
- `libs/server/kiln_server/spec_api.py` — UpdateSpecRequest, SpecCreationRequest
- `libs/server/kiln_server/task_api.py` — RatingOption, RatingOptionResponse

### Step 7: Desktop server API request/response models
- `app/desktop/studio_server/eval_api.py` — ~15 models
- `app/desktop/studio_server/finetune_api.py` — ~10 models
- `app/desktop/studio_server/tool_api.py` — ~10 models
- `app/desktop/studio_server/provider_api.py` — ~10 models
- `app/desktop/studio_server/repair_api.py` — 2 models
- `app/desktop/studio_server/data_gen_api.py` — 5 models
- `app/desktop/studio_server/run_config_api.py` — 3 models
- `app/desktop/studio_server/skill_api.py` — 4 models
- `app/desktop/studio_server/copilot_api.py` — 1 model
- `app/desktop/studio_server/import_api.py` — 1 model
- `app/desktop/studio_server/prompt_api.py` — 1 model
- `app/desktop/studio_server/prompt_optimization_job_api.py` — 5 models
- `app/desktop/studio_server/api_models/copilot_models.py` — ~15 models

### Step 8: Run lint, format, typecheck, tests
- `ruff check --fix libs/core/kiln_ai/datamodel/`
- `ruff format libs/core/kiln_ai/datamodel/`
- Also lint/format the server and desktop model files
- `uv run pytest libs/core/tests/ -x --timeout=30`
