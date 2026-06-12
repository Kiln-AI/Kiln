---
status: complete
---

# Phase 4: Backend wiring (kiln_server)

## Overview

Expose the `ask_user_question` built-in tool (added to libs/core in Phase 1) to the chat model from
the Kiln Copilot backend repo (`/Users/leonardmarcq/dev/kiln_ws_1/kiln_server`, branch
`leonard/ask-user-question`). This mirrors exactly how `enable_auto_mode` / `disable_auto_mode` were
wired: register the tool as client-visible (so the app server returns control + persists a snapshot
when the model calls it, then intercepts it and never executes it server-side) and give the model
system-prompt guidance on when and how to use it. No app-server interception logic changes here —
that already exists (Phase 2); Phase 4 is purely the backend exposure + prompt guidance.

## Steps

1. **`pyproject.toml`** (pre-existing uncommitted change, kept in place): `kiln-ai` / `kiln-server`
   editable deps repointed from a dead absolute `~/Downloads` path to relative `../Kiln/libs/{core,
   server}` (repos were relocated to `~/dev/kiln_ws_1/`). Required for the branch to build. Left as-is
   and included in the commit. `.vscode/settings.json` left unstaged/uncommitted.

2. **`uv sync`** to install the editable libs/core carrying the new tool; verify import of
   `AskUserQuestionTool` / `ASK_USER_QUESTION_TOOL_NAME`.

3. **`api/kiln_fastapi_api/chat/config.py`**:
   - Add `"ask_user_question"` to `CHAT_CLIENT_VISIBLE_TOOLS` (and update the explanatory comment).
   - Add `"kiln_tool::ask_user_question"` to the tuple returned by `get_chat_kiln_tool_ids()`.
   - Do NOT add it to `CHAT_SERVER_SIDE_TOOLS`.

4. **`static/kiln_projects/copilot_chat/tasks/291531180356 - kiln-chat/task.kiln`** (the JSON
   `instruction` field, found via `CHAT_KILN_TASK_PATH`): add an `## Ask the User a Question
   (ask_user_question)` section after the auto-mode guidance, consistent with the existing auto-mode
   tool-guidance style. Covers: use it when you need a decision/clarification and can offer concrete
   options; provide UP TO 5 suggested answers (short main `answer` line + 1–2 line `explanation`);
   call it ALONE (no other tool calls that turn); the user either picks one (you receive that answer
   text as the tool result) OR chooses to chat (you receive `{"choice":"chat"}` — then ask an OPEN
   follow-up question to refine). Re-validate JSON. Inline e.g. quotes use the file's existing
   `\"..\"` escaping style; the `{"choice":"chat"}` signal is real JSON (single-escaped) so the model
   receives exact JSON.

5. **`api/kiln_fastapi_api/chat/test_config.py`**: add
   `test_ask_user_question_registered_as_client_visible_tool` mirroring the enable/disable tests
   (client-visible, not server-side, in `get_chat_kiln_tool_ids()`); update the two exact-tuple
   assertions in `test_get_chat_kiln_tool_ids_uses_default_skill_id` and
   `test_get_chat_kiln_tool_ids_respects_chat_skill_id_setting` to include the new entry.

## Tests

- `test_ask_user_question_registered_as_client_visible_tool` — asserts `ask_user_question` is in
  `CHAT_CLIENT_VISIBLE_TOOLS`, NOT in `CHAT_SERVER_SIDE_TOOLS`, and
  `kiln_tool::ask_user_question` is in `get_chat_kiln_tool_ids()`.
- `test_get_chat_kiln_tool_ids_uses_default_skill_id` (updated) — exact tuple now includes
  `kiln_tool::ask_user_question`.
- `test_get_chat_kiln_tool_ids_respects_chat_skill_id_setting` (updated) — exact tuple now includes
  `kiln_tool::ask_user_question`.

## Verification

- `uv sync` clean; tool import succeeds.
- `from kiln_fastapi_api.chat.config import get_tools, get_chat_kiln_tool_ids` →
  `'ask_user_question' in get_tools().client_tools` is `True`; tuple includes
  `kiln_tool::ask_user_question`.
- `uv run pytest api/kiln_fastapi_api/chat/test_config.py` → all pass.
- `uv run ./checks.sh --agent-mode` → exit 0.
