---
status: complete
---

# Phase 5: External backend wiring (kiln_server)

## Overview

This phase wires the external Kiln Copilot backend (`/Users/leonardmarcq/Downloads/kiln_server`,
package `kiln-service`) to support auto-mode. The `enable_auto_mode` built-in tool already exists in
this repo's `libs/core` (Phase 1). Here we make the backend (a) depend on the local `libs/core` /
`libs/server` so it picks up the new tool, (b) expose `enable_auto_mode` to the chat model as a
client-visible tool so the backend returns control (and persists a snapshot) when the model calls
it, and (c) add system-prompt guidance for when/how the assistant should suggest auto-mode.

All changes are in the **separate** `kiln_server` repo on a new branch
`leonard/kil-692-assistant-auto-mode` (off `main`). No changes to the main Kiln repo (other than
this phase plan). Architecture §7, §11; functional spec §5; implementation plan Phase 5.

## Steps

1. **Branch.** In `kiln_server`, confirm clean, create + switch to
   `leonard/kil-692-assistant-auto-mode` off `main`. (Done — repo was clean.)

2. **Repoint deps to local editable paths** in `kiln_server/pyproject.toml` `[tool.uv.sources]`:
   - `kiln-ai = { path = "/Users/leonardmarcq/Downloads/Kiln/libs/core", editable = true }`
   - `kiln-server = { path = "/Users/leonardmarcq/Downloads/Kiln/libs/server", editable = true }`
   (Replaces the existing pinned `git`/`rev`/`subdirectory` sources for these two; leave the
   workspace deps untouched.) Then `uv sync` and confirm
   `kiln_ai.tools.built_in_tools.enable_auto_mode_tool.{EnableAutoModeTool, ENABLE_AUTO_MODE_TOOL_NAME}`
   imports in the synced env.

3. **Register the tool as client-visible** in `api/kiln_fastapi_api/chat/config.py` (mirror
   `call_kiln_api`):
   - Add `"enable_auto_mode"` to `CHAT_CLIENT_VISIBLE_TOOLS`.
   - Add `"kiln_tool::enable_auto_mode"` to the tuple returned by `get_chat_kiln_tool_ids()` so the
     model receives its schema.
   - Do NOT add it to `CHAT_SERVER_SIDE_TOOLS`; do NOT execute it server-side (the app server
     intercepts it).

4. **System-prompt guidance** in the chat task instructions (`task.kiln`, JSON `instruction` field,
   resolved via `get_chat_kiln_task_path()` → `static/.../copilot_chat/tasks/291531180356 -
   kiln-chat/task.kiln`). Add a concise section, consistent with the existing instruction style:
   the assistant may call `enable_auto_mode` to suggest running a signed-off, multi-step,
   tool/job-driven plan autonomously; it must call `enable_auto_mode` ALONE (no other tool calls
   that turn); the user may decline (`{"status":"declined"}` → continue interactively) or accept
   (`{"status":"enabled"}` → carry on doing the work without pausing for approval).

5. **Update existing tests** that assert the exact `get_chat_kiln_tool_ids()` tuple
   (`api/kiln_fastapi_api/chat/test_config.py`) to include the new tool id, and add an assertion
   that `enable_auto_mode` is in `CHAT_CLIENT_VISIBLE_TOOLS` and not in `CHAT_SERVER_SIDE_TOOLS`.

6. **Verify.** Run the backend's `checks.sh` (ruff check/format, ty, task-models codegen check,
   pytest) — at minimum `uv run pytest` on the chat module — and confirm config imports cleanly.

7. **Jobs API docs for the chat skill (added per user request).** The assistant didn't know how to
   drive the background-jobs API (`/api/jobs/...`), so it couldn't kick off or wait on jobs in
   auto-mode. Added api_docs to the chat skill's knowledge base (kiln_server,
   `static/.../copilot_chat/skills/408910145779 - kiln-chat/references/knowledge/api_docs/`):
   - **One overview catalog** `jobs_api_list.md` documenting the job lifecycle (pending/running/
     paused → succeeded/failed/cancelled), the registered job types and their create-time `params`
     (`eval`, `rag`, `finetune`, `noop`), and — emphasized for auto-mode — the **create→wait→result**
     pattern: either `POST /api/jobs/{type}?wait=true&timeout=N` (blocks, returns the terminal
     JobRecord), or create then `GET /api/jobs/{id}/wait?timeout=N`. Documents that jobs run
     server-side independent of the request (disconnect/504 ≠ failure; re-attach with another wait),
     that you should not poll in a loop, and how to read `result` / `errors` afterward.
   - **Eleven per-endpoint docs**, filenames matching the `KilnApiDocVerifier.api_doc_filename`
     derivation so the `call_kiln_api` precondition gate accepts them:
     `post_api_jobs_type.md`, `get_api_jobs_id_wait.md`, `get_api_jobs_id.md`,
     `get_api_jobs_id_result.md`, `get_api_jobs_id_errors.md`, `get_api_jobs.md`,
     `get_api_jobs_events.md`, `post_api_jobs_id_{pause,resume,cancel}.md`, `delete_api_jobs_id.md`.
     The jobs endpoints are already registered as agent-allowed in the `kiln_server` agent-checks
     annotations (`get/post/delete_api_jobs*.json`); lifecycle ops (pause/resume/cancel/delete)
     carry `requires_approval`, reflected in their docs.
   - **Discovery wiring** (discovery = modes → knowledge files' "API Docs" tables → `*_api_list.md`
     catalogs + per-endpoint docs, with `freeform_help.md`'s "Domain catalogs" table as the master
     index): added the `jobs_api_list.md` catalog to `freeform_help.md` (master index) and to the
     auto-mode-relevant knowledge files (`prompt_optimizer.md`, `fine_tuning.md`, `rag.md`,
     `experiment_batch.md`); and carved out the global `/api/jobs/...` prefix in the
     "Endpoint Conventions" / "Index-first" guidance of both operational modes (`improve_task.md`,
     `project_operations.md`), which previously asserted every URL is project-scoped.
   - **Verify:** `./checks.sh --agent-mode` passes (exit 0; markdown-only changes — no Python
     touched). The toolcall tests that consume api_docs (api_doc_verifier, skill precondition) pass.

## Tests

- `test_get_chat_kiln_tool_ids_uses_default_skill_id` / `..._respects_chat_skill_id_setting`
  (updated): the returned tuple now includes `"kiln_tool::enable_auto_mode"`.
- `test_enable_auto_mode_registered_as_client_visible_tool` (new): `"enable_auto_mode"` is in
  `CHAT_CLIENT_VISIBLE_TOOLS`, is in `get_chat_kiln_tool_ids()`, and is NOT in
  `CHAT_SERVER_SIDE_TOOLS`.
- Import smoke (command-line, not a pytest): `EnableAutoModeTool` /
  `ENABLE_AUTO_MODE_TOOL_NAME` importable from the synced env; `config.get_tools().client_tools`
  and `get_chat_kiln_tool_ids()` reflect the new tool.

## Notes / follow-up (do NOT do now)

- The local editable `path` deps are intentional for dev/testing. Before merging the backend
  branch, repoint `kiln-ai`/`kiln-server` back to a published Kiln git rev that includes the
  `enable_auto_mode` tool (architecture §11).
