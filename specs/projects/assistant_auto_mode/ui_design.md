---
status: complete
---

# UI Design: Assistant Auto-Mode

All UI lives in the existing assistant chat page
(`app/web_ui/src/routes/(app)/assistant/`). No new pages or routes. We add: a consent dialog, a
footer auto-mode control + indicator, a Stop affordance, and a "working" treatment in the Chat
History dialog. Everything follows existing DaisyUI/Tailwind patterns already in `chat.svelte`,
`tool_approval_box.svelte`, and `chat_history.svelte`.

## UX Principles

- **Consent is the gate, and it must be impossible to miss.** A blocking modal, not a toast.
- **The "on" state must be unmistakable and always visible** while a run is active — green
  indicator under the input, persisting across reloads/re-attach.
- **Stopping must be one click, always reachable** whenever a run is active.
- **Low noise when off.** The enable affordance is a quiet ghost control; it does not compete with
  the Send button or the cost disclaimer.
- **Reuse existing patterns.** `Dialog` for the modal (as Chat History uses), the same
  Run/Skip-style button hierarchy, the same row layout in history.

## 1. Footer control + indicator (under the message input)

The input `<form>` (chat.svelte ~L1036–1070) gets a **footer row** rendered directly beneath it
(above/replacing the current standalone `ChatCostDisclaimer` placement; the disclaimer stays, the
auto-mode row sits in the same footer zone). Two mutually-exclusive states:

**Off (default):** a quiet ghost affordance on the left of the footer row.

```
┌─────────────────────────────────────────────────────────┐
│  Type a message…                                      (↑) │
│                                                           │
└─────────────────────────────────────────────────────────┘
  ⏵⏵ Auto mode        ·  uses tokens, can run costly jobs
  (muted ghost button)    (cost disclaimer, existing)
```

- Label: `⏵⏵ Auto mode`, muted (`text-base-content/50`), `btn btn-ghost btn-xs`. Hover shows a
  tooltip: "Let the assistant run steps automatically without asking for approval."
- Clicking it opens the **consent dialog** (§3). It does not toggle directly — consent is required
  every time (functional spec §4.2).

**On (run active):** the ghost control is replaced by the green indicator + Stop.

```
┌─────────────────────────────────────────────────────────┐
│  Type a message…                                      (■) │   ← Stop also available in-field while streaming
│                                                           │
└─────────────────────────────────────────────────────────┘
  ⏵⏵ auto mode on   ▸ Stop
  (green, pulsing)    (ghost/error-tinted link)
```

- `⏵⏵ auto mode on` in green (`text-success`), the `⏵⏵` glyph gently pulsing (reuse
  `braille_spinner.svelte` styling or a CSS pulse). Matches the wording in the project overview.
- `Stop` — `btn btn-ghost btn-xs` with subtle error tint; calls `POST /api/chat/auto/{run}/stop`.
- The indicator is driven by the connected SSE state (`auto-mode-on` / `auto-mode-off` events),
  so it is correct on first paint after re-attach, not just after a local toggle.

The existing in-textarea Stop button (StopIcon, shown during `isLoading`) is unchanged; it stops
the *current visible stream*. The footer **Stop** stops the *auto run* (the server-owned loop).
While auto-mode is on, both are present and both ultimately end the run; copy/tooltips clarify
"Stop" (footer) = "Stop auto mode".

## 2. Disabled input while a run drives the conversation?

No. The textarea stays usable: the user may still type. But sending a message while a run is
active is **not** a normal flow (the assistant is mid-burst). Decision: while auto-mode is on,
keep the input enabled but treat a user send as an implicit interrupt — it stops the run and sends
the message interactively. (Simpler than locking; matches "user can always take back control".)
Confirm during implementation; default to interrupt-on-send.

## 3. Consent dialog

A blocking `Dialog` (same component as Chat History). Title: **"Turn on auto mode?"**

Body copy (final):

> Auto mode lets the assistant **run steps on its own** to make progress without stopping to ask
> you each time.
>
> While it's on:
> - It will **run tool calls and Kiln API actions without asking for approval** — including
>   actions you'd normally confirm.
> - It may **start costly jobs** (for example, reflective optimization runs) that **use tokens and
>   can incur real cost**.
> - It **keeps working on the server even if you close this window**, until it finishes, needs your
>   input, or you stop it.
>
> Auto mode turns off automatically when the assistant has a question for you or is done. You can
> stop it anytime.

- When triggered by the **backend tool**, and the model supplied a `reason`, show it above the
  bullets in a quoted callout: *"The assistant suggests auto mode to: {reason}."*
- Buttons: **Cancel** (`btn btn-ghost`) and **Turn on auto mode** (`btn btn-primary`).
- **Cancel / dismiss** → decline path (functional spec §4.2): backend-tool path calls
  `POST /api/chat/auto/decline`; toggle path just closes.
- **Turn on** → `POST /api/chat/auto/enable`; dialog closes; footer switches to the green "on"
  state.
- The dialog is keyboard-accessible; Escape = Cancel/decline.

## 4. Chat History "working" treatment

`chat_history.svelte` rows (currently: title + date + hover action menu) gain an **active
indicator** when the enriched `GET /api/chat/sessions` marks a row `auto_active` (functional spec
§6.3 — the flag is computed server-side; the UI just renders it).

- **Green dot** before the title: a small `size-2 rounded-full bg-success` with a soft pulse, and
  an `aria-label="Auto mode running"`. Tooltip: "Auto mode is running".
- **Grouping (progressive disclosure):** if any rows are active, render an **"Active" section at
  the top** ("Working now") above a divider, then the rest under "Recent" — so the running
  conversation is the first thing the user sees. If none are active, show the flat list as today.
- Date column: for active rows, show "Working…" in `text-success` instead of the timestamp.
- Selecting an active row hydrates from the latest trace (existing `selectSession`) **and**
  re-attaches the live stream (§5). Selecting works exactly as today otherwise.
- The list is refreshed while the dialog is open (light poll or the existing fetch on open) so the
  dot appears/clears without manual reload. Keep it cheap; no need for sub-second accuracy.

## 5. Re-attach experience (opening an active conversation)

When the user opens a conversation that is running auto-mode:

1. The completed history renders immediately via the existing snapshot hydration
   (`hydrateSessionFromSnapshot`).
2. The chat shows the existing in-progress affordances (status steps / `chat_status_steps`,
   spinners, tool execution lines) for the current turn, fed by re-attaching to the runner's live
   observer stream. On attach, the runner replays the current turn's buffered events so there is no
   visible gap (functional spec §4.5.2).
3. The footer shows the green **"⏵⏵ auto mode on"** indicator + **Stop**.
4. If the run finishes between hydrate and attach, the UI simply lands in the normal "off" state
   with the completed conversation — no error.

If re-attach fails (no buffer / runner already gone), fall back to the hydrated history plus a
brief "Catching up…" state, then normal once the next snapshot arrives — never a hard error.

## 6. States summary

| Context | Off | Consent pending | On (active) |
|---|---|---|---|
| Footer | muted `⏵⏵ Auto mode` ghost | dialog open | green `⏵⏵ auto mode on` + Stop |
| Input | normal | normal (dialog blocks) | enabled; send = interrupt |
| History row | title + date | n/a | green dot + "Working…", grouped on top |

## 7. Responsive / platform

- Footer row wraps on narrow widths: indicator on its own line above the cost disclaimer.
- Consent dialog uses the existing responsive `Dialog` sizing.
- All new affordances are keyboard-reachable and have `aria-label`s; the pulsing dot/indicator
  also carries text so it isn't color-only (accessibility: don't rely on green alone — the word
  "on"/"Working…" conveys state too).

## 8. Out of scope (UI)

- No per-tool auto-approve toggles or settings surface (auto-mode is all-or-nothing while on).
- No global "auto runs" dashboard beyond the Chat History treatment.
- No cost/budget meter UI (would accompany a future budget cap, functional spec §9).
