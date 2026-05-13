---
status: complete
---

# UI Design: Multiturn Trace Forking

UI is scoped to the multiturn run-detail page (`/dataset/{p}/{t}/{run_id}/run`). No other surfaces change.

## Existing Layout (Reference)

The multiturn run-detail page currently renders:

1. Properties panel + rating UI (existing run-detail page chrome).
2. **TraceComponent** — a vertical list of role-collapsed blocks (system / user / assistant / tool), each rendered as a DaisyUI `collapse collapse-arrow bg-base-200`. Header shows role label (left), one-line preview (middle), expand arrow (right). Body shows full content when expanded.
3. **Bottom composer** — appends a new turn N+1.

This project introduces a fork affordance on user blocks and an inline composer that opens at the forked position.

## Fork Affordance

### Placement

A fork button is rendered **inside the expanded body of each eligible user block** (the DaisyUI `.collapse-content`), positioned at the bottom-right of the expanded content — adjacent to the existing copy-to-clipboard-style affordances we use elsewhere. The user must expand a turn to see (and click) its fork button; the collapsed header remains a pure click-to-expand target.

The original design placed the fork button in the collapsed header (next to the expand arrow). UI signoff round 2 surfaced a click-target conflict: the header is itself the expand toggle, so a button there competes with the collapse click and forces awkward propagation hacks. Moving the button into the expanded body resolves the conflict and matches the user's gesture flow — they almost always want to see what they're forking before they fork, which means expanding the turn anyway.

Eligibility rules (from the functional spec):

- User blocks only.
- Turn 1's user block: **no** fork button.
- Turns 2..N user blocks (including the leaf): fork button shown, when the ancestor for that turn is resolved.
- Any user block above a broken chain point: no fork button.

### Visual

- A small square icon button with a branch-style icon, no text label by default.
- Right-aligned within a row at the bottom of the expanded user block's content.
- Tooltip on hover: `"Fork from here"`.
- Accessible label: `aria-label="Fork from this turn"`.
- Size: matches the small icon-button pattern (`btn btn-sm btn-square`, ~h-8/w-8). Muted (gray-400) by default; darkens on hover.
- Hidden when the block is collapsed (it lives inside `.collapse-content`, which Svelte does not render until the block is expanded).

### Icon choice

Use a fork / branch icon (Git-branch metaphor). Rationale: "fork" is the conceptual model — we are creating a sibling branch, not editing the original message. Calling it "Edit" would mislead users into thinking the original is mutated.

> **Judgment call worth flagging.** If you'd prefer a different metaphor (e.g. "Retry from here" with a refresh-style icon) say the word — the label/icon swap is a one-line change.

## Inline Composer (Fork Mode)

### Position

When fork is activated on turn K:

1. Turn K's user block and **all subsequent blocks** (turn K's assistant/tool messages, plus turns K+1..N) collapse out of the visible flow. The blocks remain in the DOM (rendered, but hidden via a Svelte conditional) so reopening them on Cancel is instant. The system block and turns 1..K-1 stay rendered as normal.
2. An inline composer renders in the position where turn K's user block was.
3. The bottom composer is hidden while the inline composer is open.

### Composition

The inline composer is a re-skinned use of the same `composer.svelte` already used at the bottom — we don't fork the component. New props:

- `mode: "append" | "fork"` (default `"append"`).
- `prefill_text?: string` (in fork mode, the original turn K user text).
- `forked_turn_index?: number` (used for the heading; e.g. `"Forking turn 3"`).
- `on_cancel?: () => void` (fork mode only).
- `parent_task_run_id` is already a prop / derived; in fork mode it is set to turn K-1's run id, not the leaf's.

### Layout

The inline composer renders a thin context strip above the textarea:

```
┌──────────────────────────────────────────────────────────────┐
│ ↪ Forking turn 3        Original message preserved on parent │
└──────────────────────────────────────────────────────────────┘
[ run config picker ]
[ textarea, prefilled with original turn-3 text         ]
[ Cancel ]                                  [ Send ]
```

- The context strip uses a muted background and an arrow / branch icon to reinforce "this is a fork."
- The "Cancel" button is a `btn btn-ghost`; "Send" is the primary action button (matching the existing composer).
- The run config picker defaults to **turn K's original run config** (per the functional spec), with the user free to switch.
- Pending state on Send disables both buttons and shows a spinner on Send (matches existing composer behavior).
- Send failure shows an inline error above the buttons; the user's text is preserved; retry is just clicking Send again.

### Cancel behavior

- Closes the inline composer.
- Re-expands the hidden blocks (turn K onward) to their previous state.
- Re-shows the bottom composer.
- If the inline composer has unsaved edits (the textarea content differs from the original prefill), prompt a small confirmation dialog: `"Discard your changes?"` with Discard / Keep editing. If the content is unchanged, close without confirmation.

### Switching fork target

If a user clicks fork on another user block while a fork is already open:

- If the composer has unsaved edits: confirmation dialog (`"Discard your current fork edits and fork from turn N instead?"`).
- If clean: swap immediately. The previously hidden blocks re-show up to the new fork point; turn N and beyond hide; prefill updates; run config defaults update.

### Send

- POSTs `/run` with `parent_task_run_id` = turn K-1's run id and the new text.
- On success: SvelteKit `goto` to `/dataset/{p}/{t}/{new_run_id}/run` with `replaceState: true`.
- On failure: inline error.

## Broken-Chain State

When the ancestors endpoint returns `chain_broken: true`:

- A non-blocking alert banner renders **above the conversation** (above the TraceComponent), using the DaisyUI `alert alert-warning` style:

  > ⚠ Some earlier turns can't be forked because their run data is missing or corrupted. Forking is still available for later turns.

- The banner is dismissible (small × on the right) per the existing alert convention.
- For user blocks above the break, no fork button is rendered (per the functional spec).
- The bottom composer remains functional.

If the ancestors endpoint fails outright (network / 5xx, not a graceful `chain_broken`):

- A different banner: `"Couldn't load conversation history. Forking is unavailable."`
- No fork buttons rendered anywhere.
- Bottom composer continues to work (it only needs the leaf id).

## Empty / Edge States

- **Turn 1 alone (single-turn-style conversation that happens to be on a multiturn task).** No fork buttons anywhere (turn 1 is ineligible). Bottom composer continues to work as the only entry point for additional turns.
- **Single eligible turn (N=2).** Fork button appears only on the leaf's user block. This is correct — turn 1 is hidden, turn 2 is leaf and forkable.
- **Wide chains (N large).** Fork buttons render on every eligible user block — they don't crowd because the affordance is small and lives inside the existing header.

## Responsive Behavior

The page is desktop-first today; we don't change that. The fork button is small enough that it fits in the existing header row on narrow viewports. The inline composer reuses the existing composer's layout, which already adapts to the page width.

## Accessibility

- The fork button is a `<button>` element (not a div) with an explicit `aria-label="Fork from this turn"`.
- The button is focusable; pressing Enter or Space activates it.
- The inline composer's textarea receives focus on open, with cursor positioned at the end of the prefilled text.
- The cancel-confirmation dialog is a DaisyUI `<dialog>` (modal) — keyboard-dismissible with Escape.
- The broken-chain banner has `role="alert"`.

## Components Touched / Created

| File | Change |
|---|---|
| `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/+page.svelte` | Fetch ancestors on load; pass mapping to TraceComponent; manage fork state (open/closed, target turn). |
| `app/web_ui/src/lib/ui/trace/trace.svelte` | Accept new optional props: `forkable_run_ids?: (string \| null)[]` (positional, same length as `trace`), `on_fork?: (run_id: string, turn_index: number) => void`. Render fork button in user block header when `forkable_run_ids[i]` is set. |
| `app/web_ui/src/routes/(app)/dataset/[project_id]/[task_id]/[run_id]/run/multiturn_send.ts` | Used as-is (already accepts `parent_task_run_id`). |
| Composer component (existing — likely inlined in the page today; see architecture step) | Add `mode`, `prefill_text`, `forked_turn_index`, `on_cancel` props and render the fork-mode context strip + Cancel button when in fork mode. |
| New: small Fork icon (SVG component under `app/web_ui/src/lib/ui/icons/`) | Branch / fork icon. |

The TraceComponent is the right place for the fork button because it's the component that already knows about message structure. The page-level component coordinates the fork state because it owns the composer and the navigation.

## Out of Scope (Visual)

- Sibling navigation widgets (e.g. "Branch 2 of 3" pagination on user blocks).
- A branch-tree visualization.
- Animations on truncate/restore (we use instant hide/show; nice-to-have, not required).
- Mobile-specific layout tweaks beyond what the existing page already does.

## Open Questions

1. **Icon + label.** I chose a fork/branch icon, no text label, tooltip "Fork from here." Alternatives: "Retry from here" with a refresh icon; an explicit text button reading "Fork". My pick keeps the row uncluttered for long conversations, but if you want better discoverability at the cost of a wider footer, we can show a short text label.

2. **Expanded-only visibility.** The fork button is only visible when the user block is expanded (see Placement). For first-time users this means the affordance is one click less obvious than an always-visible header button. We accepted this trade-off because the header is itself a click-to-expand target, and putting an interactive button there created a click-target conflict during signoff round 2. If discoverability becomes a complaint, an alternative would be a tiny hover-revealed icon outside the collapse container (e.g. floating to the right of the block) — not in v1.
