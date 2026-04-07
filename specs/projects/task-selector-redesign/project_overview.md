---
status: complete
---

# Task/Project Selector Redesign

Redesign the `select_tasks_menu.svelte` component from a single-column expandable menu list into a two-column panel layout with projects on the left and tasks on the right.

## Reference

A static HTML mock (`kiln_modal_selector_mock.html`) provides the target layout. The mock is not production code -- it doesn't use our UI frameworks, colors, or design system. It's purely a layout/structure reference.

## Current State

The existing `select_tasks_menu.svelte` renders as a DaisyUI `<ul class="menu">` with expandable project rows. Clicking a project expands inline to show its tasks. It's used in two contexts:
- **Sidebar dialog**: Wrapped in a `<Dialog>` with the title "Select Project & Task" in `+layout.svelte`
- **Fullscreen setup page**: Rendered directly in the onboarding flow at `/setup/select_task`

The redesigned component should work in both contexts, ideally as a single file change.

## Design Goals

- **Two-column layout**: Projects pane on the left (~320px), tasks pane on the right (remaining width). Based on the mock.
- **No search**: Cut from the mock.
- **No recents**: Cut from the mock.
- **No subtitle**: Cut from the mock.
- **Title is external**: "Select Project & Task" comes from the Dialog wrapper or the setup page, not this component.
- **Currently selected at top**: Show the currently selected project/task at the top of the component.
- **Single "New" buttons**: Only in pane headers ("+ New Project" in project pane header, "+ New Task" in task pane header). Both are standard/ghost buttons (not primary/blue). Remove duplicate inline create rows at bottom of each list.
- **Click-to-select tasks**: Clicking a task immediately selects it and closes (dispatches `task_selected`). No "Open Task" or "Cancel" footer buttons.
- **Dismiss via X**: Users dismiss without selecting via the dialog's X button (already provided by Dialog) or clicking outside. No cancel button in component.
- **Project selection shows tasks**: Clicking a project in the left pane loads its tasks in the right pane. Selected project is visually highlighted.
- **Project descriptions**: Show project description below the name if available (data exists on the Project type).
- **Task pane header**: "Tasks in [Project Name]" with task count. No search hint text.
- **No timestamps on tasks**: Data not available.
- **Task count badge**: Each project row shows a count of its tasks.
- **Responsive**: On small screens, collapse to single-column layout.
