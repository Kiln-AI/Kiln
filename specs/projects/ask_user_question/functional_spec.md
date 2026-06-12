---
status: complete
---

# Functional Spec: Ask User Question

## 1. Summary

The assistant can call a new tool, **`ask_user_question`**, to ask the user a question with a small
set of concrete suggested answers. The app server intercepts the tool call and surfaces it to the
browser as a structured prompt; the user picks one suggested answer (one click) or chooses **"Chat
about this"** to refine via free chat. The user's choice resolves the tool call and the conversation
continues. Works in both normal (interactive) chat and auto-mode.

Reuses the auto-mode interception/SSE/answer pattern (client-visible tool → intercept → SSE event →
browser UI → answer endpoint resolves the tool result → continue).

## 2. The `ask_user_question` tool

- A new **libs/core** built-in tool, registered as a **client-visible** tool in the backend (like
  `enable_auto_mode`/`call_kiln_api`), so the backend returns control + persists a snapshot when the
  model calls it. The app server **intercepts it by name and never executes it**.
- **Schema:**
  - `question: string` (required) — the question to ask.
  - `suggested_answers: [{ answer: string, explanation: string }]` — **0 to 5** items. `answer` is
    the main line; `explanation` is a 1–2 line rationale. (Empty/omitted ⇒ just a question + "Chat
    about this".)
- **"Chat about this" is added by the client**, always — it is NOT one of the model's
  `suggested_answers`.
- `run()` is a signal no-op (intercepted; never executed) — exists only for libs/core completeness.

## 3. Behavior

### 3.1 Asking

When the model calls `ask_user_question`, the app server intercepts it and emits an
`ask-user-question` SSE event with `{ tool_call_id, question, suggested_answers }`, then **pauses**:

- **Interactive chat:** the `/api/chat` stream returns (same pattern as `tool-calls-pending` /
  `auto-mode-consent-required`); the browser shows the question.
- **Auto-mode:** the burst **goes idle** (auto-mode flag stays on, per auto-mode R1 §4.3.1) with the
  question surfaced; the run waits for the answer. (A question inherently needs the user.)

While a question is pending, the browser **blocks the text input** — the user must choose.

### 3.2 Answering

The user resolves the pending question one of two ways. Either resolves the `ask_user_question`
tool call (no dangling tool call in the trace) and continues:

1. **Pick a suggested answer (one click).** The chosen answer's **main line** is sent as the user's
   response: the tool call is resolved with that text, and it is rendered in the transcript as the
   user's message. The conversation continues (in auto-mode if it was, per §3.3).
2. **"Chat about this".** The tool call is resolved with a **"chat" signal**; the model then asks an
   **open follow-up question** (prompt-guided), and the text input is **enabled** so the user can
   free-type. (Auto-mode, if on, stays on.)

### 3.3 Auto-mode composition

- Asking in auto-mode → burst idle, flag stays on (the question is the assistant "asking the user"
  under auto-mode R1). The indicator stays on ("· waiting for you").
- Answering (pick or chat) → resumes the burst in auto-mode (resolve the tool result + continue),
  mirroring how `/api/chat/auto/{run}/message` resumes an idle run — but the answer is a **tool
  result** resolving the pending `ask_user_question` call, not a fresh user message.

### 3.4 Edge cases

- **Multiple questions / re-ask:** only one `ask_user_question` is expected per turn (prompt-guided
  to call it alone). If answered then re-asked later, the same flow repeats.
- **Disconnect / reattach while a question is pending:** the pending question is part of the current
  turn; on reattach it is replayed from the current-turn buffer (auto) or re-rendered from the
  persisted snapshot's pending tool call (interactive), so the user still sees it. (Detail in
  architecture.)
- **Empty `suggested_answers`:** render just the question + "Chat about this".
- **>5 suggested answers** from the model: the app server/UI caps/ignores beyond 5 (prompt says max
  5; defensive cap).
- **User picks while offline / stale:** standard error surfaced inline; the question remains until
  resolved.

## 4. API & contracts (app server)

- **SSE event** `ask-user-question` — `{ type, trace_id, tool_call_id, question, suggested_answers:
  [{answer, explanation}] }`. Emitted on the `/api/chat` stream (interactive) and on the per-run
  auto observer stream (auto).
- **`POST /api/chat/ask/answer`** — body `{ trace_id, tool_call_id, choice }` where `choice` is
  either `{ answer: string }` (a picked/edited suggested answer) or `{ chat: true }`. The endpoint
  resolves the `ask_user_question` tool call (tool result = the answer text, or a chat signal) and
  continues: if the conversation has an active auto run (registry lookup by trace), it resumes that
  run; otherwise it returns a `CancellableStreamingResponse` continuing the interactive stream.
- Reuses existing session/trace/continuation contracts.

## 5. Backend (kiln_server)

- Register `ask_user_question` in `CHAT_CLIENT_VISIBLE_TOOLS` + `get_chat_kiln_tool_ids()` (mirror
  `enable_auto_mode`).
- System-prompt guidance: when to use it (you need a decision/clarification and can offer concrete
  options), provide **up to 5** concrete answers each with a short (1–2 line) explanation, call it
  **alone**, and that the user may pick one (you'll receive that answer) or choose to chat — in
  which case you'll receive a chat signal and should **ask an open follow-up question** to refine.

## 6. UI (functional level; details in ui_design.md)

- A **question card** in the transcript: the question, up to 5 selectable **answer options** (main
  line + explanation), and an always-present **"Chat about this"** action.
- Text input **disabled** while pending; enabled after "Chat about this" (or after any answer).
- One-click selection sends the answer; the chosen answer appears as the user's message.

## 7. Out of scope

- Multi-select answers (single choice only, plus chat).
- Editing a suggested answer before sending (one-click send; "Chat about this" covers free-form).
- Persisting question UI state beyond the normal trace/buffer (reattach re-renders from those).
