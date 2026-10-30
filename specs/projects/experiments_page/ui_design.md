---
status: complete
---

# UI Design: Experiment Lineage Page

This doc turns the design handoff (`design_reference/`) into a Kiln screen. The handoff's layout, node encoding and interactions are the goal. Kiln's style guide (`.agents/frontend_design_guide.md`, `.agents/frontend_controls.md`, the `kiln-ui` skill) wins wherever the two disagree. Behavior is defined in `functional_spec.md`. This doc covers look and controls.

**Sibling screens:** the run config detail page (`routes/(app)/optimize/[project_id]/[task_id]/run_config/[run_config_id]/`), whose property list the detail panel reuses, and the Optimize page, for header buttons and the table frame.

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
| Custom chips (white, 8px radius, dark border when on) | House selection buttons: off `btn btn-sm btn-outline`, on `btn btn-sm btn-secondary` | The Rating and Feedback recipe is the house toggle. |
| "Clear" underlined text button | `button.link` with `text-sm text-gray-500` | Same idiom as AppPage's `sub_subtitle` action. |
| ⓘ glyph | `InfoTooltip` | House control. |
| Custom 28px zoom buttons | `btn btn-sm` in a DaisyUI `join` | Default grey button. |
| Graph card, 8px radius border | Table frame: `rounded-lg border` | The only box that fits a pan and zoom area. The table frame is the documented one. |
| Detail panel as a bordered card | No box. A column beside the graph, sections titled with `SettingsHeader` | House rule: content sits on the page. |
| Custom ✕ close button | The `Dialog` close button classes | The existing house close button. |
| Panel config rows (custom grid) | "Changed from Parent" keeps a small custom diff list. The full config is the existing `PropertyList` from `getRunConfigUiProperties` | The ask was to reuse the run config component. No house control shows old and new values, so the diff list is the one custom element in the panel. |
| "Open in Run" `btn-primary`, "Compare to Parent" | "Compare" and "Compare to Parent", both `btn btn-mid` | The panel already shows everything the run config detail page does, so there's no link to it. The page has no single main action, so it has no primary button. |
| White tooltip card, 12px text | `InfoTooltip`'s popover look: `bg-stone-200 rounded-md shadow-lg px-3 py-2 text-sm`, left aligned, positioned with `@floating-ui/dom` | One tooltip look across the app. |
| 13px and 12px text | `text-sm` and `text-xs` | DaisyUI and Tailwind sizes only. |
| Zoom 50–200% only, scroll to pan | Zoom from min(50%, fit) to 200%. Drag and scroll pan. Fit button added. | You asked for Fit/+/− and pan, like Mike's. |
| Single parent per node | Every parent drawn. Extra parents dashed. | Merges are part of the story. |
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
| Edges | `base-300`, 1px |
| Selected lineage edges | `secondary`, 1.5px |
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

The same glyph is drawn at 40px (radius 4px, gap 2px) in the panel header, and at 12px (radius 2px) as chip and diff-row swatches. One pure function returns the rectangles for a list of kinds and a size. It is the only place the encoding lives.

## Page Layout

```
Optimize >                                              [breadcrumb]
Experiment Lineage                                      [AppPage title]
Every run configuration for this task, and what changed from its parent.   [AppPage subtitle]

182                       17                            [stats row]
run configurations        models

Changed from parent (i)  [■ Prompt 31] [■ Tools 25] [■ Skills 12] [■ Model 112] [■ Settings 41] [■ Copy or re-run 26]  Clear

┌───────────────────────────────────────────────┐   Gusty Forest              (x)
│ Click a run config for details.   [−]100%[+][Fit]│   Derived from Calm River · 3 children
│                                               │
│               (graph, pan and zoom)           │   Changed from Parent ──────────
│                                               │   ■ Tools   web_search, sql_query
│                                               │             ~~web_search~~
│                                               │   Notes ────────────────────────
│                                               │   (Output)
│  No recorded parent (12)                      │   Run Configuration ────────────
│  ■ ■ ■ ■ ■ ■ ■ ■ ■ ■ ■ ■                      │   (PropertyList)
└───────────────────────────────────────────────┘   [Compare] [Compare to Parent]
```

- Vertical rhythm: the page content is one `flex flex-col gap-6`. Children carry no margins.
- **Stats row**: `flex gap-10`. Each stat is a column: the number as `text-xl font-medium tabular-nums`, the label under it as `text-sm text-gray-500`. Left aligned. No box, no divider. There's no house stat control, so this is a justified custom element.
- **Filter row**: `flex flex-wrap items-center gap-2`. The label is `text-sm font-medium` with `InfoTooltip`. Each chip is a `btn btn-sm` (outline when off, secondary when on) holding a 12px swatch glyph, the name, and the count. The count is `text-gray-500` when off and `opacity-70` when on, so it stays readable on black.
- **Body**: `flex gap-6`. It fills the window's remaining height: measure the body's top offset on mount and on resize, set the height to `100vh − top − bottom padding`, minimum 420px. At `lg` and wider, the panel (fixed 360px) sits right of the graph. Below `lg`, the body stacks, the graph keeps a fixed 480px height, and the panel sits below it.
- **Graph frame**: `rounded-lg border`, `flex flex-col`, `overflow-hidden`.
  - Toolbar: a row with `px-3 py-2 border-b`. Left: hint "Click a run config for details. Hover for a summary." as `text-xs text-gray-500`. Right: a DaisyUI `join` of `btn btn-sm`: "−", the zoom percentage as non-interactive text, "+", "Fit". Buttons have `aria-label`s: "Zoom out", "Zoom in", "Fit graph".
  - Canvas: fills the rest. One SVG holds a single group with the zoom and pan transform. Edges are drawn first, then nodes. Cursor: `grab` on empty space and `grabbing` while dragging, `pointer` on nodes.
  - "No recorded parent (N)" label: SVG text in the graph, `text-xs`, `fill-gray-500`, above the grid.
- **Detail panel**:
  - Header row: 40px glyph, then a column with the name (`text-lg font-medium`, truncated with a `title`) and the lineage line (`text-sm text-gray-500`, parent names as `link` buttons). The close button sits at the top right of the panel, using `Dialog`'s close button classes and the same icon.
  - Sections, each a `SettingsHeader` over its body:
    - "Changed from Parent": a grid `grid-cols-[12px_auto_1fr] gap-x-3 gap-y-2 text-sm`. Swatch, then the kind name in `text-gray-500`, then a value column. The new value is `font-medium`. The old value sits under it as `text-xs text-gray-500 line-through`. The Model row shows the provider logo (`get_provider_image`, 14px) before the model name. Long tool and skill lists wrap.
    - "Notes": `Output` with the notes text. Under it, "Created by an agent" or "Created by a person" as `text-sm text-gray-500`.
    - "Run Configuration": `PropertyList` with `getRunConfigUiProperties(...)`. It has the same content as the detail page. The input transform action opens the same `InputTransformModal`.
  - Actions row: `grid grid-cols-2 gap-2`, so the two `btn btn-mid` are the same size.
  - The panel scrolls on its own (`overflow-y-auto`) when it's taller than the body.
- **Hover tooltip**: shown after a short delay (100ms) and hidden on leave. It's anchored to the hovered node's screen rectangle, placed to the right with a flip. It isn't scaled with the zoom. Line 1 is `font-medium`. Lines 2 and 3 are normal weight.

## Empty and Edge States

- No run configs: `Intro` with the title "No Run Configurations Yet", one paragraph on what lineage shows, and a "Create Run Config" button.
- No lineage at all: info `Warning` (default size) above the graph frame. The graph shows just the grid.
- Selected node hidden by a filter: it stays at full opacity (functional spec).
- Very long run config names: truncate in the panel header and the tooltip, with the full name in `title`.

## Entry Point Placement

- Optimize page, Run Configurations header: `btn btn-mid` "Experiment Lineage", first in the row, before "Compare". Hidden in select mode. The three buttons don't fit beside the title at narrower widths (for example 1024px with the Assistant pane open), so the button group wraps (`flex-wrap`, right-aligned with `sm:justify-end`) and a button drops to a second line. The title keeps the rest of the row (`sm:basis-0`) but never narrows below `min-w-44`, so "Run Configurations" stays on one line. At 1440px with the Assistant pane open, all three buttons fit on one line. The same applies in select mode.
- Optimize page, row `TableActionMenu`: "Show in Experiment Lineage", after "Set as Task Default".
- Compare page: AppPage `action_buttons` entry `{ label: "Experiment Lineage", href: "/optimize/{project_id}/{task_id}/experiment_lineage" }`.
- From the panel:
  - "Compare" links to `/specs/{project_id}/{task_id}/compare?from=optimize&columns=2&models={this_id},`. The trailing comma leaves column 2 empty, the same way Compare writes its own URL.
  - "Compare to Parent" links to `/specs/{project_id}/{task_id}/compare?from=optimize&columns=2&models={parent_id},{this_id}`.
  - `from=optimize` makes Compare's breadcrumb point back to Optimize.

## Component Plan (Seed)

The coding agent completes this per the `kiln-ui` skill. It is listed here so the review lens has a starting point.

| Element | House control | Justification if custom |
|---|---|---|
| Title, breadcrumb, subtitle | `AppPage` | |
| Stats row | Custom | No house stat control. AppPage has no slot for it. |
| "Changed from parent" label tip | `InfoTooltip` | |
| Filter chips | Rating and Feedback selection recipe | Adds a swatch and a count inside the button. |
| Clear | `button.link` | |
| Graph frame | Table frame `rounded-lg border` | Pan and zoom needs a visible edge. |
| Zoom controls | `btn btn-sm` in `join` | |
| Graph canvas, nodes, edges | Custom SVG | No house control draws graphs. |
| Hover tooltip | `InfoTooltip` popover look and `@floating-ui/dom` | `InfoTooltip` anchors to its own "i" icon, not to an SVG node. |
| Panel section titles | `SettingsHeader` | |
| Changed-from-parent rows | Custom grid | No house control shows a value with its previous value. |
| Notes | `Output` | |
| Run config properties | `PropertyList` with `getRunConfigUiProperties` | |
| Panel close | `Dialog` close button classes | |
| Panel actions | `btn btn-mid` | |
| Empty state | `Intro` | |
| No-lineage message | `Warning` (info) | |
