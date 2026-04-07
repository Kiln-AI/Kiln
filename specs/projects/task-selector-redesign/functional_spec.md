---
status: complete
---

# Functional Spec: Task/Project Selector Redesign

## Overview

Replace the existing single-column expandable menu (`<ul class="menu">`) in `select_tasks_menu.svelte` with a two-column panel layout. Projects on the left, tasks on the right. The component must work in both the sidebar dialog and the fullscreen setup page.

## Layout Structure

### Currently Selected Banner

At the top of the component, show the currently selected project and task:

- Format: "Currently selected: **Project Name** / **Task Name**"
- If no task is selected: "No task selected"
- Styled subtly (muted text, small font) so it doesn't dominate

### Two-Column Content Area (Desktop)

Side-by-side panes below the banner:

- **Left pane (~320px)**: Projects list
- **Right pane (flex 1)**: Tasks for the selected project

Each pane is a bordered, rounded container with a header and scrollable list area.

### Small Screen Behavior

On small screens, only one pane is visible at a time:

- **Project indicator button** at top showing the selected project name. Clicking it reveals the project pane and hides the task pane.
- **Project pane**: When visible, clicking a project selects it and collapses the project pane, showing the task pane.
- **Task pane**: Visible when the project pane is hidden. Shows tasks for the selected project.
- Toggling between panes: project indicator button toggles to project pane; selecting a project toggles back to task pane.

## Left Pane: Projects

### Header

- Title: "Projects"
- Subtitle: "Pick a project first"
- Button: "+ New Project" (ghost/outline style, not primary)
  - Links to `new_project_url` prop

### Project List

Each project row shows:

- Folder icon
- Project name (bold, truncated if long)
- Project description below the name (small, muted, truncated if long). Only shown if description exists.
- No task count badge on project rows.

**Interactions:**

- Hover: subtle background highlight
- Click: selects the project, loads its tasks in the right pane
- Selected project: highlighted background with accent border
- The current project (from store) is auto-selected on mount
- Clicking the already-selected project is a no-op (no toggle-off behavior)

## Right Pane: Tasks

### Empty State (no project selected)

Centered message: "Select a project to view its tasks" with a document icon.

### Header (project selected)

- Title: "Tasks in **[Project Name]**"
- Subtitle: "[N] tasks" (count from loaded task list)
- Button: "+ New Task" (ghost/outline style, not primary)
  - Links to `new_task_url` prop + `"/" + project.id`

### Task List

Each task row shows:

- Document icon
- Task name (bold, truncated if long)

**Interactions:**

- Hover: subtle background highlight
- Click: immediately selects the task AND the project, updates the store, navigates to `/`, dispatches `task_selected` event. No confirmation step.
- Currently selected task (if viewing its project): highlighted with "Currently selected" label

### Loading State

While tasks are loading, show a centered spinner in the task list area.

### Error State

If task loading fails, show an error message in the task list area.

## Props (unchanged)

- `new_project_url: string` (default: `/settings/create_project`)
- `new_task_url: string` (default: `/settings/create_task`)

## Events (unchanged)

- `task_selected`: Dispatched when a task is clicked. Used by the Dialog wrapper to close.

## Behavior Details

### Initial State

- On mount, if a current project exists in the store, auto-select it and load its tasks
- If no current project, show the project list with no selection and the empty state in the task pane

### Project Switching

- Clicking a different project immediately updates the right pane
- Shows loading spinner while tasks load
- If the user rapidly clicks between projects, only the last-clicked project's tasks should render (existing debounce logic handles this via `last_loaded_project_id`)

### Task Re-selection

- Clicking the already-selected task should still fire `task_selected` (to close the dialog)

## Out of Scope

- Search / filtering
- Recents
- Timestamps on tasks
- Inline project/task creation (buttons link to creation pages)
- Drag and drop
- Keyboard navigation beyond browser defaults
