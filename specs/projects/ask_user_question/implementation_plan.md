---
status: complete
---

# Implementation Plan: Ask User Question

Branch `leonard/ask-user-question` (off `leonard/kil-692-assistant-auto-mode`); PR targets
`leonard/kil-692-assistant-auto-mode`. Details in functional_spec.md / ui_design.md /
architecture.md.

## Phases

- [x] **Phase 1 — `ask_user_question` tool (libs/core)**
  - `AskUserQuestionTool` mirroring `enable_auto_mode_tool.py`: `KilnBuiltInToolId.ASK_USER_QUESTION`,
    `tool_registry.py` case, `ASK_USER_QUESTION_TOOL_NAME`, schema (`question` required;
    `suggested_answers` array maxItems 5 of `{answer, explanation}`), signal-only `run()`. Tests.
    (Architecture §1.)

- [x] **Phase 2 — App server: interception + answer endpoint**
  - Constants + `ask-user-question` SSE formatter. Intercept `ask_user_question` in
    `ChatStreamSession` (emit + return) and `AutoChatRunner` (emit + go IDLE, pending unresolved).
    `POST /api/chat/ask/answer` resolving the tool call (pick → answer text; chat → chat signal) and
    continuing — auto-resume vs interactive stream by registry lookup; echo the answer to the bus for
    auto. Tests against a fake upstream. (Architecture §2.)

- [ ] **Phase 3 — Web UI**
  - `ask_user_question.svelte` card (options + "Chat about this"); handle the `ask-user-question`
    event in `streaming_chat.ts` (interactive + auto observer); `chat_session_store.answerQuestion`;
    input gating while pending (re-enabled on chat/resolve); render the chosen answer as the user's
    message; resolution/error/detach clears the gate. Regenerate `api_schema.d.ts`. vitest coverage.
    (`ui_design.md`, Architecture §3.)

- [ ] **Phase 4 — Backend wiring (`/Users/leonardmarcq/Downloads/kiln_server`)**
  - Register `ask_user_question` in `CHAT_CLIENT_VISIBLE_TOOLS` + `get_chat_kiln_tool_ids()`; add
    system-prompt guidance (≤5 concrete answers w/ short explanations, call alone, chat-signal →
    open follow-up). Verify. Pre-merge: editable deps → published rev (as for auto-mode tools).
    (Architecture §4.)

- [ ] **Phase 5 — Open PR** into `leonard/kil-692-assistant-auto-mode`.
