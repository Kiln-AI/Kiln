# Phase 5: Frontend - Run Config Integration

## Goal
Add skills selection to the run config UI so users can choose which skills to include in agent runs.

## Files to Modify

### Modify: `app/web_ui/src/lib/ui/run_config_component/tools_selector.svelte`

Add a "Skills" option group to the tools multi-select dropdown. Skills should appear as a separate group from the other tool types.

Currently, `ToolsSelector` groups tools by `ToolSetType`: `["search", "kiln_task", "mcp", "demo"]`.

Add handling for the new `"skill"` type:

```typescript
// In the group building logic, add:
case "skill":
  return {
    label: "Skills",
    options: toolSet.tools.map((tool) => ({
      value: tool.id,
      label: tool.name,
      description: tool.description ?? undefined,
    })),
  }
```

The `FancySelect` multi-select dropdown already supports option groups, so skills will appear naturally as a "Skills" section in the dropdown.

### Modify: `app/web_ui/src/lib/stores/tools_store.ts`

The tools store loads available tools via `GET /api/projects/{project_id}/available_tools`. Since the backend now includes skills in this response, the store should work without changes — it already handles arbitrary `ToolSetType` values.

However, verify that:
1. The store correctly passes through the new "skill" type
2. Selected skill IDs are included in the run config's `tools_config.tools` list

### Modify: `app/web_ui/src/lib/types.ts`

After regenerating the API schema, ensure the `ToolSetType` enum includes `"skill"`.

### Run Config Flow

When a user selects skills:
1. Skills appear in the tools dropdown under a "Skills" group
2. Selected skill IDs (e.g. `kiln_tool::skill::123`) are stored in `tools_config.tools`
3. When the run executes, the backend's adapter consolidates skill tool IDs into a single `SkillTool`
4. The agent sees one `skill` tool with all selected skills listed

**No skills selected**: The `skill` tool is not provided to the agent at all. This matches the ticket requirement: "Skills tool not given to agent unless 1+ is selected."

### Hidden When No Skills

The skills group should only appear in the dropdown if the project has skills. Since the backend only includes the skills tool set when `project.skills()` is non-empty, this is handled automatically — the frontend already filters empty tool sets.

## Testing

### Frontend Tests

1. **Tools selector**: Mock available_tools API response including a skill tool set. Verify:
   - Skills group appears in dropdown
   - Skills can be selected/deselected
   - Selected skill IDs are in the correct format

2. **Run config**: Verify that selected skills are included in the `tools_config` when saving/running.

### Integration Test

1. Create a project with a skill
2. Navigate to run page
3. Verify skill appears in tools dropdown
4. Select skill, run a task
5. Verify the agent receives the skill tool and can call it

## Key Design Notes

- Skills use the existing tools infrastructure — no new UI components needed for the run config
- The backend consolidation of multiple skill tool IDs into one `SkillTool` is transparent to the frontend
- If a project has no skills, the "Skills" group simply doesn't appear in the dropdown
- Consider adding a "Create Skill" action in the skills option group header (like how Kiln tasks have "Create New"), linking to `/settings/manage_skills/{project_id}/create`
