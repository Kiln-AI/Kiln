---
status: complete
---

# Phase 9: Docs-link audit + final polish (cross-flow consistency)

## Overview

Two goals: (1) audit and remove dead/non-salient docs links from the create flow and the eval detail route, and (2) sweep the create-flow components this project introduced/changed to replace hardcoded `text-gray-*` colors with theme-aware `text-base-content/*` tokens for dark-mode compatibility, plus fix any remaining cross-flow heading/spacing/copy inconsistencies.

## AUDIT: Docs links

All three docs.kiln.tech URLs used in the eval flow were verified via WebFetch and return **404 Page Not Found**:

| File | URL | Status | Decision |
|---|---|---|---|
| `[eval_id]/+page.svelte:624-629` | `https://docs.kiln.tech/docs/evaluations` | 404 | REMOVE |
| `[eval_id]/+page.svelte:625-627` | `https://docs.kiln.tech/docs/evaluations/evaluate-appropriate-tool-use` | 404 | REMOVE |
| `[eval_id]/+page.svelte:636-637` | `sub_subtitle="Read the Docs"` + `sub_subtitle_link={docs_link(evaluator)}` | Dead links | REMOVE `docs_link()` function, `sub_subtitle`, and `sub_subtitle_link` props |
| `create_eval_config/+page.svelte` | (already removed in Phase 2) | N/A | No action |
| `create_eval_config/[eval_config_type]/+page.svelte` | (already removed in Phase 3) | N/A | No action |

**Note:** `compare_run_configs/+page.svelte` and `eval_configs/+page.svelte` also have dead docs links but are outside this project's scope (not in the create flow; not introduced/changed by this project).

## AUDIT: Hardcoded gray colors in create-flow components

Components THIS PROJECT introduced or changed that use hardcoded `text-gray-*`:

| Component | Instances | Replacement |
|---|---|---|
| `eval_type_intro.svelte` | `text-gray-500` (explainer), `text-gray-400` (example) | `text-base-content/60`, `text-base-content/40` |
| `eval_test_run_pane.svelte` | Multiple `text-gray-400`, `text-gray-600`, `text-gray-300` | `text-base-content/40`, `text-base-content/70`, `text-base-content/30` |
| `test_run_input_card.svelte` | `text-gray-500`, `text-gray-400`, `text-gray-600` | `text-base-content/60`, `text-base-content/40`, `text-base-content/70` |
| `test_run_browse_dialog.svelte` | `text-gray-500`, `text-gray-400`, `text-gray-600` | `text-base-content/60`, `text-base-content/40`, `text-base-content/70` |
| `manual_example_dialog.svelte` | `text-gray-500` | `text-base-content/60` |
| `reference_data_field.svelte` | `text-gray-500` | `text-base-content/60` |
| `eval_config_builder.svelte` | `text-gray-600` (confirm dialog) | `text-base-content/70` |
| `form_section.svelte` | `text-gray-500` | `text-base-content/60` |
| `disclosure_radio_group.svelte` | `text-gray-500` | `text-base-content/60` |
| `eval_type_hero.svelte` | `text-gray-500` | `text-base-content/60` |
| `eval_type_row.svelte` | `text-gray-500`, `text-gray-400` | `text-base-content/60`, `text-base-content/40` |
| `create_eval_config/+page.svelte` | `text-gray-500` (section heading) | `text-base-content/60` |
| `set_check_form.svelte` | `text-gray-500` (hint text) | `text-base-content/60` |
| `tag_input.svelte` | `bg-gray-200 text-gray-600`, `text-gray-400 hover:text-gray-600` | `bg-base-300 text-base-content/70`, `text-base-content/40 hover:text-base-content/70` |

**Out of scope:** `llm_judge_form.svelte` (not introduced by this project, keep consistent within itself), result renderers (`*_result.svelte`, `eval_result_scores.svelte` -- view surfaces, not create flow).

## Steps

1. **Remove `docs_link()` from `[eval_id]/+page.svelte`:** Delete the `docs_link` function, remove `sub_subtitle` and `sub_subtitle_link` props from the `AppPage` call.

2. **Sweep create-flow components for hardcoded gray colors:** Replace `text-gray-500` with `text-base-content/60`, `text-gray-400` with `text-base-content/40`, `text-gray-600` with `text-base-content/70`, `text-gray-300` with `text-base-content/30`, `bg-gray-200` with `bg-base-300` in all components listed in the audit above.

3. **Cross-flow consistency pass:** Check heading levels, spacing rhythm, and copy tone across the select screen, container/intro, forms, and test-run pane. Fix any inconsistencies found.

4. **Update tests:** Ensure no tests assert removed classes or docs links. Add a test asserting the eval detail page no longer renders "Read the Docs". Update any tests that assert `text-gray-*` classes.

5. **Run checks:** lint, format, type-check, tests, build.

## Tests

- Assert `[eval_id]/+page.svelte` no longer renders "Read the Docs" sub_subtitle or the `docs_link()` function.
- Assert create-flow pages still do not render "Read the Docs" (existing test).
- Verify no regression to any existing test from color class changes.
