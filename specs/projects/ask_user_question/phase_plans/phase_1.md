---
status: complete
---

# Phase 1: `ask_user_question` tool (libs/core)

## Overview

Add the `ask_user_question` built-in tool to `libs/core`, mirroring the existing
`enable_auto_mode` / `disable_auto_mode` signal tools. The tool is client-visible and never
executed in chat: the app server (future phase) intercepts it by name, surfaces the question
to the user, and resolves the call. The `run()` body here is a signal no-op kept only so the
`libs/core` tool surface is complete and the library is usable standalone.

Scope is libs/core ONLY — no app server, no web UI, no kiln_server.

## Steps

1. `libs/core/kiln_ai/datamodel/tool_id.py`: add enum member
   `ASK_USER_QUESTION = "kiln_tool::ask_user_question"` to `KilnBuiltInToolId`.

2. New file `libs/core/kiln_ai/tools/built_in_tools/ask_user_question_tool.py`:
   - Module constant `ASK_USER_QUESTION_TOOL_NAME = "ask_user_question"`.
   - `class AskUserQuestionTool(KilnTool)` constructed with
     `tool_id=KilnBuiltInToolId.ASK_USER_QUESTION`, `name=ASK_USER_QUESTION_TOOL_NAME`,
     model-facing description, and `parameters_schema`.
   - Description: ask the user a question with up to 5 concrete suggested answers, each a short
     main line + 1-2 line explanation; user picks one or chooses to chat to refine. Call alone.
   - `parameters_schema`: object with `question: string` (required) and `suggested_answers`:
     array (`maxItems` 5) of objects `{ answer: string (required), explanation: string }`.
   - `async def run(self, context=None, **kwargs) -> ToolCallResult`: signal no-op returning
     `ToolCallResult(output=json.dumps({"status": "asked"}, ensure_ascii=False))`.

3. `libs/core/kiln_ai/tools/tool_registry.py`: import `AskUserQuestionTool`; add
   `case KilnBuiltInToolId.ASK_USER_QUESTION: return AskUserQuestionTool()`.

4. Do NOT touch app server `FUNCTION_NAME_TO_TOOL_ID` (out of phase scope; intercepted by name).

## Tests

- `test_ask_user_question_tool.py` (mirror `test_enable_auto_mode_tool.py`):
  - metadata: name == `ask_user_question`, constant matches, id == `ASK_USER_QUESTION`,
    description non-empty and mentions question.
  - schema: `type` object; `question` is a required string; `suggested_answers` is an array with
    `maxItems` 5, items object with required `answer` string and `explanation` string.
  - run() returns `{"status": "asked"}` signal; both call conventions (positional
    `ToolCallContext`, no context, ignored kwargs).
- `test_tool_registry.py`: `tool_from_id(KilnBuiltInToolId.ASK_USER_QUESTION)` returns
  `AskUserQuestionTool` with matching id/name.
