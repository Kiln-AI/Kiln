# Handoff: Lineage page (Kiln, Optimize)

## Overview
A page that shows every configuration (prompt + tools + skills + model + hyperparameters) a user has run for a task, as a tree. Each child is derived from its parent. Every node shows **which of the five dimensions changed from its parent**. Several dimensions can change at once, which the old "prompt/tools/skills vs model" two-color legend couldn't show.

## About the design files
`lineage_page.html` + `lineage.js` are a **design reference written in plain HTML/JS**. They show the intended look and behavior. Don't ship them as-is. Rebuild the page in the Kiln web UI (`app/web_ui`, Svelte + Tailwind + daisyUI `kilntheme`) as a route rendered inside the existing `app_page.svelte` shell: `title="Lineage"`, subtitle as below. Only the **page content** is included. The sidebar and app shell already exist.

Open `lineage_page.html` directly in a browser to see it working (it uses generated sample data).

## Fidelity
**High-fidelity.** Colors, sizes, spacing and interactions are final. Use daisyUI/Tailwind equivalents where they exist (`btn`, `btn-primary`, `btn-mid`, `text-gray-500`, `font-light`, `border-base-300`, etc.).

## Node encoding (the core idea)
Each configuration is a small square (default **14×14px**, radius 2px). Its fill depends on **how many** dimensions changed versus its parent. Segments are always filled in the fixed order **Prompt → Tools → Skills → Model → Hyperparameters**, using only the dimensions that changed.

| Changes | Shape |
|---|---|
| 0 (copy / re-run) | Solid grey `#d1d5db` |
| 1 | Solid square in that dimension's color |
| 2 | Left half / right half |
| 3 | Left half + two right quarters (top-right, bottom-right) |
| 4 | Quadrants: TL, TR, BL, BR |
| 5 | Quadrants + a center square (40% of size, centered) holding the 5th color, outlined in white by the gap width |
| Starting point (root) | Solid `#131517` |

Segments are separated by a **1px white gap** at 14px (2px at 40px in the detail panel). Only internal edges are inset by half the gap. Outer edges stay flush. The reference implementation is `nodeRects()` in `lineage.js`.

### Dimension colors
| Dimension | Key | Color |
|---|---|---|
| Prompt | P | `#415CF5` (primary) |
| Tools | T | `oklch(0.6 0.17 290)` ≈ `#7a5af0` |
| Skills | S | `oklch(0.72 0.12 230)` ≈ `#4fa6d8` |
| Model | M | `oklch(0.68 0.17 45)` ≈ `#e8743a` |
| Hyperparameters | H | `oklch(0.82 0.15 85)` ≈ `#eebf45` |

Config dimensions use cool colors and model dimensions warm ones. These are new colors outside the theme. Add them as named tokens (for example `lineage-prompt`).

## Layout (inside the app_page content card)
Vertical stack, `gap: 24px`:

1. **Header row** (flex, wrap)
   - Left: eyebrow "Optimize" (12px, gray-500); H1 "Lineage" (24px/700); subtitle "Every configuration you’ve run, and what changed from its parent." (14px, font-light, gray-500).
   - Right: three stats, right-aligned, gap 24px: value 24px/500 tabular-nums, label 12px gray-500: **configurations**, **models** (distinct), **best eval score**.
2. **Filter row** (flex wrap, gap 8px)
   - Label "Changed from parent" (14px/500) + ⓘ info tooltip: "Each square shows what changed from its parent configuration. One change fills the square. More changes split it, always in the order prompt, tools, skills, model, hyperparameters. Click to filter."
   - Six toggle chips: Prompt, Tools, Skills, Model, Hyperparameters, Copy or re-run. Each chip is 32px high, padding 0 12px, radius 8px, 1px `#e5e7eb` border, white background, 13px text. It holds a 12px swatch (radius 2), the name, and a count in gray-500 tabular-nums. Hover: bg `#f9fafb`. **Active**: border `#161616`, weight 500.
   - Counts overlap: one configuration counts toward every dimension it changed.
   - A "Clear" text button (gray-500, underlined) appears when any filter is active.
3. **Body** (flex wrap, gap 16px)
   - **Graph card**: `flex: 1 1 520px`, 1px `#e5e7eb` border, radius 8px.
     - Toolbar (padding 8px 12px, bottom border): hint text "Click a configuration to see its details. Hover for a summary." (12px gray-500). Zoom controls on the right: − / "100%" / +, buttons 28×28px, radius 6, 1px border.
     - Scroll area: height 560px, overflow auto both ways, padding 16px.
   - **Detail panel**: `flex: 0 1 340px`, min-width 300px, 1px `#e5e7eb` border, radius 8px, padding 20px, gap 20px. It wraps below the graph on narrow widths.

## Graph
- **Tidy tree layout**: leaves placed left→right at `size + gap` spacing (gap = max(3, round(size×0.3)) = 4px at 14px). Parents are centered over their first and last child. Row height = 2 × node size (28px).
- **Edges**: elbow paths: down from the parent's bottom center, across at mid-row, down into the child's top center. Stroke `#d1d5db` 1px.
- **Selected lineage**: edges from root to the selected node are stroked `#161616` at 1.5px.
- **Selected node**: ring `0 0 0 2px #fff, 0 0 0 3.5px #161616`.
- **Best-scoring node**: ring `0 0 0 1.5px #fff, 0 0 0 3px #33B79D` (success).
- **Filtering**: nodes that don't match any active chip drop to opacity 0.15. The selected node stays at 1. Matching uses OR across chips.
- **Zoom**: 50%–200% in 25% steps. Scale the graph layer with `transform: scale()` from the top-left, and size the outer wrapper to `w×zoom, h×zoom` so scrolling works.
- **Initial scroll**: center on the best configuration.
- **Hover tooltip** (shown next to the node, not scaled): white card, 1px `#e5e7eb` border, radius 6, shadow-md, padding 8px 10px, 12px text.
  - Line 1 (500, base color): "Configuration #ID" or "Starting point".
  - Line 2: changed dimension names joined by ", ", or "Copy or re-run, no changes".
  - Line 3: "model · score 0.84".

## Detail panel
- Visible on load with the **best** configuration selected. A close button (✕, 28×28, top-right 12px, gray-500, hover bg `#f3f4f6`) hides the panel and clears the selection and lineage highlight. Clicking any node shows the panel again.
- **Header**: the node drawn at 40px (radius 4, gap 2px) + title "Configuration #ID" (16px/500). A "Best" pill (success background, white text, 12px/500) appears if it's the best node. Subline (13px gray-500): "Child of #PARENT · N children". #PARENT is a link that selects the parent. The root shows "Starting point · N children".
- **Score row**: score 24px/500 tabular + "eval score" label. Delta right-aligned: "+0.03 vs parent", 13px/500, `#1f8a74` if ≥0, `#c2391f` if <0.
- **Config list** (top border): heading "N of 5 changed from parent" / "Same settings as parent" / "Configuration" (root), 13px/500. Then five rows, always in P, T, S, M, H order. Grid columns are `12px 124px 1fr`, padding 8px 0, bottom border `#f3f4f6`, 13px text.
  - Swatch: the dimension color if changed. Otherwise white with a 1px `#d1d5db` border.
  - Label: gray-500.
  - Value: the current value, weight 500 if changed. If changed, the parent's value appears below it at 12px, gray-500, struck through.
  - The Model row shows the provider logo (14px) before the model name.
  - Value formats: "Prompt v14", tool and skill lists joined by ", " or "None", model id, "temperature 0.3 · max 1024 tokens".
- **Actions** (bottom): `btn-primary` "Open in Run" (the single primary on the screen) and default `btn` "Compare to Parent". Compare is disabled (opacity 0.4) for the root.

## State
- `selectedId: number | null`: defaults to the best node's id. Set to null on close.
- `hoverId: number | null`
- `filters: Set<'P'|'T'|'S'|'M'|'H'|'C'>` (C = copy / re-run)
- `zoom: number` (0.5–2, default 1)

## Data requirements
Per configuration: `id`, `parentId`, the full config (prompt version/id, tools[], skills[], model id + provider, hyperparameters), and an eval score. **Compute `changed` by diffing against the parent** for each of the five dimensions. Don't store it. The sample generator in `lineage.js` (`generate()`) is only for the demo. Replace it with real data.

## Assets
`assets/providers/*.svg`: provider logos, copied from the Kiln repo (`app/web_ui/static/images/`). Use the existing ones in the codebase. The ⓘ, ✕ and zoom glyphs are simple inline SVGs: use Kiln's existing info_tooltip and close icons.

## Files
- `lineage_page.html`: page markup and CSS (content area only).
- `lineage.js`: encoding (`nodeRects`), tree layout (`layout`), rendering and interactions, sample data generator.
- `assets/providers/`: provider logos used in the Model row.
