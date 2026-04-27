---
status: complete
---

# Phase 3: Enhance agentInfo Descriptions with Entity Names

## Goal

Add entity names to `agentInfo.set()` descriptions on pages that display specific entities. Use the format `entity name: {name ?? '[loading]'}` for async-loaded entities, matching the existing pattern from `edit_project` and `skill_detail` pages.

## Pattern

Since most entity data loads async (onMount), descriptions need `'[loading]'` fallback:

```svelte
$: agentInfo.set({
  name: "Spec Detail",
  description: `Spec detail for spec ID ${spec_id}. Spec name: ${spec?.name ?? '[loading]'}.`,
})
```

The `$:` reactive statement ensures the description updates once the entity loads.

## Pages to Update

### Specs & Evals
1. `specs/[project_id]/[task_id]/[spec_id]/+page.svelte` — add `spec?.name`
2. `specs/[project_id]/[task_id]/[spec_id]/[eval_id]/+page.svelte` — add `evaluator?.name`
3. `specs/[project_id]/[task_id]/[spec_id]/[eval_id]/eval_configs/+page.svelte` — add `evaluator?.name`
4. `specs/[project_id]/[task_id]/[spec_id]/[eval_id]/create_eval_config/+page.svelte` — add `evaluator?.template` or eval name
5. `specs/[project_id]/[task_id]/[spec_id]/[eval_id]/compare_run_configs/+page.svelte` — add `evaluator?.name`
6. `specs/[project_id]/[task_id]/[spec_id]/[eval_id]/[eval_config_id]/[run_config_id]/run_result/+page.svelte` — limited entity data available, may skip

### Tools
7. `tools/[project_id]/tool_servers/[tool_server_id]/+page.svelte` — add `tool_server?.name`
8. `tools/[project_id]/kiln_task/[tool_server_id]/+page.svelte` — add `tool_server?.name`
9. `tools/[project_id]/edit_tool_server/[tool_server_id]/+page.svelte` — add `tool_server?.name`

### Fine-tuning
10. `fine_tune/[project_id]/[task_id]/fine_tune/[finetune_id]/+page.svelte` — add finetune name

### Optimization
11. `optimize/[project_id]/[task_id]/run_config/[run_config_id]/+page.svelte` — add `run_config?.name`
12. `prompt_optimization/[project_id]/[task_id]/prompt_optimization_job/[job_id]/+page.svelte` — add job name

### Docs
13. `docs/extractors/[project_id]/[extractor_id]/extractor/+page.svelte` — add `extractor_config?.name`
14. `docs/library/[project_id]/[document_id]/+page.svelte` — add document name
15. `docs/rag_configs/[project_id]/[rag_config_id]/rag_config/+page.svelte` — add `rag_config?.name`
16. `docs/rag_configs/[project_id]/[rag_config_id]/rag_config/clone/+page.svelte` — add `rag_config?.name`

### Prompts
17. `prompts/[project_id]/[task_id]/saved/[prompt_id]/+page.svelte` — add `prompt_model?.name`
18. `prompts/[project_id]/[task_id]/clone/[prompt_id]/+page.svelte` — add prompt name

### Settings
19. `settings/edit_task/[project_id]/[task_id]/+page.svelte` — add task name (need to check data availability)
20. `settings/clone_task/[project_id]/[task_id]/+page.svelte` — add task name (need to check data availability)

### Dataset
21. `dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte` — limited naming, may skip

### Skills
22. `skills/[project_id]/clone/[skill_id]/+page.svelte` — need to check data availability

## Pages NOT to Update

- Pages without specific entity IDs (list pages, create pages, static pages)
- Pages that already include entity names (edit_project, skill_detail, run page)
- Setup/fullscreen pages (no entities to name)
