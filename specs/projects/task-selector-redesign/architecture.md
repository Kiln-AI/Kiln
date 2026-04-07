---
status: complete
---

# Architecture: Task/Project Selector Redesign

This is a single-component frontend redesign. No new APIs, no backend changes, no new dependencies.

## Component: `select_tasks_menu.svelte`

### Props (unchanged)

```typescript
export let new_project_url = "/settings/create_project"
export let new_task_url = "/settings/create_task"
```

### State

Existing state variables are retained with the same semantics:

- `manually_selected_project` — tracks user's project selection (distinct from store)
- `selected_project` — derived: manually selected or current project from store
- `selected_project_tasks` — loaded task list for selected project
- `tasks_loading` / `tasks_loading_error` — loading state
- `last_loaded_project_id` — prevents redundant loads

New state:

- `show_project_pane: boolean` — small-screen toggle. `true` = show projects, `false` = show tasks. Default `false` (tasks visible when a project is already selected).

### Key Behavioral Changes from Current Implementation

1. **Remove toggle-off**: Current code deselects a project when clicking it again. Remove this — clicking the selected project is a no-op.
2. **Two-column rendering**: Replace the nested `<ul>` menu structure with a two-pane grid layout.
3. **Small screen pane switching**: `show_project_pane` controls which pane is visible below the breakpoint.

### Template Structure

```
<div>                               <!-- outer container -->
  <div>                             <!-- currently selected banner -->
  
  <!-- Desktop: both visible. Small: one visible -->
  <div class="grid grid-cols-[320px_1fr] gap-4">
    <section>                       <!-- projects pane -->
      <div>                         <!-- pane header: title + new button -->
      <div>                         <!-- scrollable project list -->
        {#each project_list as project}
          <button>                  <!-- project row -->
        {/each}
      </div>
    </section>
    
    <section>                       <!-- tasks pane -->
      <div>                         <!-- pane header: title + new button -->
      <div>                         <!-- scrollable task list or empty/loading/error state -->
        {#each selected_project_tasks as task}
          <button>                  <!-- task row -->
        {/each}
      </div>
    </section>
  </div>
</div>
```

### Responsive Strategy

Use Tailwind responsive classes:

- Desktop (`md:` and above): `grid grid-cols-[320px_1fr]` — both panes visible
- Small (below `md`): single column, conditionally render one pane via `show_project_pane`

The project indicator button (small screen only) sits above the panes and is hidden on desktop with `md:hidden`.

Small-screen flow:
1. Project indicator button visible, shows selected project name
2. Click indicator → `show_project_pane = true`, project list appears, task pane hides
3. Click a project → project selected, `show_project_pane = false`, task pane reappears

### Data Flow (unchanged)

- `$projects` store provides project list
- `$current_project` / `$current_task` stores provide current selection
- Task loading via `client.GET("/api/projects/{project_id}/tasks")`
- Selection updates `ui_state` store and calls `goto("/")`
- `dispatch("task_selected")` signals the parent to close

### Dialog Integration

The parent `+layout.svelte` wraps this component in `<Dialog title="Select Project & Task">`. The Dialog provides the title and X button. The component needs the `width="wide"` prop on Dialog to accommodate two columns.

**Change needed in `+layout.svelte`**: Add `width="wide"` to the Dialog that wraps SelectTasksMenu.

### Setup Page Integration

The fullscreen setup page renders the component directly (no Dialog). The two-column layout works standalone — the component doesn't assume a Dialog wrapper.

## Testing

This is a visual/interaction redesign of an existing component. No new unit tests needed — the component's public interface (props, events, store interactions) is unchanged. Visual verification during implementation.

## Files Changed

1. `app/web_ui/src/routes/(app)/select_tasks_menu.svelte` — full rewrite of template and styles, minor script changes
2. `app/web_ui/src/routes/(app)/+layout.svelte` — add `width="wide"` to task selector Dialog
