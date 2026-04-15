---
status: complete
---

# Architecture: Collapsible Sidebar

This is a frontend-only change in `app/web_ui`. No backend / API changes. Small scope → a single architecture doc, no per-component docs needed.

## File Inventory

### New files

| Path | Purpose |
|---|---|
| `app/web_ui/src/lib/stores/viewport.ts` | Reactive viewport width store + `isLg` / `isBelow2000` derived stores. |
| `app/web_ui/src/lib/stores/chat_ui_state.ts` | Shared `chatBarExpanded` writable, init from existing storage, setter persists. |
| `app/web_ui/src/routes/(app)/sidebar_rail.svelte` | Icon-rail presentation of the left nav. |
| `app/web_ui/src/routes/(app)/sidebar_rail_item.svelte` | Single icon row (icon slot, href, label, active state, tooltip). |
| `app/web_ui/src/routes/(app)/sidebar_rail_task_chip.svelte` | Task letter chip with two-line tooltip. |
| `app/web_ui/src/routes/(app)/sidebar_rail_optimize_group.svelte` | Divider + `OPTIMIZE` clickable label + flat children. |
| `app/web_ui/src/routes/(app)/sidebar_rail_progress.svelte` | Rail progress trigger + `<Float>`-wrapped `ProgressWidget`. |
| `app/web_ui/src/routes/(app)/sidebar_rail_settings.svelte` | Settings icon with update-dot overlay. |

### Modified files

| Path | Change |
|---|---|
| `app/web_ui/src/routes/(app)/+layout.svelte` | Conditionally render `sidebar_rail.svelte` in place of the full `<ul>` when rail is active. Track `isRailActive` via derived store. Apply one-shot slide-in animation class on rail→full transition. |
| `app/web_ui/src/routes/(app)/chat_bar.svelte` | Read/write via shared `chatBarExpanded` store instead of local state + direct storage calls. |
| `app/web_ui/src/lib/chat/chat_ui_storage.ts` | Unchanged — still the persistence layer used by the new store. |
| `app/web_ui/src/routes/(app)/settings/+page.svelte` | Prepend an "Update Available" section when `$update_info.update_result?.has_update`. |

## State / Data Flow

```
viewport.ts        ─ width, isLg, isBelow2000 ─┐
chat_ui_state.ts   ─ chatBarExpanded ──────────┤─► derived isRailActive ──► +layout.svelte
                                               │                            (chooses rail vs full)
+layout.svelte     ─ section (from pathname) ──┘
```

### `viewport.ts`

```ts
import { readable, derived } from "svelte/store"
import { browser } from "$app/environment"

export const viewportWidth = readable(
  browser ? window.innerWidth : 0,
  (set) => {
    if (!browser) return () => {}
    const onResize = () => set(window.innerWidth)
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  },
)

export const isLg = derived(viewportWidth, (w) => w >= 1024)
export const isBelow2000 = derived(viewportWidth, (w) => w < 2000)
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

### `isRailActive` (in +layout.svelte)

```ts
import { derived } from "svelte/store"
import { isLg, isBelow2000 } from "$lib/stores/viewport"
import { chatBarExpanded } from "$lib/stores/chat_ui_state"

const isRailActive = derived(
  [isLg, isBelow2000, chatBarExpanded],
  ([$lg, $narrow, $chatOpen]) => $lg && $narrow && $chatOpen,
)
```

Rendered in +layout.svelte:

```svelte
{#if $isRailActive}
  <SidebarRail {section} />
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
  if (prevRailActive && !$isRailActive) {
    justExitedRail = true
    setTimeout(() => (justExitedRail = false), 250)
  }
  prevRailActive = $isRailActive
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

<ul class="sidebar-menu menu bg-base-200 w-[56px] p-0 pt-3 min-h-full">
  <!-- Logo -->
  <li class="flex justify-center mb-3">
    <img src="/images/animated_logo.svg" alt="Kiln" class="w-7 h-7" />
  </li>

  <SidebarRailTaskChip on:open={openTaskDialog} />

  <SidebarRailItem href="/" active={section === Section.Run} label="Run">
    <RunIcon slot="icon" />
  </SidebarRailItem>
  <SidebarRailItem href="/chat" active={section === Section.Chat} label="Chat">
    <ChatIcon slot="icon" />
  </SidebarRailItem>
  <!-- Dataset, Specs & Evals -->

  <SidebarRailOptimizeGroup {section} />

  <!-- Synthetic Data -->

  <li class="flex-1"></li>  <!-- spacer -->
  <SidebarRailProgress />
  <SidebarRailSettings active={section === Section.Settings} hasUpdate={$update_info.update_result?.has_update} />
</ul>
```

Props:
- `section: Section` — current section (from +layout.svelte URL matching).
- `openTaskDialog: () => void` — callback passed down to task chip.

### `sidebar_rail_item.svelte`

```svelte
<script lang="ts">
  export let href: string
  export let active: boolean = false
  export let label: string
</script>

<li class="flex justify-center">
  <a
    {href}
    class="tooltip tooltip-right flex items-center justify-center w-10 h-9 rounded-md {active ? 'bg-base-300' : 'hover:bg-base-300/50'}"
    data-tip={label}
    aria-label={label}
    aria-current={active ? 'page' : undefined}
  >
    <span class="w-5 h-5 block">
      <slot name="icon" />
    </span>
  </a>
</li>
```

### `sidebar_rail_task_chip.svelte`

```svelte
<script lang="ts">
  import { current_task, current_project } from "$lib/stores"
  import { createEventDispatcher } from "svelte"
  const dispatch = createEventDispatcher<{ open: void }>()
  $: letter = $current_task?.name?.[0]?.toUpperCase() ?? ""
  $: tip = `${$current_task?.name ?? ""}\n${$current_project?.name ?? ""}`
</script>

<li class="flex justify-center my-2">
  <button
    class="tooltip tooltip-right rail-chip-tooltip w-8 h-8 rounded-md border border-base-300 bg-base-100 text-sm font-medium flex items-center justify-center"
    data-tip={tip}
    on:click={() => dispatch("open")}
    aria-label={$current_task?.name ?? "Select task"}
  >
    {letter}
  </button>
</li>

<style>
  /* multi-line tooltip for task chip */
  :global(.rail-chip-tooltip.tooltip::before) {
    white-space: pre-line;
    text-align: left;
  }
</style>
```

The `:global(...)` selector reaches the pseudo-element generated by DaisyUI's tooltip. If DaisyUI's selector structure differs, the fallback is a custom absolute-positioned `<span>` tooltip (decided during implementation). This is the main "key algorithm" to validate early — if DaisyUI can't render multi-line tooltips cleanly, swap this one component to a hand-rolled tooltip.

### `sidebar_rail_optimize_group.svelte`

```svelte
<script lang="ts">
  import { Section } from "$lib/ui/section"
  import { ui_state } from "$lib/stores"
  import SidebarRailItem from "./sidebar_rail_item.svelte"
  export let section: Section
</script>

<div class="h-px bg-base-300 mx-2 my-2"></div>

<li class="flex justify-center">
  <a
    href="/optimize/{$ui_state.current_project_id}/{$ui_state.current_task_id}"
    class="tooltip tooltip-right w-10 h-5 flex items-center justify-center text-[9px] font-semibold tracking-wider text-gray-500 rounded hover:bg-base-300/50"
    data-tip="Optimize"
    aria-label="Optimize"
  >
    OPTIMIZE
  </a>
</li>

<SidebarRailItem ...Prompts.../>
<SidebarRailItem ...Models.../>
<SidebarRailItem ...Tools.../>
<SidebarRailItem ...Skills.../>
<SidebarRailItem ...Docs.../>
<SidebarRailItem ...FineTune.../>

<div class="h-px bg-base-300 mx-2 my-2"></div>
```

### `sidebar_rail_progress.svelte`

```svelte
<script lang="ts">
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import ProgressWidget from "$lib/ui/progress_widget.svelte"
  import Float from "$lib/ui/float.svelte"
</script>

{#if $progress_ui_state}
  <li class="flex justify-center relative">
    <div class="w-3 h-3 rounded-full bg-primary" aria-label="In progress"></div>
    <Float placement="right-start" offset_px={12}>
      <ProgressWidget />
    </Float>
  </li>
{/if}
```

Float anchors to parent element (per float.svelte `referenceElement = contentElement.parentElement`). The `<li>` is therefore the reference. The full `ProgressWidget` is rendered unchanged.

### `sidebar_rail_settings.svelte`

```svelte
<script lang="ts">
  export let active: boolean
  export let hasUpdate: boolean
</script>

<li class="flex justify-center">
  <a
    href="/settings"
    class="tooltip tooltip-right flex items-center justify-center w-10 h-9 rounded-md relative {active ? 'bg-base-300' : 'hover:bg-base-300/50'}"
    data-tip={hasUpdate ? "Settings — Update Available" : "Settings"}
    aria-label={hasUpdate ? "Settings, update available" : "Settings"}
    aria-current={active ? 'page' : undefined}
  >
    <SettingsIcon class="w-5 h-5" />
    {#if hasUpdate}
      <span class="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-primary"></span>
    {/if}
  </a>
</li>
```

### Settings page — "Update Available" section

Modify `app/web_ui/src/routes/(app)/settings/+page.svelte`:

```ts
import { update_info } from "$lib/utils/update"
// ...
$: sections = [
  ...($update_info.update_result?.has_update
    ? [{
        category: "Update Available",
        items: [{
          type: "settings",
          name: "New version available",
          description: "A new version of Kiln is ready to install.",
          button_text: "View Update",
          href: "/settings/check_for_update",
        } as KilnSectionItem],
      }]
    : []),
  // ...existing sections unchanged
]
```

The "Check for Update" item in Help & Resources stays (it lets users force a check even when `has_update` is false).

## Design Patterns & Rationale

| Decision | Rationale |
|---|---|
| Stores for viewport + chat state | Multiple components need them; Svelte stores are the idiomatic cross-component pattern; keeps `+layout.svelte` simple. |
| Component extraction for rail | Keeps `+layout.svelte` readable; rail subcomponents are independently testable. |
| Instant width snap + slide-in animation only | Matches user decision: avoids reflowing main content during animation; matches chat_bar expand timing. |
| DaisyUI `tooltip-right` first | Lowest-cost start. Refactor if visual review rejects; cleanup phase scheduled. |
| `<Float>` for ProgressWidget | User-directed; keeps widget unchanged while freeing it from the 56px column. |
| Settings "Update Available" as a KilnSection | Matches existing page patterns; no new component needed. |

## Technical Challenges

1. **Multi-line task-chip tooltip with DaisyUI**
   - DaisyUI tooltip renders via `::before` pseudo-element with content from `data-tip`. By default `white-space: normal`.
   - Plan: add `white-space: pre-line; text-align: left;` to `.rail-chip-tooltip.tooltip::before` globally (scoped to this component). Use `\n` in `data-tip`.
   - Fallback: if DaisyUI's selector or layout prevents clean multi-line rendering, drop in a small hand-rolled tooltip for this one component (conditional flag during implementation; note in PR description).
   - **Action:** implement the CSS-override path first; verify visually in browser before proceeding.

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
  - `isBelow2000` true when < 2000; false when ≥.
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
  - `data-tip` contains name + project joined by `\n`.

- `sidebar_rail_settings.svelte`:
  - Renders dot when `hasUpdate=true`.
  - No dot when false.
  - Tooltip text reflects update state.

- `sidebar_rail_item.svelte`:
  - `aria-current="page"` when active.
  - `data-tip` set to label.

- `+layout.svelte` rail selection:
  - Full sidebar when `isLg=true, narrow=false, chatOpen=true` (width ≥ 2000).
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
- Viewport resize across both breakpoints (lg, 2000px) with chat open + closed.
- `<Float>` progress widget positioning under scroll + with small/large viewport.

## Out of Scope (explicit)

- No refactor of the full sidebar markup.
- No changes to `progress_widget.svelte` internals.
- No changes to `info_tooltip.svelte` (deferred to tooltip-cleanup phase, contingent on visual review).
- No changes to mobile drawer behavior.
