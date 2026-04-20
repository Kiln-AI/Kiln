---
status: complete
---

# Architecture: Agent API Info

Single architecture doc — the project is 3 endpoints with small, focused internals. No component breakout needed.

## File layout

Endpoints are split by functional domain, not by "it's for the agent." Only `agent_overview` is broad-spectrum agent glue (aggregating across every entity type) — it gets its own file. The other two extend existing domain files.

### New files

| File | Role |
|---|---|
| `app/desktop/studio_server/agent_api.py` | `agent_overview` endpoint + response models + local aggregation helpers |
| `app/desktop/studio_server/test_agent_api.py` | Endpoint + helper tests for agent_overview |
| `libs/core/kiln_ai/datamodel/prompt_type.py` | `prompt_type_label(prompt_id, generator_id)` — ported from the TS `getPromptType` |
| `libs/core/kiln_ai/datamodel/test_prompt_type.py` | Unit tests incl. golden table mirroring TS |

### Modified files

| File | Change |
|---|---|
| `libs/server/kiln_server/task_api.py` | Add `all_tasks` endpoint + its response models (`AllTasksResponse`, `AllTasksProject`, `AllTasksTask`). Sits beside existing task endpoints. |
| `app/desktop/studio_server/eval_api.py` | Two changes: (a) extract score aggregation into module-level `compute_score_summary(...)` — existing `/score_summary` route becomes a thin wrapper, no behavior change; (b) add `eval_results_summary` endpoint + its response models. Sits beside `/score_summary`. |
| `libs/server/kiln_server/prompt_api.py` | Add `type: str` to `ApiPrompt`; compute via `prompt_type_label`. |
| `libs/server/kiln_server/test_task_api.py` | Append `all_tasks` tests. No modifications to existing tests. |
| `app/desktop/studio_server/test_eval_api.py` | Append `eval_results_summary` tests and test the extraction preserves behavior. No modifications to existing tests. |
| `app/desktop/studio_server/server.py` (or wherever `connect_*_api` calls are wired) | Call `connect_agent_api(app)`. |
| `app/web_ui/src/routes/(app)/prompts/[project_id]/[task_id]/+page.svelte` | Use `prompt.type` from the API response; delete the `getPromptType(...)` call at line 279 and the import. |
| `app/web_ui/src/routes/(app)/prompts/[project_id]/[task_id]/prompt_generators/prompt_generators.ts` | Delete `getPromptType` (lines 102-116). |
| `app/web_ui/src/lib/api_schema.d.ts` (generated) | Regenerated via `generate_schema.sh` to pick up the new `type` field and the 3 new endpoints. |

### Not modified

- `libs/core/kiln_ai/tools/built_in_tools/kiln_api_call_tool.py` — no tool change needed. The chat agent's existing `call_kiln_api` tool already hits arbitrary Kiln REST paths; the new endpoints inherit access via `openapi_extra=ALLOW_AGENT`.

---

## Component breakdown

### `agent_api.py`

Top-of-file: response Pydantic models defined in the same file (i.e., `class X(BaseModel): ...` at module top, not imported from a separate models module). This matches the `eval_api.py` pattern — that file has 16+ inline response models. One class per nested shape in the spec:

```
AgentOverviewProject, AgentOverviewTask, AgentOverviewDataset,
AgentOverviewDocs, AgentOverviewSearchTool, AgentOverviewSearchTools,
AgentOverviewPrompt, AgentOverviewSpec, AgentOverviewSpecs,
AgentOverviewEval, AgentOverviewOutputScore,
AgentOverviewToolServer, AgentOverviewToolServers,
AgentOverviewRunConfig, AgentOverviewRunConfigs,
AgentOverviewFineTune, AgentOverviewPromptOptimizationJob,
AgentOverviewSkill, AgentOverviewSkills,
AgentOverview
```

### `task_api.py` (additions)

New response models (inline at module top, same pattern):

```
AllTasksTask, AllTasksProject, AllTasksResponse
```

New route `all_tasks` added alongside the existing task endpoints.

### `eval_api.py` (additions)

New response models (inline at module top, same pattern):

```
EvalResultsSummaryRunConfigRef,
EvalResultsSummaryEvalConfig,
EvalResultsSummaryEval,
EvalResultsSummaryResponse
```

New route `eval_results_summary` added alongside `/score_summary`. Plus the extraction of `compute_score_summary` (see "`eval_api.py` refactor" below).

Module-private helpers (not exported — prefixed `_`):

```python
def _truncate_to_words(text: str | None, max_words: int) -> tuple[str | None, bool]:
    """Returns (possibly truncated text, whether it was truncated). None -> (None, False)."""

def _split_tool_and_skill_ids(tool_ids: list[str]) -> tuple[list[str], list[str]]:
    """Skill ids = those starting with 'kiln_tool::skill::'. Rest are tool ids."""

def _dataset_stats(task: Task) -> AgentOverviewDataset:
    """Single pass over task.runs(readonly=True). Populates total_count, by_tag, by_source, by_rating."""

def _docs_stats(project: Project) -> AgentOverviewDocs:
    """Single pass over project.documents(readonly=True). Populates doc_count, by_tag, by_kind."""

def _search_tools_block(project: Project) -> AgentOverviewSearchTools: ...
def _tool_servers_block(project: Project) -> AgentOverviewToolServers: ...
def _skills_block(project: Project) -> AgentOverviewSkills: ...
def _specs_block(task: Task) -> AgentOverviewSpecs: ...
def _evals_block(task: Task) -> list[AgentOverviewEval]: ...
def _prompts_block(task: Task) -> list[AgentOverviewPrompt]: ...
def _run_configs_block(
    task: Task, task_run_configs: list[TaskRunConfig]
) -> AgentOverviewRunConfigs: ...

def _connected_providers_block() -> dict[str, dict]:
    """Iterate ModelProviderName enum; for each where provider_enabled(name) is True,
    include the string key with {} value."""

def _fine_tunes_block(task: Task) -> list[AgentOverviewFineTune]: ...
def _prompt_optimization_jobs_block(
    task: Task, run_configs_by_id: dict[str, TaskRunConfig]
) -> list[AgentOverviewPromptOptimizationJob]: ...
```

Route registration: `def connect_agent_api(app: FastAPI):` with nested `@app.get(...)` — matches the project's universal pattern (e.g., `project_api.py:45`). The `all_tasks` and `eval_results_summary` routes are added inside the existing `connect_*_api` functions in their respective files.

All three routes carry `openapi_extra=ALLOW_AGENT` (defined at `libs/server/kiln_server/utils/agent_checks/policy.py:31`). Without this, the chat agent's `call_kiln_api` tool refuses to call them.

### `prompt_type.py` (new)

```python
_GENERATOR_LABELS: dict[str, str] = {
    "kiln_prompt_optimizer": "Kiln Optimized",
    "few_shot_prompt_builder": "Few-Shot",
    "multi_shot_prompt_builder": "Many-Shot",
    "repairs_prompt_builder": "Repair Multi-Shot",
    "simple_chain_of_thought_prompt_builder": "Chain of Thought",
    "few_shot_chain_of_thought_prompt_builder": "Chain of Thought + Few Shot",
    "multi_shot_chain_of_thought_prompt_builder": "Chain of Thought + Many Shot",
}

def prompt_type_label(prompt_id: str, generator_id: str | None) -> str:
    if prompt_id.startswith("fine_tune_prompt::"): return "Fine-Tune"
    if prompt_id.startswith("task_run_config::"): return "Frozen"
    if generator_id:
        label = _GENERATOR_LABELS.get(generator_id)
        if label: return label
    if prompt_id.startswith("id::"): return "Custom"
    return "Unknown"
```

Labels are copied verbatim from the TS `getPromptType` (`app/web_ui/.../prompt_generators.ts:102-116`). Any change to label text must update both until the TS helper is removed.

### `eval_api.py` refactor

Today: lines 1035-1109 are aggregation logic inline inside the FastAPI handler `get_eval_config_score_summary` (declared at 1005).

After: extract into a module-level function.

```python
def compute_score_summary(
    task: Task,
    eval: Eval,
    eval_config: EvalConfig,
    task_run_configs: list[TaskRunConfig],
    expected_dataset_ids: set[ID_TYPE],
) -> EvalResultSummary:
    # body = current lines 1035–1109, with parameters instead of fetches
```

Existing route becomes ~10 lines:
```python
task = task_from_id(project_id, task_id)
eval = eval_from_id(project_id, task_id, eval_id)
eval_config = eval_config_from_id(project_id, task_id, eval_id, eval_config_id)
task_run_configs = get_all_run_configs(project_id, task_id)
expected_dataset_ids = dataset_ids_in_filter(task, eval.eval_set_filter_id, readonly=True)
if not expected_dataset_ids:
    raise HTTPException(400, "No dataset ids in eval set filter...")
return compute_score_summary(task, eval, eval_config, task_run_configs, expected_dataset_ids)
```

The new `eval_results_summary` endpoint loads `task` and `task_run_configs` once, caches `expected_dataset_ids` per `eval.eval_set_filter_id`, and calls `compute_score_summary` in the inner loop.

---

## Data flow per endpoint

### agent_overview

```
task_from_id(project_id, task_id)
project_from_id(project_id)  (via task.parent_project())
get_all_run_configs(project_id, task_id)  (includes finetune-run-configs)

Build AgentOverview from:
  project → _project_block
  task → _task_block (instruction truncated, schemas passed through)
  task.runs(readonly=True) → _dataset_stats (single pass)
  project.documents(readonly=True) → _docs_stats (single pass)
  project.rag_configs() → _search_tools_block (filter is_archived)
  merged generators + task.prompts() → _prompts_block (see prompt list note)
  task.specs() → _specs_block (filter status == "archived")
  task.evals() → _evals_block
  project.external_tool_servers() → _tool_servers_block (filter properties.is_archived)
  task + task_run_configs → _run_configs_block (split tool/skill ids)
  task.finetunes() → _fine_tunes_block
  task.prompt_optimization_jobs() + run_configs_by_id → _prompt_optimization_jobs_block
  project.skills() → _skills_block (filter is_archived)
  ModelProviderName × provider_enabled() → _connected_providers_block
```

**Prompt list**: mirror what the existing `/api/projects/.../tasks/.../prompts` endpoint returns. That endpoint (`prompt_api.py:144-181`) returns `PromptResponse{generators, prompts}` where `generators` is the hardcoded list of built-in prompt generators (including `simple_prompt_builder`, which surfaces `task.instruction` as a callable prompt id). The agent_overview merges both into a single flat list. Virtual prompts (`fine_tune_prompt::<finetune_id>`, `task_run_config::<run_config_id>`) are already handled by the existing endpoint via the generators/prompts split — we just merge them.

**Connected providers**: iterate the `ModelProviderName` enum. For each name, call `provider_enabled(name)` from `libs/core/kiln_ai/adapters/provider_tools.py:29`. If true, include the string enum value as a key with `{}` value. No existing GET endpoint aggregates this today — the logic is exposed via the core helper, not yet surfaced in a REST endpoint.

### all_tasks

```
for project_path in Config.shared().projects_paths():
    project = project_from_path(project_path)
    for task in project.tasks(readonly=True):
        include {id, name, description, instruction (truncated 100), created_at}
```

Output is nested by project. No cross-project aggregation.

### eval_results_summary

```
task = task_from_id(...)
task_run_configs = get_all_run_configs(...)

for eval in task.evals():
    expected_dataset_ids = dataset_ids_in_filter(task, eval.eval_set_filter_id, readonly=True)

    eval_configs_out = []
    for eval_config in eval.configs():
        if not expected_dataset_ids:
            summary = EvalResultSummary(results={}, run_config_percent_complete={}, dataset_size=0)
        else:
            summary = compute_score_summary(task, eval, eval_config, task_run_configs, expected_dataset_ids)
        eval_configs_out.append({ eval_config_id, eval_config_name, is_default, summary })

    evals_out.append({ eval_id, eval_name, default_judge_config_id, run_configs: [{id, name} for rc in task_run_configs], eval_configs: eval_configs_out })
```

Single `task.runs()` read (memory-cached by the datamodel; `compute_score_summary` and `dataset_ids_in_filter` both use `readonly=True`).

---

## Key design decisions

### 1. Pydantic response models everywhere
Dicts would give no OpenAPI schema, breaking the generated TS client and our `check_schema.sh` contract. All responses are explicit models, inline in `agent_api.py` (matches `eval_api.py` convention of 16+ inline models).

### 2. No caching across requests
Every request recomputes. Underlying datamodel loads are already memory-cached by the Kiln base model. Desktop app is single-user. Staleness is worse than a sub-second recompute.

### 3. Single-pass aggregation
`_dataset_stats` and `_docs_stats` iterate once, populating multiple dicts in the same loop. Not three passes per section.

### 4. No filter caching in `eval_results_summary`

`dataset_ids_in_filter(task, filter_id, readonly=True)` is called once per eval (not per eval × config). The work is linear in `task.runs()` and well under 10k runs in realistic workspaces. Not worth caching — keep the implementation simple.

### 5. Skills list is project-scoped
Skills are children of `Project` (`project.py:27`), not `Task`. The `skills` block reads `project.skills()`, same pattern as search tools and tool servers.

### 6. Prompt type: single source of truth in Python
The TS helper is deleted; TS now reads `prompt.type` from the API response. Until the UI switchover lands, both live in parallel — tests on the Python port use the same golden table as the TS implementation, so divergence is caught immediately.

### 7. `eval_results_summary` handles empty dataset filters gracefully
The existing `/score_summary` endpoint raises `HTTPException(400, "No dataset ids in eval set filter...")` when an eval's filter matches zero runs. In the wrapper, we do NOT propagate that 400 — one misconfigured eval shouldn't fail the whole overview. Instead, emit the eval entry with an empty `EvalResultSummary(results={}, run_config_percent_complete={}, dataset_size=0)`. The existing endpoint's behavior is unchanged.

---

## Error handling

| Case | Response |
|---|---|
| Unknown project_id | 404 from `project_from_id` (reuse) |
| Unknown task_id | 404 from `task_from_id` (reuse) |
| File read error mid-iteration | Propagate as 500; matches existing endpoint behavior |
| Empty eval set filter (in `eval_results_summary`) | Return `dataset_size: 0` for that eval; don't 400 |
| Empty task (no dataset / no prompts / etc.) | 200 OK; all keys present with empty values (see spec's "field presence" rule) |

Logging: none beyond what existing endpoints produce. No new log sites.

---

## Testing strategy

Framework: pytest + FastAPI `TestClient`. Fixtures mirror `app/desktop/studio_server/test_eval_api.py:57-66`.

**Additive-only rule.** Existing tests are not modified. In particular:
- `test_eval_api.py` tests for `/score_summary` stay as-is — they lock in current behavior of the endpoint being refactored. If the extraction to `compute_score_summary(...)` breaks anything observable, those tests fail.
- `test_prompt_api.py` tests for `/prompts` stay as-is — they still pass because `type` is an additive field.
- `test_task_api.py` existing tests stay as-is — `all_tasks` is appended.

New endpoints get their own full test coverage (happy paths, empty fixtures, edge cases, error handling) — not just behavioral-equivalence shims.

### Unit tests — helpers

- `test_prompt_type.py` — golden table test. One case per branch (fine_tune, task_run_config, each of the 7 generator ids, `id::`, unknown). Table values copied directly from the TS test expectations (if any — otherwise copied from the TS implementation's label strings).
- `_truncate_to_words`: under limit, at limit, one word over limit, many words over, empty string, `None`. Verify `instruction_truncated` bool and ellipsis shape.
- `_split_tool_and_skill_ids`: mixed list, all skills, all tools, empty list.

### Unit tests — per-block aggregators

- `_dataset_stats`: fixtures with known tag/source/rating mixes; verify every dict key present (including zeros) and counts correct. Verify a run with two tags contributes to both. Verify unrated bucket handles missing rating and non-five-star rating types.
- `_docs_stats`: similar; verify kind buckets.
- `_search_tools_block` / `_tool_servers_block` / `_skills_block` / `_specs_block`: create archived + active fixtures; verify archived excluded and `archived_*_count` matches.

### Endpoint tests — happy paths

- `agent_overview`: realistic task fixture. Snapshot-like assertion on the top-level shape (all keys present), then targeted assertions on each block's semantics.
- `all_tasks`: 2 projects × 2 tasks each; verify nested shape; verify instruction truncation at 100 words.
- `eval_results_summary`: task with 3 evals × 2 configs × 4 run_configs; verify nested shape.

### Endpoint tests — edge cases

- Empty task: every list is `[]`, every dict is present with zero counts, every `archived_*_count` is `0`. `default_run_config_id` is `null`.
- Instruction just over 300 words: truncated to exactly 300, ends with ` …`, `instruction_truncated == True`.
- Instruction exactly 300 words: not truncated, no ellipsis, `instruction_truncated == False`.
- Unknown project/task → 404.

### Behavioral-equivalence test (`eval_results_summary` ↔ `score_summary`)

Given a populated fixture, for each `(eval, eval_config)` pair, assert that the `summary` field returned by `eval_results_summary` equals what `/score_summary` returns for the same `(eval_id, eval_config_id)`. Guards against drift when the refactor lands.

### Performance sanity (`eval_results_summary`)

Instrument `task.runs(...)` with a call counter; assert it's called **once** over an `eval_results_summary` request that covers N evals × M configs. Catches accidental regression where the helper re-fetches per iteration.

### Coverage target

New modules ≥90% line coverage. Existing project convention.

---

## Dependencies

No new third-party dependencies. Uses existing FastAPI, Pydantic v2, `httpx` (unchanged — chat agent tool).

## OpenAPI + TS client regeneration

After endpoint definition lands, `app/web_ui/src/lib/generate_schema.sh` regenerates `api_schema.d.ts`. CI check `check_schema.sh` enforces this is up to date.

## Rollout

- No DB migration (no persisted data).
- Additive endpoints.
- Existing `/score_summary` endpoint unchanged in shape and behavior (internals refactored only).
- `ApiPrompt` gains a `type: str` field — additive, older TS clients ignore unknown fields, so safe.
- TS `getPromptType` deletion is a follow-up UI task; both can coexist during rollout.
