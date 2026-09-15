---
status: complete
---

# Phase 3: App-server API surface + `enable_auto_mode` interception

## Overview

Wires the Phase 2 auto-run engine into the app server's chat HTTP surface. Three pieces:

1. **Interception** — the interactive `/api/chat` stream (`ChatStreamSession.stream()`) detects an
   `enable_auto_mode` tool call in a round, emits an `auto-mode-consent-required` SSE event (carrying
   the enable tool-call id, optional reason, and any sibling client tool calls), and returns — never
   executing `enable_auto_mode` as a tool.
2. **Endpoints** — a new `auto/api.py` module exposing
   `enable / decline / {run}/stop / {run}/events / sessions`, mirroring `chat/routes.py` and
   `jobs/api.py` patterns. `enable` starts a registry run; `decline` resumes interactive streaming;
   `events` is a pure SSE observer over the per-run bus; `sessions` lists active runs.
3. **Session-list enrichment** — `ChatSessionListItem` gains `auto_active` / `auto_run_id`, populated
   via `auto_chat_registry.is_active_for_trace(row.id)`.

Plus wiring `connect_chat_auto_api(app)` in `desktop_server.py`. Server-side Python only.

## Steps

1. **`chat/constants.py`** — add SSE type constant alongside the existing ones:
   `SSE_TYPE_AUTO_MODE_CONSENT_REQUIRED = "auto-mode-consent-required"`.

2. **`chat/stream_session.py`** — interception in `ChatStreamSession.stream()`:
   - Import `ENABLE_AUTO_MODE_TOOL_NAME` from
     `kiln_ai.tools.built_in_tools.enable_auto_mode_tool` and the new constant.
   - Add module helper `_format_consent_required_sse(trace_id, enable_tool_call_id, reason, siblings)`
     producing `{type, trace_id, enable_tool_call_id, reason, sibling_tool_calls}` (siblings as
     pending-item dicts via `_pending_item_from_event`).
   - In the post-round block, inside `if round_state.finish_tool_calls:`, BEFORE the approval gate:
     scan `round_state.tool_input_events` for the first event whose `toolName ==
     ENABLE_AUTO_MODE_TOOL_NAME`. If found: `reason = enable_evt.input.get("reason")`,
     `siblings = [non-server client events != enable_evt]`, yield the consent SSE, `return`.

3. **`chat/auto/api.py`** (new) — `connect_chat_auto_api(app)` with these endpoints, all
   `tags=["Copilot"]`, `openapi_extra=DENY_AGENT`, `@no_write_lock` on the mutating ones
   (enable/decline/stop). Reuse `_get_base_url`, `_build_upstream_headers`, `get_copilot_api_key`
   from `chat/routes.py` and `kiln_server_client`.
   - `POST /api/chat/auto/enable` — body `EnableAutoRequest(AutoChatSeed + reason?)`; build
     upstream url/headers like routes.py; `auto_chat_registry.start(seed, reason, upstream_url,
     headers)`; return `{run_id}`. On `AutoChatConcurrencyError` → HTTP 429.
   - `POST /api/chat/auto/decline` — body `{trace_id, enable_tool_call_id, siblings?: [ToolCallInfo]}`.
     Build continuation messages: enable → `{"status":"declined"}`, each sibling → `DENIED_TOOL_OUTPUT`.
     Return `CancellableStreamingResponse(ChatStreamSession(...).stream())` (interactive resume).
   - `POST /api/chat/auto/{run_id}/stop` — `await auto_chat_registry.stop(run_id)`; 202; idempotent
     (stop is a no-op for unknown ids).
   - `GET /api/chat/auto/{run_id}/events` — 404 if `registry.get(run_id) is None`; else
     `CancellableStreamingResponse(iter_with_keepalive(run.bus.subscribe(), KEEPALIVE))` mapping
     `KeepalivePing` → `: ping\n\n`.
   - `GET /api/chat/auto/sessions` — `[{run_id, current_trace_id, status, reason}]` from
     `registry.list_active()`.

4. **`chat/routes.py`** — add `auto_active: bool = False` and `auto_run_id: str | None = None` to
   `ChatSessionListItem`; in `list_chat_sessions`, for each row call
   `auto_chat_registry.is_active_for_trace(item.id)` and set the fields.

5. **`chat/__init__.py`** — export `connect_chat_auto_api`.

6. **`desktop_server.py`** — import and call `connect_chat_auto_api(app)` next to
   `connect_chat_api(app)` / `connect_jobs_api(app)`.

## Tests

New `chat/auto/test_api.py` (FastAPI TestClient; app wires `connect_custom_errors`,
`connect_chat_api`, `connect_chat_auto_api`; fresh `AutoChatRegistry` patched in per test; upstream
mocked via the Phase-2 fakes / `PATCH_ASYNC_CLIENT`):

- `test_enable_starts_run_returns_run_id` — POST enable → 200 + `{run_id}`; registry has an active run.
- `test_enable_cap_returns_429` — registry at cap → 429 with a clear message.
- `test_decline_resumes_interactive_stream` — POST decline → 200 event-stream; continuation body sent
  upstream has enable→`{"status":"declined"}` and sibling→`DENIED_TOOL_OUTPUT`.
- `test_stop_returns_202_and_is_idempotent` — stop active run → 202; stop unknown id → 202.
- `test_events_streams_then_terminal` — attach to a run → bus bytes stream; `test_events_404_unknown`.
- `test_sessions_lists_active_runs` — sessions endpoint returns active run summaries.
- Interception (in `chat/test_routes.py` or here): `test_enable_auto_mode_emits_consent_required` —
  a round with an `enable_auto_mode` tool call emits `auto-mode-consent-required` (with reason +
  siblings carried) and does not execute it / continue.
- `test_session_list_auto_active_join` — `list_chat_sessions` sets `auto_active`/`auto_run_id` from
  the registry for a row whose trace is active.
- `test_auto_endpoints_have_no_write_lock` — enable/decline/stop carry `_git_sync_no_write_lock`.
