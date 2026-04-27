---
status: complete
---

# Functional Spec: Agent API Info

## Goals

Three new REST endpoints designed for the Kiln chat agent. Guiding principles:

1. **Token-efficient:** return only "key info" a decision-making LLM needs. Truncate long free-form text.
2. **No missing features:** the overview must mention every top-level entity type the project/task has, so the agent can't overlook a capability.
3. **No many-call loops:** replace patterns that currently force the agent to make N×M calls (eval results) with a single server-side aggregated payload.

The agent calls these through its existing generic `call_kiln_api` tool — no new agent tool registration is required; just new REST endpoints.

## Cross-cutting rules

These apply to every endpoint below unless noted.

### Field presence

Every documented key is always present in the response, even when empty. Empty values use `null`, `[]`, or `{}` as appropriate. This lets a future agent distinguish "checked and empty" from "older server hasn't populated this yet."

### IDs and timestamps

- All IDs are the Kiln 12-digit string IDs (`ID_TYPE`), passed through as-is.
- `created_at` is included on every list entry — serialized as an ISO-8601 string (timezone-aware).
- `favourite` / `starred` / `priority` are included whenever the underlying model has them, under the exact field name the datamodel uses (`starred` for run configs, `favourite` for evals, `priority` for specs). No normalization — the agent sees the same names the UI and models use.

### Archive handling

Each entity type has its own archive behavior (different field locations, some have none). The overview is consistent:

- Entities with an archive flag: **archived items are excluded** from the list. A sibling `archived_<name>_count: int` key reports how many were hidden. Entities with zero archived still report `archived_<name>_count: 0` — the key is always present.
- Entities without an archive flag: no count key is emitted.

| Entity | Archive field | Notes |
|---|---|---|
| Spec | `status == "archived"` | filter |
| RagConfig (search tools) | `is_archived: bool` | filter |
| ExternalToolServer | `properties.is_archived: bool` | filter |
| Skill | `is_archived: bool` | filter |
| Eval, Prompt, Fine-tune, Document, Project, Task, RunConfig, TaskRun | — | no archive concept; nothing to filter |

### Text truncation

`agent_overview` truncates `Task.instruction` to 300 words. `all_tasks` truncates `Task.instruction` to 100 words.

Algorithm: split on whitespace. If word count > limit, keep first N words, join with single spaces, append ` …` (space + ellipsis). Output a boolean `instruction_truncated: bool` alongside so the agent knows.

`Task.thinking_instruction` is truncated under the same 300-word rule (same boolean). Other long strings (descriptions, prompt text on Prompt rows) are returned in full — they're bounded by UI conventions and not typically paragraph-length.

### Performance expectations

- `agent_overview`: reads only project+task files. Aggregations (dataset counts, document tag counts) iterate JSON files under the task/project but do not call LLMs, MCP servers, or external services. Target <500ms for a typical task.
- `all_tasks`: reads every project dir + every task file. No LLM calls. Target <1s for a typical workspace.
- `eval_results_summary`: pure file reads (the underlying `score_summary` logic is already readonly file IO — see `app/desktop/studio_server/eval_api.py:1018-1110`). Shared data (`task.runs(readonly=True)`, `get_all_run_configs`) is loaded once per request and reused across evals × eval_configs rather than calling the existing endpoint function in a loop.

---

## Endpoint 1: agent_overview

`GET /api/projects/{project_id}/tasks/{task_id}/agent_overview`

One-shot summary of a single task. Agent calls this at chat start.

### Response

```jsonc
{
  "project": {
    "id": "...",
    "name": "...",
    "description": "..." | null,
    "created_at": "..."
  },
  "task": {
    "id": "...",
    "name": "...",
    "description": "..." | null,
    "instruction": "first 300 words …",
    "instruction_truncated": true,
    "thinking_instruction": "..." | null,
    "thinking_instruction_truncated": false,
    "input_json_schema": { ... } | null,
    "output_json_schema": { ... } | null,
    "default_run_config_id": "..." | null,
    "created_at": "..."
  },
  "dataset": {
    "total_count": 0,
    "by_tag": {"tag_a": 3, "tag_b": 1},
    "by_source": {"human": 0, "synthetic": 0, "file_import": 0, "tool_call": 0},
    "by_rating": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "unrated": 0}
  },
  "docs": {
    "doc_count": 0,
    "archived_document_count": 0,  // always 0 today; see archive table
    "by_tag": {},
    "by_kind": {"document": 0, "image": 0, "video": 0, "audio": 0}
  },
  "search_tools": {
    "items": [
      {
        "id": "...",
        "name": "...",
        "tool_name": "...",
        "tool_description": "...",
        "description": "..." | null,
        "tags": ["..."] | null,
        "created_at": "..."
      }
    ],
    "archived_search_tool_count": 0
  },
  "prompts": [
    {
      "id": "id::..." | "fine_tune_prompt::..." | "task_run_config::..." | "<generator_id>",
      "name": "...",
      "type": "Custom" | "Fine-Tune" | "Frozen" | "Kiln Optimized" | "Few-Shot" | "Many-Shot" | "Repair Multi-Shot" | "Chain of Thought" | "Chain of Thought + Few Shot" | "Chain of Thought + Many Shot" | "Unknown"
    }
  ],
  "specs": {
    "items": [
      {
        "eval_id": "...",
        "name": "...",
        "spec_type": "desired_behaviour" | "issue" | "tone" | "formatting" | "localization" | "appropriate_tool_use" | "reference_answer_accuracy" | "factual_correctness" | "hallucinations" | "completeness" | "toxicity" | "bias" | "maliciousness" | "nsfw" | "taboo" | "jailbreak" | "prompt_leakage",
        "priority": "p0" | "p1" | "p2" | "p3",
        "status": "active" | "future" | "deprecated",   // "archived" filtered out
        "tags": [],
        "created_at": "..."
      }
    ],
    "archived_spec_count": 0
  },
  "evals": [
    {
      "eval_id": "...",
      "name": "...",
      "description": "..." | null,
      "template": "kiln_requirements" | "desired_behaviour" | "kiln_issue" | "tool_call" | "toxicity" | "bias" | "maliciousness" | "factual_correctness" | "jailbreak" | "rag" | null,
      "default_judge_config_id": "..." | null,     // = Eval.current_config_id; null => no default judge configured
      "output_scores": [{"name": "...", "type": "five_star" | "pass_fail" | "pass_fail_critical"}],
      "favourite": false,
      "created_at": "..."
    }
  ],
  "tool_servers": {
    "items": [
      {
        "id": "...",
        "name": "...",
        "type": "remote_mcp" | "local_mcp" | "kiln_task",
        "description": "..." | null,
        "created_at": "..."
      }
    ],
    "archived_tool_server_count": 0
  },
  "run_configs": {
    "default_run_config_id": "..." | null,
    "items": [
      {
        "id": "...",
        "name": "...",
        "description": "..." | null,
        "type": "kiln_agent" | "mcp",
        "model_name": "..." | null,            // kiln_agent only
        "model_provider": "..." | null,        // kiln_agent only; raw provider id (not friendly name)
        "prompt_id": "..." | null,             // kiln_agent only
        "tool_ids": ["mcp::...", "kiln_tool::rag::...", "kiln_tool::<builtin>", "kiln_task::...", "kiln_unmanaged::..."],
        "skill_ids": ["kiln_tool::skill::..."],
        "starred": false,
        "created_at": "..."
      }
    ]
  },
  "fine_tunes": [
    {
      "id": "...",
      "name": "...",
      "description": "..." | null,
      "provider": "...",
      "base_model_id": "...",
      "fine_tune_model_id": "..." | null,   // null until job completes
      "latest_status": "unknown" | "pending" | "running" | "completed" | "failed",
      "created_at": "..."
    }
  ],
  "prompt_optimization_jobs": [
    {
      "id": "...",
      "name": "...",
      "model_name": "..." | null,           // resolved from target_run_config_id
      "model_provider": "..." | null,       // resolved from target_run_config_id
      "latest_status": "pending" | "running" | "succeeded" | "failed" | "cancelled",
      "created_prompt_id": "..." | null,    // set when the job produced a new prompt
      "created_at": "..."
    }
  ],
  "skills": {
    "items": [
      {
        "id": "...",
        "name": "...",
        "description": "...",
        "created_at": "..."
      }
    ],
    "archived_skill_count": 0
  },
  "connected_providers": {
    "openai": {},
    "anthropic": {},
    "openrouter": {}
  }
}
```

### Per-section notes

**project / task**
- Fields mirror what the UI shows in the project-picker and task detail views, plus `input_json_schema`, `output_json_schema`, and `default_run_config_id` which the agent explicitly needs.
- `Task.description` and `Project.description` are nullable team-facing text — not used in prompts (`project.py:38`, `task.py:147`).
- `Task.instruction` is the canonical "prompt" the overview truncates (`task.py:151-153`).

**dataset**
- `by_rating` only uses the five-star scale. Runs with any non-five-star rating type bucket into `"unrated"` (shouldn't happen per user; safe fallback).
- `by_source` always includes all four enum keys even when zero (`task_output.py:166`).
- `by_tag` matches the aggregation the UI already does client-side (`app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/+page.svelte:244`). A run with two tags contributes to both tags.
- `archived_document_count` key only exists once Document gains an archive flag. Until then it's omitted.

**docs**
- `by_tag` reuses the logic from the existing `/api/projects/{project_id}/documents/tag_counts` endpoint (`libs/server/kiln_server/document_api.py:1168`) — call it internally or inline the aggregation.
- `by_kind` matches the `Kind` enum (`extraction.py:36-42`).
- Documents have no archive flag; the `archived_document_count` row is omitted until one is added (see cross-cutting rule: no flag → no count key).

**search_tools**
- Fields match the list-view columns in `app/web_ui/src/routes/(app)/docs/rag_configs/[project_id]/+page.svelte`.
- Sub-config IDs (extractor/chunker/embedding/vector store/reranker) are deliberately excluded — they're plumbing, not agent-relevant.

**prompts**
- `type` is the exact label the UI shows in the prompts table (`app/web_ui/.../prompts/.../+page.svelte:279`), derived by `getPromptType(prompt_id, generator_id)` in `app/web_ui/.../prompt_generators/prompt_generators.ts:102`.
- List includes both persisted `Prompt` rows and virtual prompts: fine-tune prompts, frozen run-config snapshots, and every built-in generator. Source: `/api/projects/.../tasks/.../prompts` returns `PromptResponse{generators, prompts}` (`libs/server/kiln_server/prompt_api.py:144-181`); the agent_overview endpoint merges both into one flat list.
- **Base task prompt coverage.** The "base task prompt" in Kiln is `Task.instruction` (and optionally `Task.thinking_instruction`) — the UI surfaces these via a dedicated "Base Task Prompt" card, not a prompt row. The raw text is already returned in the `task.instruction` / `task.thinking_instruction` fields of this response. Its *callable* representation in the prompts list is the built-in generator `simple_prompt_builder`, which renders `task.instruction` verbatim at call time; it's included in the merged list as a normal entry with `id: "simple_prompt_builder"`. So the agent can see the base prompt two ways: as raw text in the task block, and as a selectable prompt id in the prompts list.
- **Shared code:** port `getPromptType` to a Python helper in `libs/core/kiln_ai/` (e.g., `prompt_type.py`), make the Python API compute `type` server-side, and switch the Svelte UI to consume the server-computed `type` instead of re-deriving it client-side. One source of truth.

**specs**
- `definition` is deliberately excluded (user: too long; UI list view also omits it — `app/web_ui/src/routes/(app)/specs/.../+page.svelte:117-129`).
- `spec_type` is the raw enum string. The UI formats it via `formatSpecType` (`app/web_ui/src/lib/utils/formatters.ts:199`) — purely a display concern. We return the raw value; the agent can read the enum directly.
- "Template" in UI = `spec_type` (not `Eval.template`). For an agent, knowing the spec_type is what matters.

**evals**
- `template` is `Eval.template` (the `EvalTemplateId` enum, `eval.py:34-49`), nullable.
- `default_judge_config_id` exposes the default judge (or null). Sourced from `Eval.current_config_id`; renamed in the API response for clarity (`current_config_id` is cryptic on its own; `default_judge_config_id` makes the role explicit).
- `output_scores` is the list of score dimensions this eval measures, each with a `name` (e.g., "Accuracy", "Hallucination") and a `type` (five_star / pass_fail / pass_fail_critical). Included because it tells the agent *what the eval checks* — an agent asked "how well does this task score on hallucination?" can see which eval has a score named "Hallucination" instead of running every eval to find out. The UI treats these as first-class column headers in the eval results table for the same reason.
- Evals have no archive flag; nothing to filter.

**tool_servers**
- No `tool_count`: for MCP servers it's not knowable without a live call, and for `kiln_task` it's always 1 — neither is useful enough to justify a field.
- `is_archived` lives at `properties.is_archived` (`external_tool_server.py`); the endpoint filters it out of `items` and adds it to the count.

**run_configs**
- `default_run_config_id` is stored on `Task` (`task.py:172`).
- Per-config fields mirror the UI summary card (`app/web_ui/src/lib/ui/run_config_component/run_config_summary.svelte`) plus `description` and `id` which the UI summary omits but an agent needs.
- `tool_ids` and `skill_ids` are split by prefix (`kiln_tool::skill::` → skill_ids, everything else → tool_ids), matching the UI split helper `split_tool_and_skill_ids` in `app/web_ui/src/lib/stores/tools_store.ts:83`. Skills are a distinct backend concept (separate model, separate UI page) so they get their own list.
- Noise fields (`temperature`, `top_p`, `thinking_level`, `structured_output_mode`, frozen prompt snapshot content) are omitted.
- `starred` is the datamodel field name; returned verbatim.
- No archive.

**fine_tunes**
- All fine-tunes are returned regardless of status (matches what the UI fine-tunes page shows — `app/web_ui/src/routes/(app)/fine_tune/[project_id]/[task_id]/+page.svelte`). The agent may care about pending/failed jobs for status questions, not just model selection.
- `fine_tune_model_id` is `null` until the job completes — the agent can tell from `latest_status` whether the entry is usable.

**prompt_optimization_jobs**
- Short summary only. `model_name` / `model_provider` are resolved server-side by reading the job's `target_run_config_id` and inlining its model fields — keeps the agent from having to cross-reference the run_configs section.
- `latest_status` uses the raw enum from the datamodel (`prompt_optimization_job.py:25-28`): `pending`, `running`, `succeeded`, `failed`, `cancelled`. Status is not real-time (per datamodel docstring) — noted here so the agent doesn't assume freshness.
- `created_prompt_id` points at the produced prompt when one exists; the prompt itself shows up in the `prompts` list under the normal type-derivation rules.
- No archive flag; no filtering.

**skills**
- Per-skill body (SKILL.md content) is **not** included — it's rarely small and the agent can fetch it on demand.
- `is_archived` filtered, `archived_skill_count` reported.

**connected_providers**
- Dict keyed by `ModelProviderName` enum value (`libs/core/kiln_ai/datamodel/datamodel_enums.py:96-118`). Valid keys: `openai`, `groq`, `amazon_bedrock`, `ollama`, `openrouter`, `fireworks_ai`, `kiln_fine_tune`, `kiln_custom_registry`, `openai_compatible`, `anthropic`, `gemini_api`, `azure_openai`, `huggingface`, `vertex`, `together_ai`, `siliconflow_cn`, `cerebras`, `docker_model_runner`.
- **Only connected providers appear** (those where `provider_enabled(name)` in `libs/core/kiln_ai/adapters/provider_tools.py:29` returns true). Agents that want the full enum of possible providers can read the enum directly; this dict is the "what can actually run right now" view.
- Values are currently `{}` (empty object). Object shape is chosen over a list so we can add per-provider metadata later (e.g., `model_count`, `has_api_key_configured`, `display_name`) without a breaking change.
- No archive concept.

### Explicitly excluded from agent_overview

These are top-level child types of Project or Task we decided *not* to include, with reasoning:

- `ExtractorConfig`, `ChunkerConfig`, `EmbeddingConfig`, `VectorStoreConfig`, `RerankerConfig` — RAG pipeline plumbing composed by `RagConfig`. Agent should only see the `search_tools` (RagConfig) it can actually call; these aren't agent-actionable.
- `DatasetSplit` — used by evals internally. No agent action hinges on it.
- `SyntheticDataGenerationSessionConfig` — transient job, not agent-actionable.
- `TaskRequirement` — deprecated (replaced by Specs).
- `Feedback` (child of TaskRun) — run-internal.
- `EvalRun` (child of EvalConfig) — summarized via `eval_results_summary`.

---

## Endpoint 2: all_tasks

`GET /api/all_tasks`

Workspace directory. Agent uses this when the user asks about other tasks/projects, not at startup.

### Response

```jsonc
{
  "projects": [
    {
      "id": "...",
      "name": "...",
      "description": "..." | null,
      "created_at": "...",
      "tasks": [
        {
          "id": "...",
          "name": "...",
          "description": "..." | null,
          "instruction": "first 100 words …",
          "instruction_truncated": true,
          "created_at": "..."
        }
      ]
    }
  ]
}
```

No archive filtering (no archive flag exists on Project or Task).

Response is unbounded in list length. For multi-hundred-task workspaces this could be large; out of scope for v1 — revisit if it becomes a problem.

---

## Endpoint 3: eval_results_summary

`GET /api/projects/{project_id}/tasks/{task_id}/eval_results_summary`

Server-side fan-out of the existing `score_summary` endpoint across every eval × eval_config for a task.

### Response

```jsonc
{
  "evals": [
    {
      "eval_id": "...",
      "eval_name": "...",
      "default_judge_config_id": "..." | null,   // = Eval.current_config_id
      "run_configs": [
        {"id": "...", "name": "..."}             // one place to map run_config_id -> name
      ],
      "eval_configs": [
        {
          "eval_config_id": "...",
          "eval_config_name": "...",
          "is_default": true,
          "summary": {
            "results": { "<run_config_id>": { "<score_key>": { "mean_score": 0.0 } } },
            "run_config_percent_complete": { "<run_config_id>": 0.0 },
            "dataset_size": 0
          }
        }
      ]
    }
  ]
}
```

### Notes

- `summary` preserves the existing `EvalResultSummary` shape verbatim (`app/desktop/studio_server/eval_api.py:289`). Keys in `summary.results` are run_config IDs; the `run_configs` map at the eval level lets the agent look up names without a separate call. Per-run-config completion is available in `summary.run_config_percent_complete` (same granularity the UI shows in `run_config_comparison_table.svelte:154-157`).
- `is_default` is `(eval_config_id == Eval.current_config_id)`.
- No query params. Dataset filter is implicit via `eval.eval_set_filter_id` (same as today).

### Implementation: heavy reuse via extraction

The existing `/score_summary` route handler (`app/desktop/studio_server/eval_api.py:1005-1110`) contains ~100 lines of aggregation logic inline. Before building the wrapper, extract the core aggregation into a plain, reusable function:

```python
# new helper — pure, no FastAPI deps
def compute_score_summary(
    task: Task,
    eval: Eval,
    eval_config: EvalConfig,
    task_run_configs: list[TaskRunConfig],
    expected_dataset_ids: set[ID_TYPE],
) -> EvalResultSummary:
    # body = existing lines 1035–1109, parameterised instead of fetched
```

Then:

- **Existing `/score_summary` endpoint** becomes a thin wrapper: fetch `task`, `eval`, `eval_config`, `task_run_configs`, compute `expected_dataset_ids`, call `compute_score_summary`. Same behavior, same response, same route.
- **New `/eval_results_summary` endpoint** fetches `task` and `task_run_configs` **once**. Caches `expected_dataset_ids` per `eval.eval_set_filter_id` (distinct filter IDs are rare). Nested loop over `task.evals()` × `eval.configs()` calls the same `compute_score_summary` helper. No logic is duplicated.

Net-new code for the wrapper is just: the route, the outer loop, the response-shape wrapper (`{eval_id, eval_name, default_judge_config_id, run_configs, eval_configs[]}`). All scoring math is reused verbatim.

---

## Out of scope (v1)

- Returning per-run details (TaskRun contents) in any overview — the agent fetches individual runs by ID on demand.
- Returning Skill body (SKILL.md contents) — on-demand fetch.
- Returning ExtractorConfig / ChunkerConfig / etc. detail.
- Pagination of any list. All lists are returned in full.
- Caching. All endpoints compute on every request. Acceptable given pure file-read costs; revisit if a workspace grows large enough to hurt.
