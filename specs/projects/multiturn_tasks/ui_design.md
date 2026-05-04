---
status: complete
---

# UI Design: Multiturn Tasks

The visible surface of this project is small but structurally important. We touch three pages: task creation, `/run`, and the run-detail page. Each has a single-turn branch (unchanged) and a multiturn branch (new).

This document covers visual structure and interaction. Component file layout / split is in `architecture.md`.

## Page Inventory

| Page | Route | Single-turn | Multiturn |
|---|---|---|---|
| Task creation | `/setup/create_task` (and edit) | unchanged | adds `turn_mode` selector + hides schema fields when multiturn |
| Task edit | `/settings/edit_task/.../...` | unchanged | shows `turn_mode` as read-only |
| Run (turn 1 / one-shot) | `/run` | unchanged | turn-1 form only; navigates away on Send |
| Run-detail (turns 2..N for multiturn) | `/dataset/.../.../{run_id}/run` | unchanged | conversation view + composer |

No new routes.

## Task Creation — `turn_mode` Selector

Position: in the task-creation form, near the top (before input/output schema sections — because multiturn changes whether those fields are available).

Control: a two-option toggle / segmented control:

```
Task type:  [ Single-turn ▶ ]  [ Multiturn ]
            Each run is independent.   Conversational; runs continue prior runs.
```

Defaults to `Single-turn`.

Conditional behavior:
- If user picks `Multiturn`:
  - Input schema field: hidden, replaced with a small note: "Multiturn tasks use plain-text input."
  - Output schema field: hidden, replaced with: "Structured output is not supported for multiturn tasks yet."
- If user picks `Single-turn`: schema fields render as today.

Edit page: `turn_mode` shown as a read-only label ("Task type: Multiturn") with a subtle hint that it cannot be changed.

Pushback considered: a checkbox would also work, but a two-option control with descriptions is more discoverable and signals that this is a meaningful task-shape choice, not a flag.

## `/run` — Turn 1 of a Multiturn Conversation

Same layout as today's run page, with two differences for multiturn tasks:

1. The "Run" button is labeled **"Send"** (subtle copy change to set the conversational expectation).
2. The output panel is **not rendered inline.** On a successful response, the page navigates to `/dataset/.../.../{new_run_id}/run`.

Loading state: the existing run-page spinner is fine. No streaming in v1.

Failed-turn: error rendered inline in the existing error area; user remains on `/run` with their input intact.

For single-turn tasks: nothing changes.

## Run-Detail Page — Conversation View (Multiturn Only)

Layout (top to bottom):

```
┌─────────────────────────────────────────────┐
│  AppPage header (existing)                  │
├─────────────────────────────────────────────┤
│  Conversation                               │
│                                             │
│  ┌─ Turn 1 ──────────────────────────────┐  │
│  │  user: ...                            │  │
│  │  assistant: ...                       │  │
│  │  meta: model · latency · [rate]       │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  ┌─ Turn 2 ──────────────────────────────┐  │
│  │  user: ...                            │  │
│  │  assistant: ...                       │  │
│  │  meta: model · latency · [rate]       │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  ...                                        │
├─────────────────────────────────────────────┤
│  Composer (sticky bottom)                   │
│                                             │
│  [ run config picker (collapsible) ]        │
│  ┌───────────────────────────────────────┐  │
│  │ Type your next message...        [→]  │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### Conversation rendering

- Each **turn** (one `TaskRun`) is rendered as a clearly bounded block — a card with a thin border and a small header strip ("Turn N").
- Inside each turn: user message, then assistant message. Roles labeled.
- Both messages rendered with markdown (reuse / lift the existing chat markdown renderer).
- Reasoning / thinking content (if `intermediate_outputs.cot` is present) renders as a collapsible section above the assistant's reply, mirroring the chat page's collapse pattern.
- Tool calls (when added later — out of scope but design must accommodate) would render as additional collapsible blocks within a turn.

The conversation list is rendered from the loaded TaskRun's `trace` field plus walk of the parent chain — but in practice the full trace is already on the leaf, so just iterating the leaf's `trace` and grouping by turn boundary (each user/assistant pair) is enough.

### Per-turn metadata

Per-turn metadata strip (under each assistant response):

- Model (e.g. "GPT-4o · openrouter")
- Latency (e.g. "1.2s")
- Cost (e.g. "$0.0021") — small and de-emphasized
- A rating affordance — same control as today's run-detail page rating, scoped to the turn's TaskRun.

Detailed run info (full token usage, full request settings, raw trace) is reachable per turn via a "View run details" link that opens the turn's TaskRun in its standard run-detail rendering. We do not duplicate the entire current run page inside each turn block — too noisy.

### Composer

- Sticky at the bottom of the page.
- Textarea grows with content (capped to ~6 lines, then scrolls).
- Run-config picker: collapsed by default, shows current model + a small "Change" affordance. Expanded reveals the full RunConfigComponent.
- The picker defaults to **the previous turn's config** for this conversation. Switching it applies only to the next turn the user sends.
- Send button: enabled only when textarea non-empty and not currently sending.
- While sending: button shows a spinner; textarea + run-config picker disabled.
- On success: composer clears, URL replaces to the new run id, conversation re-renders with the new turn appended, page auto-scrolls to the bottom of the conversation.
- On failure: composer keeps the user's text; an inline error appears above the composer with a Retry option.

### Empty / loading / error states

- **Loading the run-detail page itself**: existing skeleton — unchanged.
- **Conversation has 0 turns visible**: not a real state — turn 1 always exists if you're on the page (you got here from `/run` after creating it).
- **Failed to load the TaskRun**: existing error UI — unchanged.

### Scroll behavior

- On initial page load: scroll to the bottom (latest turn is most relevant).
- On Send + success: auto-scroll to the new turn.
- User can scroll up freely to read prior turns; scroll position is preserved if they navigate within the page.

### Single-turn tasks on the run-detail page

Unchanged. No conversation view, no composer.

## Visual Style

Stay aligned with existing Kiln UI conventions:

- Cards for turn blocks: same border / radius as other Kiln cards.
- Composer: matches the chat composer's general look but uses Kiln run-page colors and spacing — this is the run page, not a chat clone.
- Markdown rendering: same renderer as `/chat`, lifted to a shared location if not already.
- Per-turn metadata: small, gray, single-line, in line with how the current run-detail page presents metadata.

Explicit non-goals for visual style:

- Not a free-flowing chat bubble layout. Each turn is a structured, rateable artifact.
- No avatars, no timestamps in chat-app style. Keep it tool-like.
- No animations beyond the existing Kiln spinner pattern.

## Discoverability / Affordances

- The Task type chooser at creation makes the choice explicit upfront. Tooltip / inline help describes the difference in one sentence.
- The run-detail page composer (multiturn only) is the obvious continuation entry point — no extra "Continue conversation" button needed because the composer itself is the affordance.
- Per-turn "View run details" links provide a way to dig into any turn's full TaskRun page without cluttering the conversation view.

## Responsiveness

Existing Kiln UI is desktop-first; we follow that. The composer and turn cards stack naturally on narrower viewports. No mobile-specific layout work in v1.
