---
status: complete
---

# Phase 3: Web UI for ask_user_question

## Overview

The browser-side of `ask_user_question`. Phase 2 already emits the
`ask-user-question` SSE event on both the interactive `/api/chat` stream and the
per-run auto observer stream, and exposes `POST /api/chat/ask/answer`. Phase 3
renders the question card inline in the transcript, gates the message input while
a question is pending, and resolves the pending tool call by POSTing the user's
choice — picking a suggested answer (one click) or "Chat about this". Works in
interactive chat and auto-mode, and survives reattach (history restore /
hard-refresh). Frontend only (`app/web_ui`).

## Steps

1. `streaming_chat.ts`
   - New part type `{type:"ask-user-question", toolCallId, question,
     suggestedAnswers, resolution?}` + `SuggestedAnswer` /
     `AskUserQuestionResolution` types. `toBackendMessage` skips ask parts (the
     card never round-trips; continuation keys off `trace_id`).
   - `AskUserQuestionPayload` + `askUserQuestionPayloadFromEvent` (defensive:
     drops malformed suggestions, caps to 5).
   - `StreamEventProcessor`: handle `ask-user-question` → append/refresh the card
     part (`ask` slot kind) + fire `onAskUserQuestion`.
   - Interactive `streamChat`: on `ask-user-question`, let the processor render
     the card, then `onFinish()`+return (ends the stream like
     `auto-mode-consent-required`). Add `onAskUserQuestion` to options.

2. `auto_run_store.ts` — add `onAskUserQuestion` to `AutoRunChatSink`; forward it
   from `buildProcessor()` so the observer path surfaces the card.

3. `chat_session_store.ts`
   - State `askPending: {toolCallId, traceId} | null` (gates input).
   - `recordPendingQuestion` (gate on) wired into the interactive `streamChat`
     and the auto sink. `resolveQuestionPart` collapses the card.
   - `answerQuestion(toolCallId, {answer}|{chat})` → collapse card + clear gate +
     `POST /api/chat/ask/answer`. Auto-on → 202, observer continues (no local
     user message; the bus echoes a pick). Interactive → render a pick as the
     user's message, consume the continuation stream into a fresh assistant turn;
     chat → no user message, input re-enabled. Clears gate on success/error.
   - `reset` clears the gate; `loadSession` recomputes it from an unresolved card
     in the restored messages (reattach).

4. `session_messages.ts` — hydrate an `ask_user_question` tool call as an
   `ask-user-question` card; a tool result collapses it (`{"choice":"chat"}` →
   chat, else picked answer).

5. `ask_user_question.svelte` (new) — the card: question, full-width option
   buttons (main line + muted explanation), a divider, an always-present "Chat
   about this" ghost button + hint, and a collapsed resolved summary. Real
   buttons, aria labels, focus-visible outline; state by text + layout.

6. `chat.svelte` — render the card part (simplified + detailed views);
   `inputDisabled` includes `askPending`; pending placeholder hint; pick/chat
   handlers call `store.answerQuestion`.

## Tests

- `ask_user_question.test.ts`: renders question/options/explanations + "Chat
  about this"; pick → `onPick(answer)`; chat → `onChat`; empty suggestions; both
  resolved summaries; disabled state.
- `streaming_chat.test.ts`: `askUserQuestionPayloadFromEvent` parse/cap;
  interactive `ask-user-question` renders the card, fires `onAskUserQuestion`,
  ends the stream.
- `chat_session_store.test.ts`: records pending + gates input; interactive pick
  POSTs + renders user message + collapses card + clears gate; "Chat about this"
  POSTs chat signal + no user message + clears gate; auto path renders card on
  observer + answers via 202 with no local user message; error clears gate;
  reset clears gate; loadSession re-gates on an unresolved restored card (and not
  on a resolved one).
- `session_messages.test.ts`: hydrate pending card; collapse to pick; collapse to
  chat.
