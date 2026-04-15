---
status: complete
---

# Functional Spec: Collapsible Sidebar

## Goal

When the chat pane is open and horizontal space is limited, collapse the main left nav (`app/web_ui/src/routes/(app)/+layout.svelte`) to a narrow **icon rail** so that the main content area retains usable width. When space returns (user closes chat, or viewport widens past the threshold), revert to the normal sidebar.

## Trigger

The rail is shown iff **all** of the following are true:

- Viewport is large (`lg` breakpoint and above — `min-width: 1024px`). Below `lg`, sidebar behavior is unchanged (off-canvas drawer).
- Chat pane is open (`expanded === true` in `chat_bar.svelte`).
- Viewport width is **< 2000px**.

Otherwise the full sidebar is shown (existing design, no changes).

The rail state is **purely derived** from the above. No manual toggle, no persistence, no user-facing control to override it. Closing the chat is the only user-visible way to bring the full sidebar back while on a narrow viewport.

## Transition Behavior

The **sidebar container width** always **snaps** (instant). The main content area therefore reflows exactly once per transition — no width animation on the main column. Only the **content inside the sidebar** animates.

- **Collapse** (full → rail): container width snaps to rail width. Interior content snaps to rail layout (instant — no animation).
- **Expand** (rail → full): container width snaps to full width. Interior content **animates in from the left** (slide) with the same timing as the chat pane expand (**250ms linear**, matching `chat_bar.svelte` `.chat-expand-x`). Because the container is already at full width when the animation starts, the main content does not re-layout during the animation.
- **Resize across the 2000px threshold** while chat is open: snap in both directions (no animation).

## Rail Layout (top to bottom)

All items are **vertically stacked**, centered in a narrow column. Rail width is designer-selected (target ≈ 56px, enough for a 20px icon + comfortable padding — final value set in the UI design / implementation).

1. **Logo** — Kiln animated logo (`/images/animated_logo.svg`), no wordmark. Non-interactive (matches current — it's decorative).
2. **Task selector chip** — a single uppercase letter inside a small square/rounded box; chevron removed; click opens the task picker dialog (same `taskDialog` as today).
3. **Primary nav items (single icons):**
   - Run
   - Chat
   - Dataset
   - Specs & Evals
4. **"OPTIMIZE" divider group** — horizontal rule above, small uppercase "OPTIMIZE" label (tap target acts as the old Optimize parent link — i.e. navigates to `/optimize/...`). Below the label, the six former children are shown flat (no indent): Prompts, Models, Tools, Skills, Docs & Search, Fine Tune. A matching horizontal rule closes the group below Fine Tune.
5. **Synthetic Data** — single icon (below the OPTIMIZE group).
6. **(spacer — pushes the below items to the bottom)**
7. **Progress indicator** (when `progress_ui_state` is active) — see "Progress indicator in rail" below.
8. **Settings** — single icon. When an app update is available, a small badge dot is overlaid on the Settings icon (see "App update in rail" below).

## Tooltips

Every icon / chip in the rail shows a tooltip on hover. Used to replace the text label that's hidden.

- **Position:** right side of the icon, vertically centered.
- **Delay:** 0ms enter, 0ms leave (can be tuned later).
- **Implementation:** start with DaisyUI `tooltip tooltip-right` utility classes.
- **Content:**
  - Nav items: the same label used today ("Run", "Chat", "Dataset", "Specs & Evals", "Prompts", "Models", "Tools", "Skills", "Docs & Search", "Fine Tune", "Synthetic Data", "Settings").
  - OPTIMIZE label: "Optimize" (tooltip on hover of the text label).
  - Task chip: a two-line tooltip showing the task name and project name, matching the visual weight of the current in-sidebar component (task name in medium weight, project name in lighter/gray). If no task is selected the chip is blank (a redirect is expected in that state, so tooltip content is unspecified).

> **Refactor follow-up (later phase):** if after visual review we keep DaisyUI tooltip, refactor `info_tooltip.svelte` so its logic is shared with the rail tooltips. If we swap to a custom tooltip, leave `info_tooltip.svelte` untouched.

## Task Chip

- **Letter:** first character of `$current_task.name`, uppercased.
- **No task selected:** blank chip. This state is not expected to be visible to users (an upstream redirect covers it), so no explicit fallback design is required.
- **Chevron:** removed in rail state (only present in the full sidebar as today).
- **Click:** opens the existing `SelectTasksMenu` dialog (same binding as the full sidebar's task button).
- **Tooltip:** task name (medium weight) over project name (lighter/gray). Mirrors the typography of the full-sidebar task button.

## Progress Indicator in Rail

When `progress_ui_state` is non-null, the rail shows a small trigger (e.g. a dot / mini progress pip) in the same slot where `ProgressWidget` lives today (above Settings). The **full `ProgressWidget` component is rendered unchanged** using the `<Float>` component (`app/web_ui/src/lib/ui/float.svelte`), anchored to the rail slot and floated out to the right.

- The trigger is compact (sits inside the rail column); the floated widget is the existing widget with no visual compromises (same title, body, progress bar / steps, CTA, close button).
- `<Float>` placement: `right-start` (or similar — final placement chosen in UI design). The widget follows the trigger on scroll/resize via `autoUpdate`.
- Show/hide of the float: always rendered while `progress_ui_state` is non-null (i.e. the widget is visible whenever the rail shows it, not a hover-only popover). The trigger itself is the visible rail element; the float is the full widget beside it.
- All existing widget behavior (click → navigate to `$state.link`, auto-clear on arrival, × close) is preserved.

## App Update Indicator in Rail

When `$update_info.update_result?.has_update` is true, the dedicated "App Update Available" list item is removed from the rail. Instead:

- A small **primary-colored dot badge** is overlaid on the top-right corner of the Settings icon.
- The Settings tooltip changes to "Settings — Update Available" when the badge is shown.
- Clicking Settings routes to `/settings` (not `/settings/check_for_update`). Rationale: the rail is space-constrained; the dot is a discoverability cue, not a direct CTA.

### Settings page — "Update Available" header (required change)

So the user can still act on / understand the dot after landing on `/settings`, add an **"Update Available"** header/section to the top of the `/settings` page. This appears **only when `has_update` is true** and provides the same affordance the removed rail pill did: a clear CTA to visit `/settings/check_for_update`. Styling matches existing section headers on the settings page. Header wording: **"Update Available"**; body/CTA: link text like "View update →" pointing to `/settings/check_for_update`.

This header is visible on the settings page regardless of whether the rail is active (it's a page-level affordance, not rail-specific).

## Active Section Indicator

Same styling as today: `bg-base-300` on the active item. No additional accent bar or special treatment.

## OPTIMIZE Group (applies in rail only)

- **Scope:** this divider-group layout (horizontal rule + small label + flat children) is **only** used in the rail. The full sidebar retains its current nested-parent design.
- **Label** ("OPTIMIZE") is clickable and acts as the old "Optimize" parent link — navigates to `/optimize/$project_id/$task_id`.
- **Children** in the rail are flat (no indent): Prompts, Models, Tools, Skills, Docs & Search, Fine Tune.

## Mobile / Small Screens

Below the `lg` breakpoint: behavior is unchanged. The sidebar is an off-canvas drawer toggled by the hamburger button. The rail is **not** used on mobile.

## Configuration / Constants

- **Collapse threshold:** 2000px viewport width (hard-coded constant, named for reuse).
- **Rail width:** TBD in UI design step, target ≈ 56px.
- **Expand animation:** 250ms linear, matching `chat_bar.svelte` expand.

## Out of Scope

- Persistence of rail state.
- Manual toggle control for the rail.
- Collapsing the sidebar when the chat pane is closed.
- Redesigning the full (expanded) sidebar.
- Redesigning `ProgressWidget` outside the rail.
- Changes to mobile/small-screen drawer behavior.
- Changes to `info_tooltip.svelte` (unless the deferred refactor phase runs).
- Changes to `ProgressWidget` internals (it's rendered as-is via `<Float>`).

## Edge Cases

- **Chat open, viewport resizes from ≥2000px to <2000px:** sidebar snaps from full → rail.
- **Chat open, viewport resizes from <2000px to ≥2000px:** sidebar snaps rail → full (no animation).
- **Viewport <2000px, user closes chat:** rail → full with 250ms slide-in-from-left animation.
- **Viewport <2000px, user opens chat (from closed):** sidebar snaps full → rail instantly.
- **Viewport crosses `lg` breakpoint** (to mobile): rail disappears, drawer behavior takes over (current behavior).
- **No task selected:** task chip is blank; redirect is expected to resolve this before the user sees the state.
- **App update flag toggles on while rail is active:** dot badge appears on Settings icon immediately; settings tooltip updates.
- **Progress state clears while rail is active:** progress indicator disappears immediately.
