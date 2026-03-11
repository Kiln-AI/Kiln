# Phase 5: Frontend - Run Config Integration

## Goal

Add skills selection to the run config UI as a **separate dropdown** (not inside the tools dropdown) so users can choose which skills to include in agent runs. The skills dropdown is always visible — even when the project has no skills — and includes a "New Skill +" option at the top for quick creation.

## Design Decisions

- **Separate dropdown**: Skills get their own multi-select `FormElement` / `FancySelect`, placed **above** the tools selector in the run config form. This gives skills appropriate visibility and avoids burying them inside tool groups.
- **Always visible**: Unlike tools (which can hide when empty), the skills dropdown is always rendered. When the project has no skills, the dropdown still shows the "New Skill +" option so users can discover and create skills from the run config.
- **"New Skill +" option**: Always the first option in the dropdown. Uses the same pattern as the run config dropdown's "New Run Configuration" option: a special sentinel value (`"__create_new_skill__"`), badge `"＋"`, `badge_color: "primary"`. Selecting it navigates to the skill creation page.
- **Remember last selected**: Skills persist last-selected state per task, exactly like tools do via `indexedDBStore`.

## Files to Create / Modify

### Create: `app/web_ui/src/lib/ui/run_config_component/skills_selector.svelte`

New component, following the same structure as `tools_selector.svelte` but simpler (no tool-set grouping needed).

**Props:**

- `task_id: string | null` — used for persisting selection
- `skills: string[]` — bound list of selected skill tool IDs (e.g. `kiln_tool::skill::<id>`)

**Dropdown structure (OptionGroup[]):**

```
Group 1 (label: ""):
  - { value: "__create_new_skill__", label: "New Skill", badge: "＋", badge_color: "primary" }

Group 2 (label: "Available Skills"):
  - { value: "kiln_tool::skill::abc123", label: "Code Review", description: "Reviews code..." }
  - { value: "kiln_tool::skill::def456", label: "Writing Guide", description: "..." }
  ...
```

When `"__create_new_skill__"` is selected:

1. Remove it from the bound `skills` array (it's not a real selection)
2. Navigate to `/settings/manage_skills/{project_id}/create`

**Data source:** Filter the `available_tools` API response for `type === "skill"` tool sets, then map their tools to options. If no skill tools exist, Group 2 is omitted — only the "New Skill +" option remains.

**Persistence (last-selected):**

- Read from `$skills_store.selected_skill_ids_by_task_id[task_id]` on mount
- Write back on change (same pattern as tools_selector)
- Filter out unavailable skill IDs when available skills change

### Create: `app/web_ui/src/lib/stores/skills_store.ts`

New IndexedDB-backed store for remembering selected skills per task. Follows the exact same pattern as `tools_store.ts`:

```typescript
import { indexedDBStore } from "./index_db_store";

interface SkillsStoreState {
  selected_skill_ids_by_task_id: Record<string, string[]>;
}

export const skills_store = indexedDBStore<SkillsStoreState>("skills_store", {
  selected_skill_ids_by_task_id: {},
});
```

### Modify: `app/web_ui/src/lib/ui/run_config_component/tools_selector.svelte`

Remove skill-type tools from the tools dropdown. Filter out `type === "skill"` tool sets so they don't appear in both dropdowns. Skills are handled entirely by the new `skills_selector.svelte`.

### Modify: `app/web_ui/src/lib/ui/run_config_component/run_config_component.svelte`

Add `<SkillsSelector>` above `<ToolsSelector>` in the run config form. Wire up the `skills` binding and pass `task_id`. Merge the selected skill IDs into `tools_config.tools` alongside the selected tool IDs when building the run config payload.

**Model compatibility**: The existing `requires_tool_support` derivation must account for skills:

```typescript
// Currently:
$: requires_tool_support = tools.length > 0;
// Must become:
$: requires_tool_support = tools.length > 0 || skills.length > 0;
```

This flows into `updated_model_dropdown_settings.requires_tool_support`, which controls:

- Model dropdown filtering: models without `supports_function_calling` are moved to a "Not Recommended - Tool Calling Not Supported" group (in `available_models_dropdown.svelte`)
- Warning display when an unsupported model is selected

Skills require function calling just like tools do (the agent calls the `skill` tool), so this check must include them.

The skills selector must follow the **same hide/show rules** as the tools selector:

- **`hide_tools_selector={true}`** → also hide the skills selector. Used by:
  - Prompt optimization job creation (`create_prompt_optimization_job`)
  - Q&A generation dialog (`generate_qna_dialog`)
  - `create_new_run_config_dialog` (passes through)
- **`show_tools_selector_in_advanced={true}`** → also move skills selector into the "Advanced Options" collapse. Used by:
  - Data gen sample modal (`generate_samples_modal`)
  - Data gen node (`generated_data_node`)

These are structured generation flows (data gen, prompt optimization, Q&A) where agent skills aren't relevant. The existing `hide_tools_selector` and `show_tools_selector_in_advanced` props on `run_config_component.svelte` should control both tools and skills — no new props needed.

Alternatively, if we want independent control, add `hide_skills_selector` / `show_skills_selector_in_advanced` props, but for now keeping them in sync with the tools props is simpler and matches the use cases.

### Modify: `app/web_ui/src/routes/(app)/fine_tune/.../create_finetune/+page.svelte`

The fine-tune page has special tool handling that skills must participate in:

1. **Dataset matching**: The page passes `selected_tool_ids` as `required_tool_ids` to `SelectFinetuneDataset`, which filters eligible datasets to those matching the selected tools. Since skills are now a separate binding, the fine-tune page must **merge `selected_tool_ids` and `selected_skill_ids`** before passing to the dataset selector:

   ```typescript
   required_tool_ids={[...selected_tool_ids, ...selected_skill_ids].length > 0
     ? [...selected_tool_ids, ...selected_skill_ids]
     : undefined}
   ```

2. **Disabled when model doesn't support function calling**: The existing `disabled_tools_selector` logic disables and clears tools when the selected model lacks function calling. Skills must follow the same rule — if the model can't do function calling, it can't call the skill tool either. The skills selector should accept a `disabled` prop (like the tools selector's `ToolsSelectorSettings.disabled`) and the fine-tune page should pass `disabled={disabled_tools_selector}` to both selectors.

3. **Saved state**: The fine-tune page persists form state to IndexedDB (`SavedFinetuneState`). Add `skills?: string[]` to this interface so selected skills are also restored when returning to the form.

### Modify: `app/web_ui/src/lib/types.ts`

After regenerating the API schema, ensure the `ToolSetType` enum includes `"skill"`.

## Run Config Flow

When a user selects skills:

1. Skills appear in the **skills dropdown** (separate from tools)
2. Selected skill IDs (e.g. `kiln_tool::skill::123`) are merged into `tools_config.tools` alongside tool IDs
3. When the run executes, the backend's adapter consolidates skill tool IDs into a single `SkillTool`
4. The agent sees one `skill` tool with all selected skills listed

**No skills selected**: The `skill` tool is not provided to the agent at all. This matches the ticket requirement: "Skills tool not given to agent unless 1+ is selected."

## Testing

### Frontend Tests

1. **Skills selector**: Mock `available_tools` API response including a skill tool set. Verify:
   - Skills dropdown renders even when no skills exist (shows "New Skill +" only)
   - Skills can be selected/deselected
   - Selected skill IDs are in the correct format (`kiln_tool::skill::<id>`)
   - Selecting "New Skill +" navigates to the creation page
   - Last-selected skills are restored from `skills_store` on mount

2. **Skills store**: Verify IndexedDB persistence:
   - Selected skills are saved per task_id
   - Unavailable skills are filtered out on load

3. **Tools selector**: Verify skill-type tools are excluded from the tools dropdown.

4. **Run config**: Verify that selected skills are merged into `tools_config.tools` when saving/running.

5. **Model compatibility**: Verify:
   - Selecting skills (with no tools) sets `requires_tool_support = true` on the model dropdown
   - Models without function calling appear in "Not Recommended" group when skills are selected
   - Warning is shown when a non-function-calling model is selected with skills active

6. **Fine-tune page**: Verify:
   - Selected skills are merged with selected tools into `required_tool_ids` for dataset matching
   - Skills selector is disabled when model doesn't support function calling
   - Skills are cleared when model changes to one without function calling
   - Skills are persisted/restored in the fine-tune saved state

### Integration Test

1. Create a project (no skills yet)
2. Navigate to run page — skills dropdown visible with "New Skill +" option
3. Click "New Skill +" — navigates to skill creation
4. Create a skill, return to run page
5. Skill appears in dropdown, select it
6. Run a task — agent receives the skill tool and can call it
7. Navigate away and back — last-selected skill is remembered

## Key Design Notes

- Skills get a **dedicated dropdown** for visibility and discoverability, separate from tools
- The dropdown is **always visible** (never hidden), with "New Skill +" as a permanent first option for discoverability
- "New Skill +" follows the same sentinel-value pattern as the run config dropdown's "New Run Configuration" option
- The `skills_store` mirrors `tools_store` exactly — IndexedDB persistence of selected IDs per task
- The backend consolidation of multiple skill tool IDs into one `SkillTool` is transparent to the frontend
- Skill IDs are merged into `tools_config.tools` at submission time, so the backend run config schema doesn't need a new field
