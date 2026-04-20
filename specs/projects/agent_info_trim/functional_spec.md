---
status: complete
---

# Functional Spec: Agent Info Trim

Follow-up trim of the `agent_overview` endpoint plus one small change to the former `all_tasks` endpoint. Parent spec: `specs/projects/agent_api_info/functional_spec.md`. This document describes only the deltas.

`eval_results_summary` is unchanged.

### Rename: `all_tasks` → `task_summaries`

The endpoint is renamed from `GET /api/all_tasks` to `GET /api/task_summaries`. Reasoning: "all_tasks" implies the response is a complete enumeration of tasks with full fidelity, but the endpoint truncates `task.instruction` — a deliberate divergence from typical list-API conventions where list items mirror the full model. The new name signals that entries are summaries, not full tasks.

The endpoint's route handler gets a short docstring calling this out:

```python
"""Return a workspace-wide list of projects and their tasks, with truncated
task.instruction values. Unlike typical list endpoints, entries here are
intentionally lossy — the shape is tuned for LLM-agent context efficiency,
not for driving UIs that need the full Task model."""
```

No Svelte call sites exist for the old path (confirm during implementation); this is a straight rename, not a dual-endpoint rollout.

## Goals

1. Cut token count in `agent_overview` without removing any capability signal.
2. Replace bool-plus-maybe-truncated-string with an inline sentinel the model reads naturally.
3. Introduce a reusable "truncation list" shape for sections with unbounded growth.
4. Keep the API breaking changes contained to this release — all three endpoints shipped together in the prior project, so coordinated updates are acceptable.

## 1. Truncation sentinel replaces `instruction_truncated` (agent_overview + task_summaries)

**Before**

```jsonc
"instruction": "first 300 words …",
"instruction_truncated": true,
```

**After**

```jsonc
"instruction": "first N words [...truncated, load task for full instructions]",
```

Rules:

- When text is truncated: strip trailing whitespace and append a single space + the literal sentinel `[...truncated, load task for full instructions]`. No separator ellipsis. The previous ` …` suffix is **removed**.
- When text is *not* truncated: no sentinel, no changes.
- Applies to both endpoints:
  - `agent_overview` — truncates `task.instruction` to **70 words** (down from 300).
  - `task_summaries` — truncates `task.instruction` to **100 words** (unchanged limit; only the sentinel/bool swap applies).
- The `instruction_truncated: bool` field is removed from both response shapes.
- `null` / empty instruction: emit as-is (no sentinel, no bool).

**Helper change:** A dedicated `truncate_to_words_with_agent_sentinel(text, max_words)` helper in `libs/core/kiln_ai/utils/formatting.py` handles truncation and sentinel appending in one call. It preserves original whitespace in the retained prefix. Callers in `agent_api.py` and `task_api.py` use this helper directly.

## 2. Remove `thinking_instruction` fields from `agent_overview`

Delete both `task.thinking_instruction` and `task.thinking_instruction_truncated` from the `agent_overview` task block. No replacement. The agent can fetch the full task if it needs thinking instructions.

`task_summaries` did not include `thinking_instruction`; unchanged.

## 3. Drop `created_at` everywhere in `agent_overview`

Remove `created_at` from:

- `project`, `task`
- Each item in `search_tools.items`, `specs.items`, `tool_servers.items`, `run_configs.items`, `skills.items`
- Each item in `evals`, `fine_tunes`, `prompt_optimization_jobs`

`task_summaries` also drops `created_at` from each project and task entry — consistent with the "created_at is low-signal" rationale.

## 4. Collapse `fine_tunes` and `prompt_optimization_jobs` to counts

Progressive disclosure: the agent learns these exist but must fetch detail separately.

**Before**

```jsonc
"fine_tunes": [ { /* detailed entries */ } ],
"prompt_optimization_jobs": [ { /* detailed entries */ } ]
```

**After**

```jsonc
"fine_tunes": { "total_count": 0 },
"prompt_optimization_jobs": { "total_count": 0 }
```

Keys are always present. Count is the raw number of entries the old implementation would have returned (no filtering by status). Minimum zero.

## 5. Truncation-list format for `prompts` and `run_configs`

A shared list shape for sections that can grow long. Keys, in order:

```jsonc
{
  "total":   <int>,           // total items in the underlying source (post-archive-filter, if applicable)
  "showing": "<int> of <int>", // "<len(items)> of <total>" — display string mirroring "total"
  "items":   [ /* items */ ]
}
```

`showing` is a formatted string to keep it self-describing in the model's context. It always equals `f"{len(items)} of {total}"`.

### Inclusion rule — `run_configs`

RunConfigs have `starred: bool`. The truncation rule:

1. Start with the set of **all starred** run_configs (no cap — if there are 8 starred, all 8 are returned).
2. If the starred set has fewer than 5 entries, pad from the non-starred pool in `created_at` descending order (latest first) until `items` has 5 entries OR the underlying pool is exhausted, whichever comes first.
3. If `total ≤ 5`, `items` is simply all of them.

**Ordering inside `items`:** starred first (among themselves, `created_at` desc), then padded non-starred (also `created_at` desc). Stable within each group.

`items` shape per run_config — unchanged from the parent spec except `created_at` and `starred` handling:

```jsonc
{
  "id": "...",
  "name": "...",
  "description": "..." | null,
  "type": "kiln_agent" | "mcp",
  "model_name": "..." | null,
  "model_provider": "..." | null,
  "prompt_id": "..." | null,
  "tool_ids": ["..."],
  "skill_ids": ["..."],
  "starred": false
}
```

`starred` is retained inside the item (the agent uses it to tell the difference between "I'm seeing this because the user picked it" and "I'm seeing this because it was recent"). `created_at` is dropped (per §3).

The existing `default_run_config_id` top-level key stays at the section level:

```jsonc
"run_configs": {
  "default_run_config_id": "..." | null,
  "total":   <int>,
  "showing": "<int> of <int>",
  "items":   [ /* see above */ ]
}
```

### Inclusion rule — `prompts`

`Prompt` has **no** `starred`/`favourite` field. Built-in generators and `fine_tune_prompt::` virtual prompts also have no star metadata. Per user decision **(A)**: *no* prompts are treated as starred. The rule simplifies to:

- `items` contains **only real data-model prompts**: persisted `Prompt` rows + `fine_tune_prompt::` virtuals + `task_run_config::` virtuals.
- Built-in prompt generators are **fully excluded** from `items`. Rationale: they're a fixed, well-known set any agent can enumerate from the prompt-generators REST endpoint if needed, and they account for most of the verbosity today.
- Take the 5 most recent from the includable pool by `created_at` desc. If the pool has ≤ 5 entries, return all of them.

`total` counts the includable pool (persisted Prompts + fine_tune_prompt virtuals + task_run_config virtuals). Built-in generators are never counted here.

`items` shape per prompt — unchanged from the parent spec except `created_at` is dropped (per §3):

```jsonc
{
  "id": "id::..." | "fine_tune_prompt::..." | "task_run_config::...",
  "name": "...",
  "type": "Custom" | "Fine-Tune" | "Frozen"
}
```

The `type` union for items in this list is narrowed to just `"Custom"`, `"Fine-Tune"`, `"Frozen"` — the three outcomes `prompt_type_label` can produce for those id shapes. Generator-label values (e.g. `"Chain of Thought"`) no longer appear here because generators are excluded.

### §5a. Sibling field: `generators_from_task_instruction_count`

Built-in generators are excluded from `items`, but the agent still needs to know they exist (so it knows to fetch the prompt-generators endpoint if it wants to pick one). A sibling integer field reports the count:

```jsonc
"prompts": {
  "total": 24,
  "showing": "5 of 24",
  "generators_from_task_instruction_count": 8,
  "items": [ /* up to 5 most recent real prompts */ ]
}
```

**Definition:** the count of built-in prompt generators registered in `prompt_generators` (`libs/server/kiln_server/prompt_api.py:291`). Each of those generators produces a prompt derived from `task.instruction` (+ optionally `task.thinking_instruction`), so "generators from task instruction" describes the set exactly.

At the time of writing there are 8 generators (`simple_prompt_builder`, `few_shot_prompt_builder`, `multi_shot_prompt_builder`, `repairs_prompt_builder`, `simple_chain_of_thought_prompt_builder`, `few_shot_chain_of_thought_prompt_builder`, `multi_shot_chain_of_thought_prompt_builder`, `kiln_prompt_optimizer`). The count is computed at request time from the registered list, not hardcoded.

Full section shape:

```jsonc
"prompts": {
  "total":   <int>,
  "showing": "<int> of <int>",
  "generators_from_task_instruction_count": <int>,
  "items":   [ /* ... */ ]
}
```

Length: `len(items) == min(5, total)`. `showing` is `f"{len(items)} of {total}"`.

## 6. Sections unchanged

Per user decision, the truncation-list format does **not** apply to:

`specs`, `evals`, `search_tools`, `tool_servers`, `skills` — these remain fully-listed as specified in the parent functional spec, minus the `created_at` drop from §3.

Archived filtering + `archived_*_count` siblings for these sections are unchanged.

`connected_providers`, `dataset`, `docs` — unchanged except `created_at` is not present in any of them today.

## Updated `agent_overview` response shape (summary)

For reference — this is the full shape after all changes above. Comments mark what changed vs the parent spec.

```jsonc
{
  "project": {
    "id": "...",
    "name": "...",
    "description": "..." | null
    // created_at removed
  },
  "task": {
    "id": "...",
    "name": "...",
    "description": "..." | null,
    "instruction": "first 70 words [...truncated, load task for full instructions]",
    // instruction_truncated removed
    // thinking_instruction removed
    // thinking_instruction_truncated removed
    "input_json_schema": { ... } | null,
    "output_json_schema": { ... } | null,
    "default_run_config_id": "..." | null
    // created_at removed
  },
  "dataset": { /* unchanged */ },
  "docs": { /* unchanged */ },
  "search_tools": { "items": [ /* no created_at */ ], "archived_search_tool_count": 0 },
  "prompts": {
    "total": 24,
    "showing": "5 of 24",
    "generators_from_task_instruction_count": 8,
    "items": [ /* up to 5 most recent real prompts */ ]
  },
  "specs": { "items": [ /* no created_at */ ], "archived_spec_count": 0 },
  "evals": [ /* no created_at */ ],
  "tool_servers": { "items": [ /* no created_at */ ], "archived_tool_server_count": 0 },
  "run_configs": {
    "default_run_config_id": "..." | null,
    "total": 12,
    "showing": "5 of 12",
    "items": [ /* starred first, then recent; no created_at */ ]
  },
  "fine_tunes": { "total_count": 0 },
  "prompt_optimization_jobs": { "total_count": 0 },
  "skills": { "items": [ /* no created_at */ ], "archived_skill_count": 0 },
  "connected_providers": { /* unchanged */ }
}
```

## Updated `task_summaries` response shape (summary)

```jsonc
{
  "projects": [
    {
      "id": "...",
      "name": "...",
      "description": "..." | null,
      // created_at removed
      "tasks": [
        {
          "id": "...",
          "name": "...",
          "description": "..." | null,
          "instruction": "first 100 words [...truncated, load task for full instructions]"
          // instruction_truncated removed
          // created_at removed
        }
      ]
    }
  ]
}
```

## Edge cases

- **Empty instruction / None**: emit as-is. No sentinel.
- **Instruction with trailing whitespace at the cut point**: strip trailing whitespace from the kept portion before appending the sentinel so there are no double spaces.
- **`total == 0` for prompts**: `items` is `[]`; `showing` is `"0 of 0"`; `total` is `0`; `generators_from_task_instruction_count` still reports the registered-generator count (usually 8).
- **`total == 0` for run_configs**: `items` is `[]`; `showing` is `"0 of 0"`; `total` is `0`; `default_run_config_id` is `null`.
- **Ties in `created_at` desc sort** (rare — separate persists in the same ms): fall back to `id` descending for stable ordering. Not worth a feature-flag; keep it internal.
- **All run_configs starred**: `items` returns all of them; `total == len(items)`. `showing` reflects equality.
- **Starred > 5**: all starred returned, no non-starred padded.

## Out of scope

- Changing `eval_results_summary`.
- Adding a `favourite`/`starred` field to the `Prompt` datamodel.
- Changing the `/api/projects/.../tasks/.../prompts` endpoint (used by the Svelte prompts page). Generators and their UI-facing names stay as-is there.
- Pagination on unbounded sections other than `prompts`/`run_configs` (deferred; user says those two are enough for now).
- Further truncation of `specs[].definition` or other long free-form fields (already excluded from the current spec).

## Testing surface (non-exhaustive)

- Sentinel appended exactly once, in both endpoints, only when truncation occurred.
- `instruction_truncated` / `thinking_instruction` / `thinking_instruction_truncated` absent from both endpoint responses.
- `created_at` absent at every level in both endpoints.
- `fine_tunes` / `prompt_optimization_jobs` are dicts with a single `total_count` key matching actual entity count.
- `prompts.items` contains only persisted Prompts, `fine_tune_prompt::`, and `task_run_config::` virtuals — no built-in generators.
- `prompts.total` and `prompts.showing` count only those real-data-model entries. Empty-prompt fixtures still report `generators_from_task_instruction_count` > 0.
- `generators_from_task_instruction_count` equals `len(prompt_generators)` (currently 8). A synthetic test that appends to `prompt_generators` should see this count rise.
- `run_configs` ordering: all-starred case, starred+padded case, all-padded case, total ≤ 5 case, total > 5 with >5 starred case.
- `showing` string format matches `f"{len(items)} of {total}"`.
- `GET /api/all_tasks` returns 404 (or matches whatever 404 shape FastAPI produces for unknown routes); `GET /api/task_summaries` returns 200.
- OpenAPI/TS client schema regenerated and consuming code compiles (or has been updated — see "Frontend impact" below).

## Frontend impact

`agent_overview` and the old `all_tasks` endpoint are currently consumed only by the chat agent via `call_kiln_api` (not by Svelte pages directly). Schema regeneration (`generate_schema.sh`) will update the generated TS types — no Svelte call sites exist to break. Confirm during implementation by grepping for the old `/api/all_tasks` path, the endpoint's response model names, and the `AllTasks*` Python symbols. Rename/update any test fixtures and assertions that reference the old path.
