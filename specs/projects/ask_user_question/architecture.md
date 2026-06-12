---
status: complete
---

# Architecture: Ask User Question

Reuses the auto-mode interception/SSE/answer machinery end to end. Spans libs/core, app server,
web UI, and the backend — exactly the layering used for `enable_auto_mode`.

## 1. Tool (libs/core)

- `libs/core/kiln_ai/tools/built_in_tools/ask_user_question_tool.py`: `AskUserQuestionTool`
  mirroring `enable_auto_mode_tool.py`. Name `ask_user_question`; export
  `ASK_USER_QUESTION_TOOL_NAME`. `KilnBuiltInToolId.ASK_USER_QUESTION` + `tool_registry.py` case.
- `parameters_schema`: object with `question: string` (required) and `suggested_answers`: array
  (maxItems 5) of `{ answer: string (required), explanation: string }`.
- `run()` signal no-op (intercepted; never executed) returning e.g. `{"status":"asked"}` with
  `ensure_ascii=False`. **Not** added to the app server `FUNCTION_NAME_TO_TOOL_ID`.

## 2. App server — interception + answer

### 2.1 Constants / parsing
- New constant `ASK_USER_QUESTION_TOOL_NAME` imported from libs/core; new SSE type
  `SSE_TYPE_ASK_USER_QUESTION = "ask-user-question"` in `chat/constants.py`; a formatter
  `_format_ask_user_question_sse(tool_call_id, question, suggested_answers)` (defensively caps
  `suggested_answers` to 5).

### 2.2 Interception (mirrors `enable_auto_mode`/disable interception)
- **`ChatStreamSession`** (interactive): in the post-round handling, before the approval gate, if a
  tool input event's name is `ask_user_question`, emit the `ask-user-question` SSE (parsing
  `question`/`suggested_answers` from the tool input) and `return` (pause). Do not execute the tool.
- **`AutoChatRunner`** (auto): same detection; emit the `ask-user-question` event onto the run's bus,
  then settle the burst to **IDLE** (flag stays on) with the pending question — reuse the existing
  "assistant asks → idle" path (the question is just a richer form of asking). The pending
  `ask_user_question` tool call is left unresolved until the user answers.

### 2.3 Answer endpoint
`POST /api/chat/ask/answer` — body `{ trace_id, tool_call_id, choice }`, `choice` =
`{ answer: string }` | `{ chat: true }`.
- Build the tool result for `tool_call_id`: content = the answer text for a pick, or a chat signal
  `{"choice":"chat"}` for "Chat about this".
- Route by conversation state (registry lookup `run_id_for_trace(trace_id)`):
  - **Active auto run** → resolve into that run and **resume the burst** (a new registry method,
    e.g. `answer_question(run_id, tool_call_id, result)`, analogous to the idle→burst path in
    `send_message`, but the seed/continuation carries the `role:"tool"` result instead of a
    `role:"user"` message). The answer is also **echoed to the bus** so observers render the user's
    choice.
  - **Interactive** → build a continuation body `{trace_id, messages:[{role:"tool", tool_call_id,
    content}]}` and return `CancellableStreamingResponse(ChatStreamSession(...).stream())`.
- Resolving via a `role:"tool"` message keeps the persisted trace clean (no dangling tool call),
  exactly like enable/disable resolution.

### 2.4 Continuation body builder
Reuse `_build_openai_tool_continuation` / the seed-body path; the only new shape is a single
`role:"tool"` result for the `ask_user_question` call (plus, for auto resume, feeding it as the
runner's next continuation).

## 3. Web UI

- `streaming_chat.ts`: handle the `ask-user-question` SSE event (in both the interactive `streamChat`
  reader and the auto observer path via `StreamEventProcessor`), producing a chat part/state that
  renders the question card. Add an `askPendingQuestion` store/flag for input gating.
- `ask_user_question.svelte` (new): the question card (options + "Chat about this"), per ui_design.
- `chat_session_store.ts`:
  - On `ask-user-question` → record the pending question, **disable input**.
  - `answerQuestion(toolCallId, {answer}|{chat})` → `POST /api/chat/ask/answer`. On a pick: render
    the chosen answer as the user's message; consume the returned interactive stream OR (auto) let
    the observer stream continue. On chat: re-enable input (the open follow-up arrives on the
    stream).
  - Clear the pending/input-block on resolution, error, or detach (can't get stuck).
- `chat.svelte`: input `disabled` includes `askPending`; render the card inline; auto-mode indicator
  unaffected (idle sub-state shows naturally).

## 4. Backend (kiln_server)

- Add `"ask_user_question"` to `CHAT_CLIENT_VISIBLE_TOOLS` + `kiln_tool::ask_user_question` to
  `get_chat_kiln_tool_ids()` (mirror enable/disable).
- System-prompt guidance in `task.kiln`: when to use it, ≤5 concrete answers each with a 1–2 line
  explanation, call it **alone**, result is the chosen answer text OR a `{"choice":"chat"}` signal
  → then ask an **open follow-up question** to refine.
- (Editable deps already point at local libs/core, so the new tool is importable; pre-merge repoint
  applies as for the auto-mode tools.)

## 5. Error handling / edge cases

- Defensive cap of `suggested_answers` to 5 at emit time.
- Empty `suggested_answers` → card shows question + "Chat about this" only.
- Answer for an unknown/expired tool_call_id → 4xx surfaced inline; pending stays until resolved.
- Reattach: interactive re-renders from the persisted snapshot's pending tool call; auto replays the
  `ask-user-question` event from the current-turn buffer (it was emitted after the last
  `kiln_chat_trace`). Input stays gated until answered.
- Disconnect does not resolve the question (pure-observer); it remains pending server-side.

## 6. Testing

- libs/core: tool metadata/schema (maxItems 5, required question) + registry case.
- App server (pytest, fake upstream): interception emits `ask-user-question` and pauses
  (interactive returns; auto → IDLE with pending); `/ask/answer` pick → clean tool result + continue
  (interactive stream and auto resume); chat → chat-signal result + continue; routing by
  active-auto-run vs interactive; defensive 5-cap; unknown tool_call_id → error; reattach replay.
- Web UI (vitest): `ask-user-question` renders the card; input gated while pending; one-click pick
  POSTs answer + renders the user message; "Chat about this" enables input; resolution/error/detach
  clears the gate; auto path renders the card on the observer stream.

## 7. One-phase decision

Single architecture doc; cohesive with existing auto-mode components.
