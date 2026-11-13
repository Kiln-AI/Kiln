---
status: complete
---

# Phase 4: Kiln web UI removal

## Overview

Remove the Prompt Optimizer from the Kiln web UI: the `/prompt_optimization/**` routes, the prompts-page entry points, the "Automatic Optimization" generator category and its redirect, the prompt-optimization entitlement helper, the type aliases, and the copy that describes the feature. Regenerate `src/lib/api_schema.d.ts` from the Phase 3 Python app so `check_schema.sh` passes again, and delete the unused duplicate `app/web_ui/api_schema.d.ts`. Update the e2e prompts spec and the README. Existing prompts with `generator_id="kiln_prompt_optimizer"` keep their "Kiln Optimized" label, which comes from the server.

## Steps

1. **Delete** `app/web_ui/src/routes/(app)/prompt_optimization/` (whole folder, including `pro_auth/` and `page.test.ts`) and `app/web_ui/api_schema.d.ts`.
2. **`src/lib/ui/kiln_copilot/entitlement_required_card.svelte`:** only the deleted routes use it and its "Learn More" link points at the optimizer docs, so delete it.
3. **`src/lib/prompt_generators.ts`:** remove the "Automatic Optimization" category.
4. **`routes/(app)/prompts/[project_id]/[task_id]/prompt_generators/+page.svelte`:** remove the `kiln_prompt_optimizer` redirect branch in `on_select`; reword the `agentInfo` description so it no longer offers optimization-based approaches.
5. **`routes/(app)/prompts/[project_id]/[task_id]/+page.svelte`:** remove the "Optimizer Jobs" action button and the "Automatically Optimize Your Prompt" banner, and the now-unused `Banner` import.
6. **`src/lib/utils/entitlement_utils.ts`:** remove `checkPromptOptimizationAccess` and the now-unused `createKilnError`/`KilnError` import; change the `checkEntitlements` docstring example to a neutral feature code. Keep `checkEntitlements`.
7. **`src/lib/types.ts`:** remove the `PublicPromptOptimizationJobStatusResponse` and `PromptOptimizationJob` aliases. Remove `JobStatus` too if the regenerated schema no longer has it (nothing else uses the alias).
8. **`src/lib/ui/data_guide_progress_widget.svelte`:** reword the badge comment so it describes the badge styles without pointing at the removed GEPA badges.
9. **`routes/(app)/optimize/[project_id]/[task_id]/optimizers.ts`:** reword the "Refine Prompt" description to drop "automatic optimizers".
10. **`src/lib/api_schema.d.ts`:** run `src/lib/generate_schema.sh`, then `check_schema.sh`.
11. **E2E:**
    - `tests/e2e/act/discover/prompts-management.spec.ts`: drop the "Optimizer Jobs" hint, assertion and expectation from the list-page test; delete the banner test; in the picker test drop "Automatic Optimization" and "Kiln Optimized" from goals, hints and assertions, and assert that "Kiln Optimized" and "Automatic Optimization" are not shown.
    - `tests/e2e/mock_kiln_server/server.ts`: drop "prompt-optimizer" from the header comment.
12. **`README.md`:** remove the "Auto-Optimize" nav link, highlight bullet and docs link; drop the "Optimization, not just evaluation" bullet (it describes the removed optimizer); reword "prompt optimization" in "Why Kiln?" and drop "Auto-Optimize" from the Kiln Pro sentence.
13. **`libs/server/kiln_server/utils/agent_checks/README.md`:** drop the "(e.g. the Prompt Optimizer)" example so the §3.7 grep is clean; the rule stays.
14. **Final check (§3.7):** `git grep -n -i -E '(^|[^a-z])gepa|prompt.optimi|PromptOptimization' -- ':!specs'` returns only the spec-required legacy-folder test in `libs/core/kiln_ai/datamodel/test_task.py`; `git grep -n kiln_prompt_optimizer -- ':!specs'` returns only `prompt_type.py` and its test.

## Tests

- No new unit tests: this phase only deletes UI and copy. The deleted `page.test.ts` covered the deleted routes only.
- `prompts-management.spec.ts` "prompt generators page shows generator categories": "Prompt Generators" and "Manual" categories show; "Automatic Optimization" and "Kiln Optimized" do not.
- `prompts-management.spec.ts` "prompts list page loads with empty state": still passes without the "Optimizer Jobs" button.
- `agent_coverage.test.ts` still passes with the routes gone.
- Full checks: `uv run ./checks.sh --agent-mode` (Python lint, format, types, tests; web lint, format, check, unit tests, build; `check_schema.sh`), the conventions gate on the worktree, and the e2e `prompts-management` spec if the e2e setup runs non-interactively.
