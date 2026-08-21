---
status: complete
---

# Phase 8: Backend wiring for `disable_auto_mode`

## Overview

Phase 6 added the `disable_auto_mode` built-in tool to libs/core (signal-only, intercepted by the
app server, never executed). Phase 8 exposes that tool to the chat model from the external Kiln
Copilot backend (`/Users/leonardmarcq/Downloads/kiln_server`), exactly mirroring how
`enable_auto_mode` was wired in Phase 5. This is pure backend wiring — no app-server or libs/core
changes. The interception logic already lives in the app server (Phase 6); the model just needs the
tool registered and prompt guidance telling it when to call it.

## Steps

1. **Restore local editable libs/core / libs/server (precondition).** The backend's
   `pyproject.toml` `[tool.uv.sources]` had been repointed from local editable paths back to a
   pinned git rev (`140c9bc…`, predates Phase 6) by a later `chore: update kiln lib` commit, so
   `disable_auto_mode_tool` was not importable. Repoint to the local editable paths (matching the
   documented Phase 5 state and the Phase 8 precondition that the tool is importable) and `uv sync`:
   ```toml
   kiln-ai = { path = "/Users/leonardmarcq/Downloads/Kiln/libs/core", editable = true }
   kiln-server = { path = "/Users/leonardmarcq/Downloads/Kiln/libs/server", editable = true }
   ```
   (Before merge, deps get repointed back to a published Kiln git rev that includes the tool — same
   as Phase 5's pre-merge note.)

2. **`api/kiln_fastapi_api/chat/config.py` — `get_chat_kiln_tool_ids()`.** Add
   `"kiln_tool::disable_auto_mode"` after the existing `"kiln_tool::enable_auto_mode"` entry.

3. **`api/kiln_fastapi_api/chat/config.py` — `CHAT_CLIENT_VISIBLE_TOOLS`.** Add `"disable_auto_mode"`
   to the frozenset (alongside `"call_kiln_api"`, `"enable_auto_mode"`). Do NOT add it to
   `CHAT_SERVER_SIDE_TOOLS` — the app server intercepts it and never executes it server-side. Update
   the explanatory comment to cover both auto-mode tools.

4. **Chat `task.kiln` instruction (system prompt).** In the file under
   `static/kiln_projects/copilot_chat/tasks/291531180356 - kiln-chat/task.kiln` (the JSON
   `instruction` field, same one Phase 5 edited for `enable_auto_mode`), extend the Auto-Mode
   guidance with a "Turning Auto-Mode off (`disable_auto_mode`)" subsection: when the user asks to
   stop auto-mode (e.g. "stop auto mode", "stop doing this automatically", "ask me before each step
   again"), call `disable_auto_mode` (ALONE) to turn it off, then continue interactively (normal
   step-by-step approval applies again). No consent needed for turning off; tool result is
   `{"status": "disabled"}`. Keep the style consistent with the existing `enable_auto_mode`
   guidance; keep the JSON valid.

5. **Tests — `api/kiln_fastapi_api/chat/test_config.py`.** Add `"kiln_tool::disable_auto_mode"` to
   the two `get_chat_kiln_tool_ids()` tuple assertions (default + custom skill id). Add a
   `test_disable_auto_mode_registered_as_client_visible_tool` mirroring the existing
   `enable_auto_mode` registration test (client-visible, not server-side, in the tool ids).

## Tests

- `test_get_chat_kiln_tool_ids_uses_default_skill_id` — updated tuple now includes
  `kiln_tool::disable_auto_mode`.
- `test_get_chat_kiln_tool_ids_respects_chat_skill_id_setting` — updated tuple now includes
  `kiln_tool::disable_auto_mode`.
- `test_disable_auto_mode_registered_as_client_visible_tool` (new) — asserts `disable_auto_mode` is
  in `CHAT_CLIENT_VISIBLE_TOOLS`, not in `CHAT_SERVER_SIDE_TOOLS`, and `kiln_tool::disable_auto_mode`
  is in `get_chat_kiln_tool_ids()`.

## Verification

- `uv run python -c "from kiln_ai.tools.built_in_tools.disable_auto_mode_tool import DisableAutoModeTool, DISABLE_AUTO_MODE_TOOL_NAME; print(DISABLE_AUTO_MODE_TOOL_NAME)"` → `disable_auto_mode`.
- `uv run python -c "from kiln_fastapi_api.chat.config import get_tools, get_chat_kiln_tool_ids; print('disable_auto_mode' in get_tools().client_tools); print(get_chat_kiln_tool_ids())"`
  → `True` and the 4-tuple including `kiln_tool::disable_auto_mode`.
- `task.kiln` re-validated as JSON (`json.load`), guidance present.
- `./checks.sh --agent-mode` → exit 0.
