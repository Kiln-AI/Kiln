---
status: complete
---

# UI Design: Experiment Lineage Page

This doc turns the design handoff (`design_reference/`) into a Kiln screen. The handoff's layout, node encoding and interactions are the goal. Kiln's style guide (`.agents/frontend_design_guide.md`, `.agents/frontend_controls.md`, the `kiln-ui` skill) wins wherever the two disagree. Behavior is defined in `functional_spec.md`. This doc covers look and controls.

**Sibling screens:** the run config detail page (`routes/(app)/optimize/[project_id]/[task_id]/run_config/[run_config_id]/`), whose property list the detail panel reuses; the spec page's sidebar (`routes/(app)/specs/[project_id]/[task_id]/[spec_id]/`), whose section titles the panel uses; and the Optimize page, for header buttons and the table frame.

## Where the Design Meets the Codebase

Each row is a place where the handoff can't be built as drawn, or where house style overrides it.

| Design | Resolution | Why |
|---|---|---|
| Eyebrow "Optimize" above the title | AppPage breadcrumb "Optimize" | The breadcrumb is the house eyebrow. |
| H1 24px/700, subtitle 14px light | AppPage `title` and `subtitle` | AppPage owns the page title. |
| Stats block at the top right of the header | A stats row in the page body, directly under the AppPage header, left aligned | AppPage has no slot at the top right. Adding one would change a shared control. |
| "best eval score" stat, "Best" pill, best ring, score in tooltip and panel | Not built | Kiln has no single score per run config. Decided: no scores on this page. |
| "Configuration #178" | The run config's name, for example "Gusty Forest" | Run configs have names, not small numbers. |
| "Prompt v14" | The prompt display name (`getRunConfigPromptDisplayName`) | Prompts have names, not versions. |
| "Hyperparameters", "temperature 0.3 · max 1024 tokens" | "Settings": temperature, top P, thinking level, structured output mode, input transform | Kiln has no max tokens setting. Input transform and output mode aren't hyperparameters. |
| Custom chips (white, 8px radius, dark border when on) | Legend chips: `btn btn-sm` with no outline, fill or shadow at rest, `bg-base-200` on hover, and `bg-base-200` with a `base-300` outline when on | You asked for chips that read as a legend: no outline at rest, light grey on hover, grey when on, never solid black. |
| "Clear" underlined text button | `button.link` with `text-sm text-gray-500` | Same idiom as AppPage's `sub_subtitle` action. |
| ⓘ glyph | Not built | You found the tooltip unneeded: the chips and squares explain themselves. |
| Custom 28px zoom buttons | `btn btn-sm` in a DaisyUI `join` | Default grey button. |
| Graph card, 8px radius border | Table frame: `rounded-lg border` | The only box that fits a pan and zoom area. The table frame is the documented one. |
| Detail panel as a bordered card | No box. A column beside the graph, sections titled in the sidebar section style (`text-xl font-bold`, no rule) | House rule: content sits on the page. The spec and Run pages title their sidebar sections this way, the same as `PropertyList`'s own title. |
| Custom ✕ close button | The `Dialog` close button classes | The existing house close button. |
| Panel config rows (custom grid) | Both "Changed from Parent" and the full config are `PropertyList`. The changes list fills its `custom_value` slot with the new value and a "was" line under it, or an "N added, N removed" link | One property list style across the panel: name on the left in the base color, value on the right in grey. |
| "Open in Run" `btn-primary`, "Compare to Parent" | A "Compare eval results to others" link under the Run Configuration title. No "Compare to Parent" | Run configs can have several parents, so one before-and-after pair doesn't fit. The panel already shows everything the run config detail page does, so there's no link to it. The page has no single main action, so it has no primary button. |
| White tooltip card, 12px text | `InfoTooltip`'s popover look: `bg-stone-200 rounded-md shadow-lg px-3 py-2 text-sm`, left aligned, positioned with `@floating-ui/dom` | One tooltip look across the app. |
| 13px and 12px text | `text-sm` and `text-xs` | DaisyUI and Tailwind sizes only. |
| Zoom 50–200% only, scroll to pan | Zoom from min(50%, fit) to 200%. Drag and scroll pan. Fit button added. | You asked for Fit/+/− and pan, like Mike's. |
| Single parent per node | Every parent drawn. Extra parents as light curves. | Merges are part of the story. |
| Initial selection: best node | No selection on load, unless `selected` is in the URL | There's no best node without scores. |
| Colors in `oklch`, new theme tokens | Colors from the shared chart palette (below) | One palette in code. |

## Color

### One Shared Chart Palette

The Compare charts (`lib/components/compare_chart.svelte`, `lib/components/compare_radar_chart.svelte`) use echarts' built-in default palette without naming it. In echarts 6.1.0 that palette is:

```
#5070dd #b6d634 #505372 #ff994d #0ca8df #ffd10a #fb628b #785db0 #3fbe95
```

A new shared file `lib/utils/chart_palette.ts` exports these nine colors as `CHART_PALETTE`. Both Compare charts set `color: CHART_PALETTE` in their echarts options, so their colors don't change, and the palette now has a name. The lineage page takes its change colors from the same constant.

### Change Colors

Kinds that change what the agent is told (prompt, tools, skills) use cool colors. Kinds that change what runs it (model, settings) use warm colors.

| Kind | Palette entry | Hex |
|---|---|---|
| Prompt | `CHART_PALETTE[0]` | `#5070dd` blue |
| Tools | `CHART_PALETTE[7]` | `#785db0` violet |
| Skills | `CHART_PALETTE[4]` | `#0ca8df` cyan |
| Model | `CHART_PALETTE[3]` | `#ff994d` orange |
| Settings | `CHART_PALETTE[5]` | `#ffd10a` yellow |

### Other Fills (Theme Tokens)

Applied with Tailwind's `fill-*` and `stroke-*` classes on the SVG, so they follow the DaisyUI theme.

| Use | Token |
|---|---|
| Copy or re-run | `base-300` |
| Starting point | `secondary` |
| Parent deleted, No recorded parent | `base-100` fill, `base-300` 1px outline |
| Deleted placeholder | `base-100` fill, `base-300` 1px dashed outline |
| Primary edges | `base-300`, 1px |
| Extra-parent curves | `base-300` at 60% opacity, 0.75px |
| Selected lineage edges, and the hovered node's edges | `secondary`, 1.5px |
| Selected ring | 2px `base-100` gap, then a 1.5px `secondary` ring |

## Node Glyph

From the handoff, unchanged. Node size 14px at 100% zoom, corner radius 2px. Segments are separated by a 1px white gap. Only internal edges are inset by half the gap, so outer edges stay flush. Kinds fill in the order Prompt, Tools, Skills, Model, Settings, using only the kinds that changed.

| Kinds changed | Shape |
|---|---|
| 1 | Solid |
| 2 | Left half, right half |
| 3 | Left half, top-right quarter, bottom-right quarter |
| 4 | Four quarters: top left, top right, bottom left, bottom right |
| 5 | Four quarters plus a center square (40% of the size) for the fifth kind, outlined in white by the gap width |

The same glyph is drawn at 40px (radius 4px, gap 2px) in the panel header, and at 12px (radius 2px) as chip swatches and beside each run config in the Lineage dialog. One pure function returns the rectangles for a list of kinds and a size. It is the only place the encoding lives.

## Page Layout

```
Optimize >                                              [breadcrumb]
Experiment Lineage                                      [AppPage title]
Every run configuration for this task, and how they evolved.   [AppPage subtitle]

182                       17                            [stats row]
run configurations        models

Changed from parent   ■ Prompt 31   ■ Tools 25   ■ Skills 12   ■ Model 112   ■ Settings 41   ■ Copy or re-run 26   Clear

┌───────────────────────────────────────────────┐   ██ Gusty Forest with a long    (x)
│ Click a run config for details.   [−]100%[+][Fit]│   ██ name that wraps to two…
│                                               │      Derived from 2 parents · 3 children
│               (graph, pan and zoom)           │      (Agent Created)
│                                               │
│                                               │   Notes
│                                               │   (Output)
│                                               │   Changed from Parent
│                                               │   Prompt   Support Prompt v7
│                                               │            was Support Prompt v1
│  No recorded parent (12)                      │   Tools    2 added, 1 removed
│  ■ ■ ■ ■ ■ ■ ■ ■ ■ ■ ■ ■                      │   Run Configuration
└───────────────────────────────────────────────┘   Compare eval results to others
                                                      (PropertyList)
```

- Vertical rhythm: the page content is one `flex flex-col gap-6`. Children carry no margins.
- **Stats row**: `flex gap-10`. Each stat is a column: the number as `text-xl font-medium tabular-nums`, the label under it as `text-sm text-gray-500`. Left aligned. No box, no divider. There's no house stat control, so this is a justified custom element.
- **Filter row**: `flex flex-wrap items-center gap-2`. The label is `text-sm font-medium`. Each chip is a `btn btn-sm font-normal shadow-none` holding a 12px swatch glyph, the name, and the count in `text-gray-500`. Off, it has a transparent fill and border, so it reads as a legend item. Hovered, it fills with `bg-base-200`. On, it has a `bg-base-200` fill and a `base-300` outline. It is never black.
- **Body**: `flex gap-6`. It fills the window's remaining height: measure the body's top offset on mount and on resize, set the height to `100vh − top − bottom padding`, minimum 420px. At `lg` and wider, the panel (fixed 360px) sits right of the graph. Below `lg`, the body stacks, the graph keeps a fixed 480px height, and the panel sits below it.
- **Graph frame**: `rounded-lg border`, `flex flex-col`, `overflow-hidden`.
  - Toolbar: a row with `px-3 py-2 border-b`. Left: hint "Click a run config for details. Hover for a summary." as `text-xs text-gray-500`. Right: a DaisyUI `join` of `btn btn-sm`: "−", the zoom percentage as non-interactive text, "+", "Fit". Buttons have `aria-label`s: "Zoom out", "Zoom in", "Fit graph".
  - Canvas: fills the rest. One SVG holds a single group with the zoom and pan transform. Edges are drawn first, then nodes, so an edge passes behind any node in its way. Cursor: `grab` on empty space and `grabbing` while dragging, `pointer` on nodes.
  - Edge shapes: a primary edge is an elbow that turns in the middle of the gap above the child's row. An extra-parent edge is a cubic S-curve with vertical ends. Its handles are half the vertical distance, capped at one row height (28px), so a long curve bends away from the nodes stacked right below its parent and right above its child. Edge widths don't scale with the zoom.
  - "No recorded parent (N)" label: SVG text in the graph, `text-xs`, `fill-gray-500`, above the grid.
- **Detail panel**: one `flex flex-col gap-8` column.
  - Header row: 40px glyph, then a `flex flex-col gap-1` column, then the close button at the top right of the panel, using `Dialog`'s close button classes and the same icon. The column holds:
    - The name as `text-xl font-bold line-clamp-2 break-words`, with the full name in `title`.
    - The lineage line as a `button.link` in `text-sm text-gray-500`, or plain text in the same style when there is nothing to list.
    - The creator badge as `badge badge-outline badge-primary badge-sm`.
  - Sections, each a section title over its body with `gap-4`. The title is `h2.text-xl.font-bold`, the sidebar section style of the spec and Run pages, which `PropertyList` also uses for its `title`. A local `lineage_panel_section.svelte` owns it, with a slot for a line right under the title.
    - "Notes": `Output` with the notes text.
    - "Changed from Parent": `PropertyList`, one property per changed kind, each filled through its `custom_value` slot. A single value is a column: the new value, then the "was" line as `text-xs font-light`. Both are `truncate` with a `title`, and both use `link` where there is a page. A list kind is a `button.link` reading "2 added, 1 removed". No swatches or provider logos, so the rows match the property list below.
    - "Run Configuration": under the title, "Compare eval results to others" as an `a.link` in `text-sm text-gray-500`. Then `PropertyList` with `getRunConfigUiProperties(...)`. It has the same content as the detail page. The input transform action opens the same `InputTransformModal`.
  - The panel scrolls on its own (`overflow-y-auto`) when it's taller than the body.
- **Lineage dialog** and **Tools Changed / Skills Changed dialogs**: `Dialog` at its normal width with a Close button (`isCancel`). The body is `flex flex-col gap-6 text-sm`. Each list is a `font-medium` heading over a `ul` with `gap-2`, one item per `li`, each `truncate` with a `title`. Lineage items start with a 12px glyph and are `button.link`; a deleted parent is `text-gray-500` text. Tool and skill items are `a.link` where `tool_link` gives a page, plain text otherwise.
- **Hover tooltip**: shown after a short delay (100ms) and hidden on leave. The hovered node's edges turn dark at the same moment and return to rest with it. It's anchored to the hovered node's screen rectangle, placed to the right with a flip. It isn't scaled with the zoom. Line 1 is `font-medium`. Lines 2 and 3 are normal weight.

## Empty and Edge States

- No run configs: `Intro` with the title "No Run Configurations Yet", one paragraph on what lineage shows, and a "Create Run Config" button.
- No lineage at all: info `Warning` (default size) above the graph frame. The graph shows just the grid.
- Selected node hidden by a filter: it stays at full opacity (functional spec).
- Very long run config names: two lines, then an ellipsis, in the panel header. One line in the tooltip and in the dialogs. The full name is in `title`.

## Entry Point Placement

- Optimize page, Run Configurations header: `btn btn-mid` "Experiment Lineage", first in the row, before "Compare". Hidden in select mode.
  - The header row is `flex flex-wrap items-center gap-x-8 gap-y-4`. The title block is `grow basis-80`, and the button group is its own `flex flex-wrap gap-3`.
  - When the title's 20rem and the buttons fit side by side, the buttons sit to the right of the title. At 1440px with the Assistant pane open, all three buttons are on one line beside the title.
  - When they don't fit (for example at 640px, or at 1024px and 1100px with the Assistant pane open), the whole button group moves to its own line under the subtitle, left-aligned with the title, and the subtitle gets the full width. The subtitle then reads on one or two lines, with no empty space beside the buttons. When the row is narrower than the buttons, they also wrap among themselves.
  - Select mode uses the same row, with "N selected", "Cancel Selection" and "Compare" in the group.
- Optimize page, row `TableActionMenu`: "Show in Experiment Lineage", after "Set as Task Default".
- Compare page: AppPage `action_buttons` entry `{ label: "Experiment Lineage", href: "/optimize/{project_id}/{task_id}/experiment_lineage" }`.
- From the panel, "Compare eval results to others" links to `/specs/{project_id}/{task_id}/compare?from=optimize&columns=2&models={this_id},`. The trailing comma leaves column 2 empty, the same way Compare writes its own URL. `from=optimize` makes Compare's breadcrumb point back to Optimize.

## Component Plan (Seed)

The coding agent completes this per the `kiln-ui` skill. It is listed here so the review lens has a starting point.

| Element | House control | Justification if custom |
|---|---|---|
| Title, breadcrumb, subtitle | `AppPage` | |
| Stats row | Custom | No house stat control. AppPage has no slot for it. |
| Filter chips | `btn btn-sm` with its fill, border and shadow set per state | The Rating and Feedback recipe has an outline at rest and a black fill when on. You asked for legend chips with neither. |
| Clear | `button.link` | |
| Graph frame | Table frame `rounded-lg border` | Pan and zoom needs a visible edge. |
| Zoom controls | `btn btn-sm` in `join` | |
| Graph canvas, nodes, edges | Custom SVG | No house control draws graphs. |
| Hover tooltip | `InfoTooltip` popover look and `@floating-ui/dom` | `InfoTooltip` anchors to its own "i" icon, not to an SVG node. |
| Panel section titles | Sidebar section title (`text-xl font-bold`), in `lineage_panel_section.svelte` | `SettingsHeader` draws a rule and a smaller title. The spec and Run page sidebars, and `PropertyList`'s `title`, use this style. |
| Creator badge | DaisyUI `badge badge-outline badge-primary badge-sm` | |
| Changed-from-parent rows | `PropertyList` with its `custom_value` slot | The slot holds the "was" line and the added and removed link, which no property type covers. |
| Notes | `Output` | |
| Run config properties | `PropertyList` with `getRunConfigUiProperties` | |
| Panel close | `Dialog` close button classes | |
| Compare link | `a.link` | |
| Lineage, Tools Changed and Skills Changed dialogs | `Dialog` | |
| Empty state | `Intro` | |
| No-lineage message | `Warning` (info) | |
