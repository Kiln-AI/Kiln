---
status: complete
---

# Phase 2: App server — interception + answer endpoint

## Overview

The libs/core `ask_user_question` tool (Phase 1) is client-visible: the backend returns control to
the app server when the model calls it. This phase makes the app server intercept that call by name
— never executing it — surface it to the browser as an `ask-user-question` SSE event, pause, and
expose `POST /api/chat/ask/answer` to resolve the pending tool call (with the picked answer text or a
chat signal) and continue. Mirrors the existing `enable_auto_mode` / `disable_auto_mode` interception
+ the auto idle→resume machinery exactly.

## Steps

1. `chat/constants.py`: add `SSE_TYPE_ASK_USER_QUESTION = "ask-user-question"`.

2. `chat/stream_session.py`:
   - Import `ASK_USER_QUESTION_TOOL_NAME` from
     `kiln_ai.tools.built_in_tools.ask_user_question_tool` and `SSE_TYPE_ASK_USER_QUESTION`.
   - Add `MAX_SUGGESTED_ANSWERS = 5` and a module helper
     `_parse_ask_user_question(input: dict) -> tuple[str, list[dict]]` that pulls `question`
     (str, default "") and `suggested_answers` (list of `{answer, explanation}`), defensively
     capping to 5 and coercing item shapes.
   - Add formatter `_format_ask_user_question_sse(trace_id, tool_call_id, question,
     suggested_answers) -> bytes` (SSE type `ask-user-question`, defensively caps to 5).
   - In `ChatStreamSession.stream()` post-round handling, before the approval gate (alongside the
     enable/disable interception): if a client event's `toolName == ASK_USER_QUESTION_TOOL_NAME`,
     emit `_format_ask_user_question_sse(...)` and `return`. Do not execute the tool.

3. `chat/auto/runner.py`:
   - Import `ASK_USER_QUESTION_TOOL_NAME` and the `_format_ask_user_question_sse` /
     `_parse_ask_user_question` helpers.
   - In `AutoChatRunner.run()` client-events handling (after the disable interception, before the
     stop/approval/auto-execute), detect an `ask_user_question` event. Emit the ask SSE onto the bus
     (`self._emit(...)`), set `idle_reason = "asked_user"`, set status `IDLE`, and `return`. The tool
     call is left UNRESOLVED (no continuation sent) — the answer endpoint resolves it.

4. `chat/auto/registry.py`: add `answer_question(run_id, tool_call_id, result_content) -> bool`.
   Mirrors the IDLE→burst path in `send_message`: only valid when the run is IDLE with flag on; build
   an `AutoChatSeed(trace_id=current_trace_id, extra_messages=[{role:"tool", tool_call_id, content}])`,
   transition RUNNING, `start_burst`, supervise. Echo the picked answer onto the bus when an
   `echo_user_content` is provided (pick → echo chosen answer as the user's message; chat → no echo).
   Returns False if the run is unknown / flag off / not idle (active RUNNING burst can't take an
   answer — there's no pending question while a burst drives).

5. `chat/routes.py`: add `POST /api/chat/ask/answer`.
   - Request model `AnswerQuestionRequest { trace_id, tool_call_id, choice: AnswerChoice }` where
     `AnswerChoice { answer: str | None = None, chat: bool | None = None }`.
   - Build `result_content`: pick → `choice.answer`; chat → `json.dumps({"choice":"chat"})`.
     Reject a malformed choice (neither a non-None answer nor `chat=True`) with 422.
   - Route via `auto_chat_registry.run_id_for_trace(trace_id)`:
     - Active auto run → `answer_question(run_id, tool_call_id, result_content,
       echo_user_content=choice.answer if pick else None)`; 404/409 if it returns False; else 202.
     - Interactive → `ChatStreamSession(initial_body={trace_id, messages:[{role:"tool",
       tool_call_id, content}]})` and return `CancellableStreamingResponse(session.stream())`.
   - `tags=["Copilot"]`, `@no_write_lock`, `openapi_extra=DENY_AGENT`.

6. Regenerate `api_schema.d.ts` (new request model). Run `./checks.sh`.

## Tests

App server (pytest, fake upstream + ASGI client), added to `chat/auto/test_api.py` +
`chat/test_stream_session.py`:

- `test_ask_user_question_interactive_emits_event_and_pauses`: interactive `/api/chat` →
  ask-user-question SSE with question + suggested_answers + tool_call_id; tool never executed; single
  upstream round (returns/pauses).
- `test_ask_user_question_caps_suggested_answers_to_5`: model emits 7 → SSE carries exactly 5.
- `test_ask_user_question_auto_settles_idle_with_pending`: auto burst calls ask_user_question →
  status IDLE, ask SSE on bus, tool call unresolved (no resolving continuation POSTed).
- `test_ask_answer_pick_interactive_resolves_and_continues`: pick → continuation body has clean
  `role:"tool"` result with the answer text; stream continues; persisted continuation has no dangling
  tool call.
- `test_ask_answer_chat_interactive_resolves_with_chat_signal`: chat → tool result content is
  `{"choice":"chat"}`; continues.
- `test_ask_answer_pick_auto_resumes_burst`: active auto run → answer resumes the burst with the
  `role:"tool"` continuation; the picked answer is echoed onto the bus.
- `test_ask_answer_chat_auto_resumes_without_user_echo`: chat → resumes; no user-message echo.
- `test_ask_answer_routes_interactive_when_no_active_auto_run`: no active run → interactive stream.
- `test_ask_answer_unknown_or_inactive_auto_run_returns_error`: registry returns False → 404/409.
- `test_ask_answer_malformed_choice_returns_422`: neither answer nor chat → 422.
- `test_ask_answer_no_write_lock`: route is `@no_write_lock`.

Runner unit test in `chat/auto/test_runner.py`:
- `test_ask_user_question_settles_idle_unresolved`: ask SSE emitted, status IDLE, only one upstream
  round (no resolving continuation).

Keep the golden interactive-unchanged test green; don't regress auto-mode behavior.
