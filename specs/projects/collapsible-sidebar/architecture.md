---
status: complete
---

# Architecture: Collapsible Sidebar

This is a frontend-only change in `app/web_ui`. No backend / API changes. Small scope → a single architecture doc, no per-component docs needed.

## File Inventory

### New files

| Path | Purpose |
|---|---|
| `app/web_ui/src/lib/stores/viewport.ts` | Reactive viewport width store + `isLg` / `isNarrowViewport` derived stores (narrow = `< 1550px`). |
| `app/web_ui/src/lib/stores/chat_ui_state.ts` | Shared `chatBarExpanded` writable, init from existing storage, setter persists. |
| `app/web_ui/src/routes/(app)/sidebar_rail.svelte` | Icon-rail presentation of the left nav. |
| `app/web_ui/src/routes/(app)/sidebar_rail_item.svelte` | Single icon row (icon slot, href, label, active state, tooltip). |
| `app/web_ui/src/routes/(app)/sidebar_rail_task_chip.svelte` | Task letter chip with two-line tooltip. |
| `app/web_ui/src/routes/(app)/sidebar_rail_optimize_group.svelte` | Divider + `OPTIMIZE` clickable label + flat children. |
| `app/web_ui/src/routes/(app)/sidebar_rail_progress.svelte` | Rail progress trigger + `<Float>`-wrapped `ProgressWidget`. |
| `app/web_ui/src/routes/(app)/sidebar_rail_settings.svelte` | Settings icon with update-dot overlay (subscribes to `update_info` directly). |
| `app/web_ui/src/routes/(app)/sidebar_rail_tooltip.svelte` | Shared tooltip primitive used by every rail item (wraps `$lib/ui/float.svelte`). |

### Modified files

| Path | Change |
|---|---|
| `app/web_ui/src/routes/(app)/+layout.svelte` | Conditionally render `sidebar_rail.svelte` in place of the full `<ul>` when rail is active. Track `isRailActive` via derived store. Apply one-shot slide-in animation class on rail→full transition. |
| `app/web_ui/src/routes/(app)/chat_bar.svelte` | Read/write via shared `chatBarExpanded` store instead of local state + direct storage calls. |
| `app/web_ui/src/lib/chat/chat_ui_storage.ts` | Unchanged — still the persistence layer used by the new store. |
| `app/web_ui/src/routes/(app)/settings/+page.svelte` | Prepend an inline "Update Available" callout card (not a `KilnSection`) when `$update_info.update_result?.has_update`. |

## State / Data Flow

```
viewport.ts        ─ width, isLg, isNarrowViewport ─┐
chat_ui_state.ts   ─ chatBarExpanded ───────────────┤─► derived isRailEligible ──► showRail ──► +layout.svelte
                                                    │    (lg && narrow && chat)      (&& section !== Chat)   (chooses rail vs full)
+layout.svelte     ─ section (from pathname) ───────┘
```

### `viewport.ts`

```ts
import { readable, derived } from "svelte/store"
import { browser } from "$app/environment"

export const viewportWidth = readable(
  browser ? window.innerWidth : 0,
  (set) => {
    if (!browser) return
    const onResize = () => set(window.innerWidth)
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  },
)

export const isLg = derived(viewportWidth, (w) => w >= 1024)
export const isNarrowViewport = derived(viewportWidth, (w) => w < 1550)
```

### `chat_ui_state.ts`

```ts
import { writable } from "svelte/store"
import { browser } from "$app/environment"
import {
  getChatBarExpanded,
  setChatBarExpanded as persistChatBarExpanded,
} from "$lib/chat/chat_ui_storage"

const initial = browser ? getChatBarExpanded() : true
export const chatBarExpanded = writable<boolean>(initial)

export function setChatBarExpanded(expanded: boolean): void {
  chatBarExpanded.set(expanded)
  if (browser) persistChatBarExpanded(expanded)
}
```

`chat_bar.svelte` then imports `chatBarExpanded` and `setChatBarExpanded` from this module. The local `expanded` variable is replaced by subscribing to the store (`$chatBarExpanded`). All writes go through `setChatBarExpanded`.

### `isRailEligible` + `showRail` (in +layout.svelte)

```ts
import { derived } from "svelte/store"
import { isLg, isNarrowViewport } from "$lib/stores/viewport"
import { chatBarExpanded } from "$lib/stores/chat_ui_state"

const isRailEligible = derived(
  [isLg, isNarrowViewport, chatBarExpanded],
  ([$lg, $narrow, $chatOpen]) => $lg && $narrow && $chatOpen,
)

// chat_bar hides itself on /chat, so there's no width pressure there — keep
// the full sidebar regardless of eligibility.
let showRail = false
$: showRail = $isRailEligible && section !== Section.Chat
```

Rendered in +layout.svelte:

```svelte
{#if showRail}
  <SidebarRail {section} openTaskDialog={...} />
{:else}
  <ul class="sidebar-menu ..." class:sidebar-slide-in={justExitedRail}>
    ... (existing full sidebar contents)
  </ul>
{/if}
```

### Animation: rail → full slide-in

The container width snaps (one `if/else` branch vs the other — no width transition). The interior of the full sidebar animates with a one-shot CSS class.

```ts
let justExitedRail = false
let prevRailActive = false
$: {
  if (prevRailActive && !showRail) {
    justExitedRail = true
    setTimeout(() => (justExitedRail = false), 250)
  }
  prevRailActive = showRail
}
```

```css
.sidebar-slide-in {
  animation: sidebar-slide-in 250ms linear;
}
@keyframes sidebar-slide-in {
  from {
    transform: translateX(-20px);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
```

Rail does **not** get a slide-in / slide-out animation — it appears/disappears instantly.

## Component Specs

### `sidebar_rail.svelte`

```svelte
<script lang="ts">
  import { Section } from "$lib/ui/section"
  import { ui_state } from "$lib/stores"
  import { update_info } from "$lib/utils/update"
  import SidebarRailItem from "./sidebar_rail_item.svelte"
  import SidebarRailTaskChip from "./sidebar_rail_task_chip.svelte"
  import SidebarRailOptimizeGroup from "./sidebar_rail_optimize_group.svelte"
  import SidebarRailProgress from "./sidebar_rail_progress.svelte"
  import SidebarRailSettings from "./sidebar_rail_settings.svelte"
  // + icon imports (same as +layout.svelte today)

  export let section: Section = Section.None
  export let openTaskDialog: () => void
</script>

<nav
  class="bg-base-200 text-base-content w-[56px] min-h-full flex flex-col items-stretch pt-3 pb-3 gap-1"
  aria-label="Primary"
>
  <!-- Logo -->
  <div class="flex justify-center mb-2">
    <img src="/images/animated_logo.svg" alt="Kiln" class="w-7 h-7" aria-hidden="true" />
  </div>

  <SidebarRailTaskChip on:open={openTaskDialog} />

  <SidebarRailItem href="/" active={section === Section.Run} label="Run">
    <RunIcon slot="icon" />
  </SidebarRailItem>
  <SidebarRailItem href="/chat" active={section === Section.Chat} label="Chat">
    <ChatIcon slot="icon" />
  </SidebarRailItem>
  <!-- Dataset, Specs & Evals -->

  <!-- OPTIMIZE divider group: Prompts, Models, Tools, Skills, Docs, Fine Tune, Synthetic Data -->
  <SidebarRailOptimizeGroup {section} />

  <div class="flex-1"></div>  <!-- spacer -->
  <SidebarRailProgress />
  <SidebarRailSettings active={section === Section.Settings} />
</nav>
```

Props:
- `section: Section` — current section (from +layout.svelte URL matching).
- `openTaskDialog: () => void` — callback passed down to task chip.

`SidebarRailSettings` subscribes to `update_info` directly (same pattern as `SidebarRailProgress` subscribing to `progress_ui_state`) instead of taking a `hasUpdate` prop — keeps a single source of truth for update state.

Top-level element is `<nav aria-label="Primary">` rather than `<ul class="sidebar-menu menu ...">`. Semantic nav is better than a `<ul>` when the items aren't a plain list.

### `sidebar_rail_item.svelte`

```svelte
<script lang="ts">
  import SidebarRailTooltip from "./sidebar_rail_tooltip.svelte"
  export let href: string
  export let active: boolean = false
  export let label: string

  let hovered = false
  let focused = false
  $: show_tooltip = hovered || focused
</script>

<div class="flex justify-center">
  <a
    {href}
    class="relative flex items-center justify-center w-10 h-9 rounded-md {active ? 'bg-base-300' : 'hover:bg-base-300/50'}"
    aria-label={label}
    aria-current={active ? 'page' : undefined}
    on:mouseenter={() => (hovered = true)}
    on:mouseleave={() => (hovered = false)}
    on:focus={() => (focused = true)}
    on:blur={() => (focused = false)}
  >
    <span class="w-5 h-5 block">
      <slot name="icon" />
    </span>
    <SidebarRailTooltip show={show_tooltip}>{label}</SidebarRailTooltip>
  </a>
</div>
```

### `sidebar_rail_task_chip.svelte`

Renders the uppercase first letter of `$current_task?.name` inside a 32×32 rounded chip. On hover/focus, a multi-line tooltip (via `SidebarRailTooltip variant="multi" role="tooltip"`) shows task name (medium) over project name (gray). No tooltip is shown when both are empty.

### `sidebar_rail_tooltip.svelte`

Shared tooltip primitive used by `sidebar_rail_item`, `sidebar_rail_settings`, `sidebar_rail_optimize_group`, and `sidebar_rail_task_chip`. Props:

- `show: boolean` — whether the tooltip is visible (owner tracks hover/focus).
- `variant: "single" | "multi"` — `"single"` is a one-line label bubble (default), `"multi"` is a left-aligned column for richer content (task chip).
- `role: string` — defaults to `"none"` (the tooltip content duplicates the anchor's `aria-label`, so it is purely visual). Task chip passes `"tooltip"` because its content includes the project name which is not in the `aria-label`.
- `aria_hidden: boolean` — defaults to `true`; task chip passes `false` to let AT read the tooltip.

Wraps `$lib/ui/float.svelte` with `placement="right"` and `portal` so the tooltip escapes any clipping by the narrow rail column.

### `sidebar_rail_optimize_group.svelte`

Renders: top 1px divider, the `OPTIMIZE` label-link (small text `text-[9px] font-semibold tracking-wider text-gray-500`, tooltip "Optimize" via `SidebarRailTooltip`), then seven child `SidebarRailItem`s (Prompts, Models, Tools, Skills, Docs & Search, Fine Tune, Synthetic Data), then a closing 1px divider. Synthetic Data lives inside this group even though the full sidebar renders it separately — grouping it keeps the rail visually compact.

### `sidebar_rail_progress.svelte`

```svelte
<script lang="ts">
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import ProgressWidget from "$lib/ui/progress_widget.svelte"
  import Float from "$lib/ui/float.svelte"
</script>

{#if $progress_ui_state}
  <div class="flex justify-center relative py-2">
    <div
      class="w-3 h-3 rounded-full bg-primary"
      aria-label="In progress"
      role="img"
    ></div>
    <Float
      placement="right-start"
      offset_px={12}
      role="region"
      aria_label="Progress"
    >
      <ProgressWidget />
    </Float>
  </div>
{/if}
```

Float anchors to parent element (per float.svelte `referenceElement = contentElement.parentElement`). The wrapping `<div>` is therefore the reference. The full `ProgressWidget` is rendered unchanged. The pip carries `role="img"` with `aria-label="In progress"` and the Float wrapper is exposed as `role="region"` with `aria-label="Progress"` so assistive tech can reach the widget.

### `sidebar_rail_settings.svelte`

Settings link with optional dot overlay. Subscribes to `$update_info` directly (no `hasUpdate` prop). When `$update_info.update_result?.has_update` is true: render a primary dot at top-right and switch `aria-label` to "Settings, update available" and tooltip to "Settings — Update Available". Uses `SidebarRailTooltip` for hover feedback.

### Settings page — "Update Available" callout

Modify `app/web_ui/src/routes/(app)/settings/+page.svelte`. Per UI signoff the `KilnSection`-based approach (originally planned below) was rejected — it made the update item look like just another section. The final design is a compact blue-tinted callout card rendered inline in the template **above** the `{#each sections}` loop, outside the `sections` array:

```svelte
{#if $update_info.update_result?.has_update}
  <div
    class="card card-bordered border-primary/30 bg-primary/5 shadow-sm rounded-md"
    data-testid="update-available-callout"
  >
    <!-- icon bubble + title/description + "View Update" primary button
         linking to /settings/check_for_update -->
  </div>
{/if}
{#each sections as section}
  <KilnSection ... />
{/each}
```

The `sections` array itself is unchanged. The "Check for Update" item in Help & Resources stays (it lets users force a check even when `has_update` is false).

## Design Patterns & Rationale

| Decision | Rationale |
|---|---|
| Stores for viewport + chat state | Multiple components need them; Svelte stores are the idiomatic cross-component pattern; keeps `+layout.svelte` simple. |
| Component extraction for rail | Keeps `+layout.svelte` readable; rail subcomponents are independently testable. |
| Instant width snap + slide-in animation only | Matches user decision: avoids reflowing main content during animation; matches chat_bar expand timing. |
| Shared `sidebar_rail_tooltip.svelte` primitive (Float-based, portaled) | All four rail components need hover/focus-driven tooltips; the multi-line task-chip content pushed us off DaisyUI's `::before`/`data-tip` pattern to a single Float-based primitive shipped in this phase. |
| `<Float>` for ProgressWidget | User-directed; keeps widget unchanged while freeing it from the 56px column. |
| Settings "Update Available" as an inline callout card (not a `KilnSection`) | Per UI signoff: a `KilnSection` rendering made the update item blend in with the other sections. A compact blue-tinted callout above the sections stands out without introducing a new reusable component. |

## Technical Challenges

1. **Multi-line task-chip tooltip** — shipped as `sidebar_rail_tooltip.svelte` (Float-based, portaled) with `variant="multi"` for the two-line task name + project layout; all four rail components use the same primitive.

2. **SSR / hydration of viewport store**
   - `window` is unavailable during SSR. `readable` initializer uses `browser ? window.innerWidth : 0`. Derived `isLg` returns `false` during SSR, so server-rendered markup = full sidebar (same as today), and hydration switches to rail if needed. This causes a brief flash of full sidebar on first paint. Acceptable — same trade-off as the existing chat_bar which already uses `browser ? getChatBarExpanded() : true`.

3. **`<Float>` inside a list item**
   - `float.svelte` attaches to `contentElement.parentElement`. The `<li>` must have `position: relative` or any non-static, and not `overflow: hidden`. Sidebar `<ul>` already uses default overflow. Verify no parent clips; if so, the Float widget's fixed positioning bypasses it anyway (strategy: "fixed" by default).

4. **Avoiding duplicate state for `chatBarExpanded`**
   - Current `chat_bar.svelte` reads `browser ? getChatBarExpanded() : true` once and keeps local state. Migrate to the new store with a single source of truth. Persistence is still in the existing module; only initialization and setter go through the store.

## Error Handling

- Storage unavailable: `chat_ui_storage.ts` already swallows errors; no changes needed.
- `current_task`/`current_project` null: task chip renders blank (specified).
- SSR: handled via `$app/environment` `browser` flag (pattern already used).
- No network calls introduced.

## Testing Strategy

Run with `npm run test_run` from `app/web_ui`.

### Unit / store tests

- `viewport.ts`:
  - `isLg` false when width < 1024; true when ≥.
  - `isNarrowViewport` true when < 1550; false when ≥.
  - `viewportWidth` updates on `resize` event (dispatch event, assert store value).
  - Subscribe/unsubscribe releases listener.

- `chat_ui_state.ts`:
  - Store initialized from storage getter.
  - `setChatBarExpanded(true)` updates store and calls persistence.

### Component tests (Vitest + @testing-library/svelte)

- `sidebar_rail_task_chip.svelte`:
  - Renders uppercase first letter when task is set.
  - Blank when no task.
  - Emits `open` event on click.
  - On hover, a `[role="tooltip"]` element appears (in `document.body` via portal) whose content contains both the task name and project name. No tooltip is rendered when both are empty.

- `sidebar_rail_settings.svelte`:
  - Renders dot when `hasUpdate=true`.
  - No dot when false.
  - Tooltip text reflects update state.

- `sidebar_rail_item.svelte`:
  - `aria-current="page"` when active.
  - On hover, the shared tooltip element (`data-testid="rail-tooltip"`) appears with text equal to `label`; disappears on mouseleave.

- `+layout.svelte` rail selection:
  - Full sidebar when `isLg=true, narrow=false, chatOpen=true` (width ≥ 1550).
  - Rail when `isLg=true, narrow=true, chatOpen=true`.
  - Full sidebar when `isLg=true, narrow=true, chatOpen=false`.
  - Not rail when `isLg=false`.
  - Tested by overriding stores before render.

- Settings page update section:
  - Section rendered when `has_update=true`.
  - Section absent when `has_update=false`.

### Manual QA

- Visual check of tooltip multi-line rendering.
- Animation timing & absence of main-content reflow on expand.
- Viewport resize across both breakpoints (lg, 1550px) with chat open + closed.
- `<Float>` progress widget positioning under scroll + with small/large viewport.

## Out of Scope (explicit)

- No refactor of the full sidebar markup.
- No changes to `progress_widget.svelte` internals.
- No changes to `info_tooltip.svelte` (deferred to tooltip-cleanup phase, contingent on visual review).
- No changes to mobile drawer behavior.
