---
status: draft
---

# Phase 1: Two-Column Task/Project Selector Redesign

## Overview

Rewrite `select_tasks_menu.svelte` from a single-column expandable menu to a two-column panel layout with projects on the left and tasks on the right. Add small-screen pane switching and a currently-selected banner. Update Dialog width in `+layout.svelte` and setup page container width.

## Steps

1. Rewrite `select_tasks_menu.svelte` script section:
   - Remove toggle-off behavior in `select_project()` (clicking selected project is a no-op)
   - Add `show_project_pane: boolean = false` state for small-screen toggle
   - On small-screen project selection, set `show_project_pane = false` to switch back to task pane

2. Rewrite `select_tasks_menu.svelte` template:
   - Add "Currently selected" banner at top showing `$current_project?.name / $current_task?.name`
   - Add small-screen project indicator button (hidden on `md:` and above)
   - Create two-column grid layout: `grid md:grid-cols-[320px_1fr] gap-4`
   - Left pane: Projects with header ("Projects" / "Pick a project first" / "+ New Project" button), scrollable list of project rows with folder icon, name, description
   - Right pane: Tasks with header ("Tasks in [Project Name]" / count / "+ New Task" button), scrollable list of task rows with document icon, name. Empty state when no project selected. Loading spinner. Error state.
   - Small-screen: conditionally show one pane at a time using `show_project_pane`
   - Style per UI design spec: `bg-base-100` bodies, `bg-base-200` headers, `border-base-300`, `rounded-2xl`, hover/selected states

3. Update `+layout.svelte`: Add `width="wide"` to the Dialog wrapping SelectTasksMenu

4. Update setup page: Widen the container from `max-w-[500px]` to `max-w-[800px]` to accommodate two columns

## Tests

- No new unit tests needed per architecture spec. This is a visual/interaction redesign. The event was renamed from `task_selected` to `dismiss` but the overall interaction pattern is the same. Visual verification during implementation.
