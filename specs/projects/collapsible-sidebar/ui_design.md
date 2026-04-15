---
status: complete
---

# UI Design: Collapsible Sidebar

Scope: visual & interaction design of the **icon rail** state of the left sidebar. The full (expanded) sidebar is unchanged and out of scope.

## Rail Dimensions

- **Width:** `56px` (matches current sidebar icon size `1.25rem` = 20px + 18px padding each side). Set as a named constant (e.g. `RAIL_WIDTH_PX = 56`) so it can be referenced from chat_bar sizing logic if needed.
- **Background:** `bg-base-200` (same as full sidebar).
- **Vertical padding:** `pt-3 pb-3` top/bottom, matching current sidebar.
- **Item gap:** ~4px between siblings (matches current `margin-bottom: 4px` on sidebar-menu `li`).

## Rail Column Structure (top to bottom)

All items centered horizontally within the 56px column.

```
┌──────┐
│ ◯    │  Logo (28px animated_logo.svg, no wordmark)
│      │
│ [ J ]│  Task chip (32×32 rounded square with uppercase letter)
│      │
│  ▶   │  Run
│  💬  │  Chat
│  🗄  │  Dataset
│  📋  │  Specs & Evals
│      │
│ ──── │  hr
│OPTIM.│  "OPTIMIZE" label (clickable → /optimize/...)
│  📝  │    Prompts
│  📦  │    Models
│  🔧  │    Tools
│  🎯  │    Skills
│  📄  │    Docs & Search
│  🎛  │    Fine Tune
│  ✨  │    Synthetic Data
│ ──── │  hr
│      │
│ ↕flex↕│  (spacer, pushes items below to bottom)
│      │
│  •   │  Progress trigger (when active) — floats full widget to right via <Float>
│      │
│  ⚙︎• │  Settings (dot badge overlaid when update available)
└──────┘
```

## Item Specs

### Icons

- **Size:** `20×20` (`w-5 h-5`) — same as current `sidebar-icon`.
- **Stroke color:** `currentColor` (inherits from link color).
- **Hit area:** full 56px column × ~36px height per item (`py-2`). Click target is the whole row, not just the icon.

### Active state

- `bg-base-300` on the hit area (full row width inside the rail), same rounding as current menu items (`rounded-md`).
- No additional accent bar, dot, or color change.

### Hover state

- `bg-base-300/50` (lighter) on the hit area.

## Task Chip

- **Container:** `32×32` rounded square (`w-8 h-8 rounded-md`), border `border-base-300`, background `bg-base-100`.
- **Letter:** first char of `$current_task.name`, uppercased. Font: `text-sm font-medium`. Color: `text-base-content`.
- **No chevron** in rail.
- **Click:** opens `taskDialog` (existing `SelectTasksMenu`).
- **Blank state** (no task): empty chip, same container rendered; no letter. (Redirect expected — not a designed-for state.)
- **Tooltip:** two lines via `SidebarRailTooltip variant="multi"`. Line 1 = task name (medium weight); line 2 = project name (`text-gray-500`). When both are empty the tooltip is not rendered.

## OPTIMIZE Divider Group

- **Top rule:** `<div class="h-px bg-base-300 mx-2 my-2"></div>` (thin separator that respects rail padding).
- **Label:** small uppercase text. `text-[10px] font-semibold tracking-wider text-gray-500`, centered in the 56px column. Text content: `OPTIM…` — **needs to fit in 56px**. Options:
  - **Option A (preferred):** full word `OPTIMIZE` at `text-[9px]` tracking-wide — fits comfortably.
  - **Option B:** abbreviate to `OPT` if readability of the full word is poor at that size after visual review.
- **Clickable:** the label is an `<a>` pointing to `/optimize/$project_id/$task_id`; hover shows `bg-base-300/50`; tooltip "Optimize" on hover.
- **Children:** Prompts, Models, Tools, Skills, Docs & Search, Fine Tune, Synthetic Data — rendered flat (no indent), same icon styling as other nav items. (Synthetic Data lives in the OPTIMIZE group in the rail even though the full sidebar renders it separately.)
- **Bottom rule:** same as top rule, below Fine Tune.
- Active state of the children: same `bg-base-300` rule as other nav items. If the current section is one of these children, the OPTIMIZE **label** is not independently highlighted.

## Tooltips

- **Implementation:** shared `sidebar_rail_tooltip.svelte` built on `$lib/ui/float.svelte` (portaled, so it escapes any overflow clipping). DaisyUI tooltip proved too rigid for the multi-line task-chip case, so all rail tooltips use the same Float-based primitive.
- **Trigger:** on hover or focus of the rail item (owner tracks the boolean).
- **Content:** single-line label for nav items, settings, and the OPTIMIZE label. Multi-line for the task chip.
- **Task chip tooltip:** two lines — task name in `font-medium`, project name in `text-gray-500`. Uses `variant="multi"` on the shared tooltip.
- **Tooltip color:** `bg-neutral` / `text-neutral-content`.

## Progress Indicator (Rail)

- **Trigger (rail slot):** a small pip — `w-3 h-3 rounded-full bg-primary` centered in a 36px row, when `progress_ui_state` is non-null. Clickable (same hit area as a nav item).
- **Float:** the full `ProgressWidget` component is rendered **unchanged** inside `<Float placement="right-start" offset_px={8}>` anchored to the trigger. Widget becomes visible whenever `progress_ui_state` is non-null (not hover-gated).
- **Visual containment:** the widget has its own bordered card styling already; no changes.
- **Z-index:** widget must sit above the main content (Float uses fixed positioning, `z-50` equivalent).

## App Update Dot (Settings)

- **Dot:** `w-2 h-2 rounded-full bg-primary`, absolutely positioned top-right of the Settings icon (`-top-0.5 -right-0.5`).
- **Container:** Settings icon wrapper becomes `relative` to anchor the dot.
- **Tooltip when dot shown:** `Settings — Update Available`.
- **Tooltip when no update:** `Settings`.

### Settings page — "Update Available" header

- Rendered at the **top** of `/settings` (above existing sections), only when `$update_info.update_result?.has_update` is true.
- Styling: matches the pattern used by other section headers on the settings page (same heading typography).
- Layout: header text `Update Available` with a subordinate link/button `View update →` routing to `/settings/check_for_update`.
- Visual emphasis: a subtle primary-tinted border/background on the section to draw attention without being alarming. Final visual decided during implementation; lean on existing DaisyUI `alert alert-info` or a bordered card with `border-primary/30`.

## Logo (Top of Rail)

- `/images/animated_logo.svg`, `w-7 h-7` (28×28, matches current). Centered. No text.
- Non-interactive (no link, no tooltip — matches today).

## Layout Transitions

Per functional spec: **container snaps, content animates on expand only.**

- **Container (outer `<div class="drawer-side">` sidebar `<ul>`):** width is set imperatively based on `isRailActive` — `56px` when rail, else `w-72 md:w-52 2xl:w-56`. Width change is not transitioned (instant).
- **Interior content:** two distinct layouts (rail vs full). On **rail → full** transition, the full-layout content uses a 250ms linear slide-in animation (`translateX(-20px)` → `translateX(0)` with opacity `0` → `1`), matching chat_bar's `.chat-expand-x` timing.
- **Collapse (full → rail):** interior content swaps instantly, no animation.

## Responsive Behavior

- **`< lg` (1024px):** sidebar behavior unchanged — off-canvas drawer with full layout. Rail not used.
- **`lg` and ≥ 1550px:** full sidebar always (even if chat open).
- **`lg` and < 1550px + chat open:** rail (except on the `/chat` page, where the chat bar is hidden and there is no width pressure).
- **`lg` and < 1550px + chat closed:** full sidebar.

## Accessibility

- **Tooltips are not the only affordance:** every nav item already has a link with an `aria-label` equal to the label text (or the text is present inside the `<a>` in the DOM — hidden visually via `sr-only` in rail state rather than removed).
- **Keyboard focus:** same as today — items are reachable via Tab; focus ring visible.
- **Active state:** conveyed via `aria-current="page"` on the active link (addition — not present today, worth adding in the rail refactor but out of scope for full sidebar behavior change).

## Open Visual Questions (parked for implementation / visual review)

- Final OPTIMIZE label rendering (full word vs. `OPT`) — decide after seeing it in situ at 9px.
- ~~Whether the multi-line task chip tooltip looks acceptable with DaisyUI's built-in tooltip; may require a custom tooltip.~~ **Resolved:** DaisyUI was rejected during implementation; all rail tooltips use the shared Float-based `sidebar_rail_tooltip.svelte`.
- Final rail width may nudge ±4px based on icon alignment.

These are resolved during implementation / the "tooltip cleanup" follow-up phase, not now.
