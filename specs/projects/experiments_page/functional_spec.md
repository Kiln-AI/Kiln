---
status: draft
---

# Functional Spec: Lineage Page

A read-only page that draws every run config of a task as a lineage graph. Each run config is one small square, connected to the run config(s) it was derived from. The square's fill shows which kinds of change it made against its parent. The point of the page is to show, at a glance, how much was tried on a task and how the agent evolved.

This is not a compare screen. The existing Compare page stays as it is, apart from a new link to this page.

Reference material in this folder:

- `reference_mock.webp`: the first mock ("All the things we tried").
- `design_reference/`: the design handoff (`README.md`, `lineage_page.html`, `lineage.js`, `screenshot.png`). It was made without access to the code. Where it conflicts with this spec or with the Kiln style guide, this spec and the style guide win. `ui_design.md` lists each conflict and how it is resolved.
- Mike's prototype on branch `mike/compare-map-view` (route `/evolution/[project_id]/[task_id]`, map view). Inspiration only. Nothing is ported from it.

## Naming and Route

- Page title: **Lineage**. (Open question 1 below. The first brief said "Experiments", the design and later messages say "lineage".)
- Route: `/optimize/[project_id]/[task_id]/lineage`.
- Breadcrumb: "Optimize", linking to `/optimize/[project_id]/[task_id]`.
- Optional query parameter `selected=<run config id>`: the run config to select on load (see Selection).

## Entry Points

There is no link in the left sidebar.

1. **Optimize page, Run Configurations header.** A plain `btn btn-mid` labelled "Lineage", placed before "Compare". It is shown only when not in select mode (select mode swaps the header buttons for selection controls, and Lineage hides with them).
2. **Optimize page, run config row menu.** A new item "Show in Lineage" in each row's `TableActionMenu`. It opens the page with `selected=<that run config's id>`.
3. **Compare page.** An AppPage action button labelled "Lineage" that opens the page. It does not pass any selection.

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

1. AppPage header: title, breadcrumb, and a subtitle carrying the stats (see Stats).
2. Filter row: "Changed from parent" label with an info tooltip, then six toggle chips.
3. Body: the graph, and the detail panel to its right when a node is selected. The body fills the remaining height of the window.

## Stats

The subtitle reads "N run configurations across M models". Examples: "182 run configurations across 17 models", "1 run configuration across 1 model".

- N counts every run config. It excludes deleted placeholders.
- M counts distinct models among run configs that have a model. A model is the pair (model name, provider). A fine-tuned model counts as its own model. MCP run configs don't add a model.

## Filter Chips

- Six chips, in this order: Prompt, Tools, Skills, Model, Settings, Copy or re-run. Each shows its swatch, its name and a count.
- Counts overlap: a node counts once toward every kind it changed. "Copy or re-run" counts nodes with that status. Counts don't change when filters are on.
- Clicking a chip toggles it. Several chips can be on at once. A node matches if it matches **any** active chip.
- While any chip is on, nodes that don't match drop to 15% opacity. Edges stay as they are. The selected node always stays at full opacity. Starting points, placeholders and nodes with no parent never match a chip.
- A "Clear" link appears after the chips while any chip is on. It turns every chip off.
- The info tooltip says: "Each square shows what changed from its parent run configuration. One change fills the square. More changes split it, always in the order prompt, tools, skills, model, settings. Settings covers temperature, top P, thinking level, structured output mode and input transform. Click a chip to filter."
- Filter state is not kept in the URL.

## Graph

### Layout

- A top-to-bottom tree. Each node's row is its longest path from a root, so every edge points down, including edges from extra parents.
- Columns follow each node's primary parent. Leaves take the next free column, left to right, ordered by creation time. A parent is centered over its first and last children. Several trees sit side by side, oldest root first.
- Nodes with no recorded parent sit in a grid below the tree, oldest first, under a label "No recorded parent (N)". The grid is as wide as the tree, or roughly four times wider than tall if there is no tree.

### Edges

- Primary edges: elbow lines. They go down from the parent's bottom center, across at the gap above the child's row, then down into the child's top center.
- Extra-parent edges: the same elbow shape, drawn dashed so a merge reads as a merge. They are not faded.
- When a node is selected, every edge on any path from a root to that node is drawn dark and slightly thicker. That includes extra-parent paths.

### Zoom and Pan

- Toolbar buttons: "−", "Fit", "+". The current zoom shows as a percentage between "−" and "Fit".
- Zoom range: from the lower of 50% and the zoom that fits the whole graph, up to 200%. "+" and "−" step by a factor of 1.25, centered on the middle of the view.
- Pinch on a trackpad, or Ctrl/⌘ plus the scroll wheel, zooms at the cursor.
- A plain scroll or two-finger swipe pans. Dragging empty space pans. Double-clicking empty space fits.
- "Fit" shows the whole graph, centered, with a small margin.
- On load: if `selected` names a run config, zoom to 100% centered on it. Otherwise, fit.
- When the detail panel opens or closes and the graph area changes width, the point at the center of the view stays at the center.

### Hover

Hovering a node shows a short tooltip next to it:

- Line 1: the run config name, or "Deleted run config".
- Line 2: the status. For Changed it lists the kinds ("Prompt, Model"). The others read "Starting point", "Copy or re-run, no changes", "Parent deleted", "No recorded parent" or "This run config was deleted".
- Line 3: the model display name with its provider ("GPT 5 (OpenAI)"), the MCP tool name for MCP run configs, or nothing for placeholders.

### Selection

- Clicking a node selects it. This opens the detail panel and highlights its lineage.
- Clicking another node moves the selection. Clicking empty space does not clear it.
- The panel's close button or Esc clears the selection and closes the panel.
- The selected node gets a dark ring.
- The selection is mirrored to the URL as `selected=<id>`, using replaceState, so reloading keeps it. An unknown `selected` id is ignored and the page fits.

### Keyboard

- The graph area can be focused. It has a label: "Run config lineage graph".
- With focus and no selection, any arrow key selects the oldest starting point, or the first node if there is none.
- With a selection: Up selects the primary parent. Down selects the oldest child. Left and Right select the previous and next node in the same row. The view pans to keep the selected node visible.
- Esc closes the panel. `+`, `-` and `0` zoom in, zoom out and fit.

## Detail Panel

Opens on the right of the graph when a node is selected. It reuses the run config detail page's property list and does not invent a new layout.

From top to bottom:

1. **Header**: the node's square drawn large, the run config name, and a lineage line:
   - Starting point: "Starting point · N children".
   - One parent: "Derived from {parent name} · N children". The parent name is a link that selects the parent.
   - Several parents: "Derived from {primary} and {others, comma separated} · N children". Each name is a link.
   - No recorded parent: "No recorded parent".
   - Deleted placeholder: "This run config was deleted · N children".
   The close button sits at the top right.
2. **Changed from Parent** section (for a node with a live primary parent): one row per changed kind, in order. Each row has the kind's swatch, the kind's name, the new value, and the parent's value struck through underneath. Values are the same display strings the property list uses (prompt name, tool and skill names, model with provider, settings as "Temperature 0.7"). A Copy or re-run reads "Same settings as parent." A Parent deleted node reads "The parent run config was deleted, so changes can't be shown." This section is hidden for other statuses.
3. **Notes** section, when `provenance.notes` exists: the full notes as read-only text, plus who created it ("Created by an agent" or "Created by a person", from `provenance.origin`, omitted when unknown).
4. **Run Configuration** section: the same property list the run config detail page shows (`getRunConfigUiProperties` with `PropertyList`). Hidden for the deleted placeholder.
5. **Actions**:
   - "Compare to Parent" opens the Compare page with the parent and this run config in its two columns. It is shown only when the primary parent is a live run config.
   - "Run Configuration" opens the run config detail page. It is hidden for the deleted placeholder.
   - Neither is a primary button. This page has no primary button.

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

- Eval scores on the graph (pending open question 2).
- Mike's cards view, compare matrix, score lenses and inspector.
- Editing, cloning or deleting run configs from this page.
- Any change to the Compare page apart from the new link.
- A sidebar link.

## Open Questions

1. **Page name.** "Lineage" (the design, and your own word for it in your last message) or "Experiments" (your first brief)? The title, route, button and row menu item all follow it.
2. **Eval scores.** The design shows an "eval score" per run config: the best-score stat, a ring on the best node, the score in the tooltip, and the score with its change against the parent in the panel. Kiln has no single score per run config. A task has several evals, each eval has several output scores on different scales, and many run configs have never been evaluated. Data for all run configs is available in one existing call (`GET /api/projects/{project_id}/tasks/{task_id}/run_configs/eval_scores`).
   - **Option A:** no scores. The page stays a pure lineage view. Compare to Parent covers scores.
   - **Option B (recommended):** a later phase adds a "Score" picker: a dropdown listing each (eval, output score) pair, plus "None". It defaults to the highest-priority eval's first score. With a score chosen, the design's score features turn on. Nodes without a score show "No score". All score UI hides when "None" is picked or no run config has scores.
   - **Option C:** like B, but in the first build.
