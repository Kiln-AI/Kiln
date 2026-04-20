---
status: complete
---

# Agent Info Trim

Follow-up to the `agent_api_info` project. The three agent APIs (`agent_overview`, `all_tasks`, `eval_results_summary`) shipped and work well — but the `agent_overview` payload is too verbose. Trim it back: fewer tokens, better signal-to-noise ratio for the chat agent.

**Scope:** this project is specifically for the `agent_overview` endpoint (and by extension the shared truncation helpers). The other two endpoints (`all_tasks`, `eval_results_summary`) are out of scope unless a change is explicitly called out.

## Changes

### Some sections reduced to counts

Progressive disclosure: tell the model these entity types exist so it knows to fetch them if needed, but don't include the detail inline. Reduce to a single-key dict:

```jsonc
fine_tunes: { "total_count": N }
prompt_optimization_jobs: { "total_count": N }
```

### Task instruction: more aggressive truncation

- Truncate `task.instruction` to **70 words** (down from current 300).
- Drop the `instruction_truncated: bool` field. Instead, when text is truncated, append a literal sentinel to the end: `[...truncated, load task for full instructions]`. Clearer to the model than a separate bool.

### Drop thinking_instruction

Remove `task.thinking_instruction` and `task.thinking_instruction_truncated` entirely. Space-saving.

### Truncation-list format for long lists

`run_configs` and `prompts` can get long with older values the model is unlikely to need. Introduce a truncation list format:

```jsonc
prompts: { "total": 24, "showing": "5 of 24", "items": [ /* 5 items */ ] }
```

```jsonc
prompts: { "total": 4, "showing": "4 of 4", "items": [ /* 4 items */ ] }
```

**Inclusion rule:** include all starred/favourited items (all of them). If that set has fewer than 5, pad to 5 using `created_at` timestamp (latest wins).

### Drop created_at everywhere

Remove `created_at` from every response block in `agent_overview`. Too many tokens, not enough value for the agent.
