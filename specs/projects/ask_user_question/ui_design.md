---
status: complete
---

# UI Design: Ask User Question

All in the existing assistant chat page. Reuses existing patterns (`tool_approval_box.svelte`,
`auto_mode_consent_dialog.svelte`, the chat message/part rendering, DaisyUI). No new routes.

## 1. Question card (in the transcript)

Rendered inline where the assistant's turn produced the question (like a tool/approval block), in a
new `ask_user_question.svelte` component:

```
┌────────────────────────────────────────────────────────┐
│  <question text>                                          │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ <answer main line>                                 │  │  ← selectable option (button/card)
│  │ <1–2 line explanation, muted>                      │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ <answer 2> …                                       │  │
│  └──────────────────────────────────────────────────┘  │
│  … up to 5 …                                             │
│                                                          │
│  ▸ Chat about this        (always present, distinct)     │
└────────────────────────────────────────────────────────┘
```

- **Options**: each a full-width clickable card — main line in normal weight, explanation in
  `text-base-content/70` below it. Hover/focus highlight; keyboard accessible (Enter/Space). **One
  click sends** that answer.
- **"Chat about this"**: always shown, visually distinct from the suggested answers (e.g. a ghost
  button below a thin divider), with a hint like "Refine this by chatting instead."
- After resolution the card collapses to a compact, non-interactive summary showing what was chosen
  (e.g. "You chose: <answer>" or "You chose to chat about this"), consistent with how resolved
  tool/approval blocks render.

## 2. Input state

- While a question is **pending**, the message textarea + Send are **disabled**, with a subtle
  placeholder/hint ("Choose an option above, or 'Chat about this' to type a reply").
- Choosing **"Chat about this"** resolves the question and **enables** the input; the assistant then
  asks an open follow-up and the user types normally.
- Picking a suggested answer also resolves it; input returns to normal for subsequent turns.

## 3. States

| State | Question card | Input |
|---|---|---|
| Pending | interactive options + "Chat about this" | disabled (hint) |
| Resolved (picked) | collapsed: "You chose: <answer>" | normal |
| Resolved (chat) | collapsed: "You chose to chat about this" | enabled (open follow-up incoming) |

## 4. Auto-mode interaction

- When a question is pending in auto-mode, the auto indicator shows its **idle** sub-state ("⏵⏵ auto
  mode on · waiting for you") alongside the question card. Answering resumes the burst (thinking
  indicator returns). No separate visual mode — the question card is the same in interactive and
  auto.

## 5. Reattach

- On reattach (history restore / hard refresh) with a pending question, the card re-renders from the
  current-turn buffer (auto) or the persisted snapshot's pending tool call (interactive), and the
  input stays disabled until answered — consistent with the live state.

## 6. Accessibility / polish

- Options are real buttons with `aria` labels; the whole card is keyboard-navigable. State is
  conveyed by text + layout (not color alone). Matches existing assistant styling/spacing.

## 7. Out of scope (UI)

- No drag/reorder, no multi-select, no inline editing of an option before sending.
