---
status: complete
---

# Functional Spec: Experiment Lineage Page

A read-only page that draws every run config of a task as a lineage graph. Each run config is one small square, connected to the run config(s) it was derived from. The square's fill shows which kinds of change it made against its parent. The point of the page is to show, at a glance, how much was tried on a task and how the agent evolved.

This is not a compare screen. The existing Compare page stays as it is, apart from a new link to this page.

Reference material in this folder:

- `reference_mock.webp`: the first mock ("All the things we tried").
- `design_reference/`: the design handoff (`README.md`, `lineage_page.html`, `lineage.js`, `screenshot.png`). It was made without access to the code. Where it conflicts with this spec or with the Kiln style guide, this spec and the style guide win. `ui_design.md` lists each conflict and how it is resolved. The handoff's eval scores are not built (see Out of Scope).
- Mike's prototype on branch `mike/compare-map-view` (route `/evolution/[project_id]/[task_id]`, map view). Inspiration only. Nothing is ported from it.

## Naming and Route

- Page title: **Experiment Lineage**.
- Subtitle: "Every run configuration for this task, and how they evolved."
- Route: `/optimize/[project_id]/[task_id]/experiment_lineage`.
- Breadcrumb: "Optimize", linking to `/optimize/[project_id]/[task_id]`.
- Optional query parameter `selected=<run config id>`: the run config to select on load (see Selection).

## Entry Points

There is no link in the left sidebar.

1. **Optimize page, Run Configurations header.** A plain `btn btn-mid` labelled "Experiment Lineage", placed before "Compare". It is shown only when not in select mode (select mode swaps the header buttons for selection controls, and this button hides with them). When the buttons don't fit beside the title, they move to their own line under it (see `ui_design.md`).
2. **Optimize page, run config row menu.** A new item "Show in Experiment Lineage" in each row's `TableActionMenu`. It opens the page with `selected=<that run config's id>`.
3. **Compare page.** An AppPage action button labelled "Experiment Lineage" that opens the page. It does not pass any selection.

## Data

Everything comes from APIs the web app already calls. No backend changes are needed for the lineage graph.

- Run configs: the existing run configs store (`load_task_run_configs`), which includes completed fine-tune run configs.
- Lineage: `run_config.provenance.derived_from_ids`. It is an ordered list. The first entry is the **primary parent**. Later entries are **extra parents** (sources merged in).
- Display names: the existing stores for model info, task prompts and available tools, as the run config detail page uses them.

## Graph Model

- **Node**: one per run config.
- **Edge**: one per (parent, child) pair, for every entry in a child's `derived_from_ids`. Each edge is either primary (the child's first parent) or extra.
- **Deleted parent**: an id in `derived_from_ids` that matches no run config becomes one placeholder node, "Deleted run config", shared by every child that names it. It keeps the tree connected.
- **Starting point**: a node with no parents and at least one child.
- **No recorded parent**: a node with no parents and no children. Run configs made before lineage was recorded, and fine-tune run configs, are usually this. They are drawn in a separate grid below the tree, not in the tree.
- **Ignored entries**: empty ids, a run config naming itself, and duplicate ids in one list.
- **Cycles**: lineage should never contain a cycle, but files can be edited by hand. If an edge would close a cycle, it is dropped and the graph still renders.

## Change Detection

Each node is compared with its **primary parent** only. Extra parents are drawn but not compared. The comparison detects five kinds of change, independently. A node can have any combination of them.

| Kind | Changed when |
|---|---|
| Prompt | `prompt_id` differs. Compared by ID, not text. |
| Tools | The set of tool IDs differs, counting only IDs that are not skills. |
| Skills | The set of skill IDs (prefix `kiln_tool::skill::`) differs. |
| Model | `model_name` or `model_provider_name` differs. |
| Settings | Any of temperature, top P, thinking level, structured output mode or input transform differs. Input transforms are compared with the existing `inputTransformsEqual`. |

Rules for the cases the table doesn't cover:

- **No change**: the node has a parent and none of the five kinds changed. It is a "Copy or re-run".
- **MCP run configs** have no prompt, tools, skills or settings. If either side is MCP, the only comparison is "the thing that runs the task": if both are MCP with the same tool ID, there is no change. Otherwise it counts as a Model change.
- **Parent deleted**: the node's primary parent is a deleted placeholder, so nothing can be compared. The node has the "Parent deleted" status, not "Copy or re-run".
- **Known limit, accepted**: two prompts with identical text but different IDs count as a prompt change. Older data can contain these duplicates. Cloning in the UI keeps the prompt ID, so new data rarely hits this.

Each node ends up with exactly one status:

| Status | Meaning |
|---|---|
| Starting point | No parents, has children. |
| Changed | Has a live primary parent and at least one kind changed. Carries the list of kinds. |
| Copy or re-run | Has a live primary parent and nothing changed. |
| Parent deleted | Primary parent is a deleted placeholder. |
| No recorded parent | No parents, no children. |
| Deleted | The placeholder itself. |

## Node Encoding

Each node is a small square. The fill shows its status. For "Changed", it shows every kind that changed. The exact shapes, sizes and colors are in `ui_design.md`. In summary:

- 1 kind: the square is filled with that kind's color.
- 2 to 5 kinds: the square is split into halves, quarters, or quarters plus a center square. Kinds always fill in the order Prompt, Tools, Skills, Model, Settings.
- Copy or re-run: solid grey.
- Starting point: solid black.
- Parent deleted and No recorded parent: white with a grey outline.
- Deleted placeholder: white with a dashed grey outline.

## Page Layout (Functional)

From top to bottom:

1. AppPage header: breadcrumb, title and subtitle.
2. Stats row (see Stats).
3. Filter row: a "Changed from parent" label, then six toggle chips. The chips double as the graph's color legend.
4. Body: the graph, and the detail panel to its right when a node is selected. The body fills the remaining height of the window.

## Stats

A styled row under the page header, with two stats. Each is a large number over a short label:

- **N** "run configurations" ("run configuration" when N is 1)
- **M** "models" ("model" when M is 1)

Counting rules:

- N counts every run config. It excludes deleted placeholders.
- M counts distinct models among run configs that have a model. A model is the pair (model name, provider). A fine-tuned model counts as its own model. MCP run configs don't add a model.

## Filter Chips

- Six chips, in this order: Prompt, Tools, Skills, Model, Settings, Copy or re-run. Each shows its swatch, its name and a count.
- Counts overlap: a node counts once toward every kind it changed. "Copy or re-run" counts nodes with that status. Counts don't change when filters are on.
- Clicking a chip toggles it. Several chips can be on at once. A node matches if it matches **any** active chip.
- While any chip is on, nodes that don't match drop to 15% opacity. Edges stay as they are. The selected node always stays at full opacity. Starting points, placeholders and nodes with no parent never match a chip.
- A "Clear" link appears after the chips while any chip is on. It turns every chip off.
- There is no info tooltip. The chips and the squares explain themselves.
- Filter state is not kept in the URL.

## Graph

### Layout

- A top-to-bottom tree. Each node's row is its longest path from a root, so every edge points down, including edges from extra parents.
- Columns follow each node's primary parent. Leaves take the next free column, left to right, ordered by creation time. A parent is centered over its first and last children. Several trees sit side by side, oldest root first.
- Nodes with no recorded parent sit in a grid below the tree, oldest first, under a label "No recorded parent (N)". The grid is as wide as the tree, or roughly four times wider than tall if there is no tree.

### Edges

- Primary edges: elbow lines. They go down from the parent's bottom center, across at the gap above the child's row, then down into the child's top center.
- Extra-parent edges: a smooth S-curve straight from the parent's bottom center to the child's top center, vertical at both ends. The curve marks them, so they have no dashes. At rest they are lighter and thinner than primary edges.
- Hovering a node draws that node's own edges dark and slightly thicker: the edges to its parents and to its children, primary and extra. They show and hide with the tooltip.
- When a node is selected, every edge on any path from a root to that node is drawn dark and slightly thicker. That includes extra-parent paths.

### Zoom and Pan

- Toolbar buttons: "−", "Fit", "+". The current zoom shows as a percentage between "−" and "Fit".
- Zoom range: from the lower of 50% and the zoom that fits the whole graph, up to 200%. "+" and "−" step by a factor of 1.25, centered on the middle of the view.
- Pinch on a trackpad, or Ctrl/⌘ plus the scroll wheel, zooms at the cursor.
- A plain scroll or two-finger swipe pans. Dragging empty space pans.
- Double-clicking zooms in one step, the same as "+", centered on the cursor. Fit stays on its button and the `0` key.
- "Fit" shows the whole graph, centered, with a small margin.
- On load: if `selected` names a run config, zoom to 100% centered on it. Otherwise, fit.
- When the detail panel opens or closes and the graph area changes width, the point at the center of the view stays at the center. If a node is selected and that would leave it out of view, the view then pans the least distance that brings it back in, whether it was selected by click or by keyboard.

### Hover

Hovering a node draws its own edges dark (see Edges) and shows a short tooltip next to it:

- Line 1: the run config name, or "Deleted run config".
- Line 2: the status. For Changed it lists the kinds ("Prompt, Model"). The others read "Starting point", "Copy or re-run, no changes", "Parent deleted", "No recorded parent" or "This run config was deleted".
- Line 3: the model display name with its provider ("GPT 5 (OpenAI)"), the MCP tool name for MCP run configs, or nothing for placeholders.

### Selection

- Clicking a node selects it. This opens the detail panel and highlights its lineage.
- Clicking another node moves the selection.
- A single click on empty space clears the selection and closes the panel. It waits about 250ms first, so a double-click on empty space only zooms. Dragging to pan never clears the selection.
- The panel's close button or Esc clears the selection and closes the panel. If focus was in the panel, it moves to the graph.
- Selecting a run config from the panel's lineage dialog pans the view the least distance that brings it into view, as the arrow keys do.
- The selected node gets a dark ring.
- The selection is mirrored to the URL as `selected=<id>`, using replaceState, so reloading keeps it. An unknown `selected` id is ignored and the page fits.

### Keyboard

- The graph area can be focused. It has a label: "Run config lineage graph".
- With focus and no selection, any arrow key selects the oldest starting point, or the first node if there is none.
- With a selection: Up selects the primary parent. Down selects the oldest child. Left and Right select the previous and next node in the same row. The view pans to keep the selected node visible.
- Esc closes the panel. `+`, `-` and `0` zoom in, zoom out and fit.

## Detail Panel

Opens on the right of the graph when a node is selected. Its run config section reuses the run config detail page's property list, and its changes section takes the same property list style. Every section is titled in the sidebar section style of the spec and Run pages.

From top to bottom:

1. **Header**: the node's square drawn large, then a column, then the close button at the top right. The column holds:
   - The run config name. It wraps to two lines, then ends in an ellipsis.
   - The lineage line, a count rather than a list of names:
     - Starting point: "Starting point · 3 children".
     - Derived: "Derived from 1 parent · 1 child", or "Derived from 2 parents · 3 children" for a merge.
     - No recorded parent: "No recorded parent".
     - Deleted placeholder: "This run config was deleted · 2 children".
     - The children part is left off when there are none ("Derived from 2 parents").
     - The line is a link that opens the Lineage dialog (below). It is plain text when the node has no parents and no children.
   - A creator badge, "Agent Created" or "Human Created", from `provenance.origin`. It is hidden when no creator is recorded.
2. **Notes** section, when `provenance.notes` exists: the full notes as read-only text.
3. **Changed from Parent** section, for a node with a live primary parent. One row per changed kind, in order, in the property list style: the kind's name on the left in the base text color, the value on the right in grey.
   - Prompt, Model and Settings show the new value, then under it a smaller, lighter line "was ‹old value›". Each is cut to one line with an ellipsis, with the full text on hover. A prompt links to its page, both the new and the old one, when it has a page; generator prompts such as "Basic (Zero Shot)" have none. Models and settings are plain text. Settings shows only the fields that changed, as "Temperature 0.7 · Thinking High".
   - Tools and Skills show "2 added, 1 removed", leaving off a part that is zero ("2 added"). It is a link that opens the Tools Changed or Skills Changed dialog (below).
   - A Copy or re-run reads "Same settings as parent." A Parent deleted node reads "The parent run config was deleted, so changes can't be shown." This section is hidden for other statuses.
4. **Run Configuration** section: under its title, a link "Compare eval results to others" that opens the Compare page with this run config in column 1 and column 2 empty. Then the same property list the run config detail page shows (`getRunConfigUiProperties` with `PropertyList`). Hidden for the deleted placeholder.

There is no "Compare to Parent" action: a run config can have several parents, so a single before-and-after pair doesn't fit. There is no primary button, and there is no link to the run config detail page. The panel already shows everything that page shows. Only the detail page's Edit and Clone actions are missing, and those are out of scope here.

### Lineage Dialog

Opened from the lineage line. The house dialog, titled "Lineage", with the run config's name as its subtitle and a Close button.

- A "Parents" list in recorded order, primary first, and a "Children" list, oldest first. A list with no entries is left out.
- One run config per line, with its small square, cut to one line with an ellipsis.
- Each live run config is a link. Choosing it closes the dialog, selects that run config and pans it into view.
- A deleted parent shows as "Deleted run config" in grey and can't be chosen.

### Tools Changed and Skills Changed Dialogs

Opened from a Tools or Skills row. The house dialog, titled "Tools Changed" or "Skills Changed", with the subtitle "Compared with the parent run configuration." and a Close button.

- An "Added" list and a "Removed" list. A list with no entries is left out.
- One tool or skill per line, by name, cut to one line with an ellipsis. Each links to its tool or skill page where one exists.

Closing either dialog returns focus to the link that opened it.

## Empty, Loading and Error States

- **Loading**: the standard full-page spinner, as on the Optimize page.
- **Error**: the standard error block, as on the Compare page.
- **No run configs**: an `Intro` explaining run configs and lineage, with a button "Create Run Config" that goes to the Optimize page's create flow (`/optimize/[project_id]/[task_id]/run_config/create`).
- **Run configs, but no lineage at all** (every node has no recorded parent): the graph shows just the grid. Above it, an info `Warning`: "Lineage is recorded when you clone a run config, or when an agent derives one from another. These run configs were created without it."

## Constraints

- Up to 1,000 run configs must pan and zoom smoothly on a mid-range laptop.
- No new npm dependency.
- One color palette in code: the graph's change colors come from the same palette the Compare charts use, moved into a shared file (see `ui_design.md`).
- Web UI only. No backend changes for this page.

## Out of Scope

- **Eval scores.** The design shows a score per run config: a best-score stat, a ring on the best node, the score in the tooltip, and the score with its change against the parent in the panel. None of these are built. Kiln has no single score per run config: a task has several evals, each eval has several output scores on different scales, and many run configs were never evaluated. The page stays a pure lineage view. The panel's Compare link covers scores.
- Mike's cards view, compare matrix, score lenses and inspector.
- Editing, cloning or deleting run configs from this page.
- Any change to the Compare page apart from the new link.
- A sidebar link.
