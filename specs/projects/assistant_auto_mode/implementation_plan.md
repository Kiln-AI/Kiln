---
status: complete
---

# Implementation Plan: Assistant Auto-Mode

Ordered by dependency. Each phase is one reviewable unit. Details live in `functional_spec.md`,
`ui_design.md`, and `architecture.md` — this is the checklist, not a restatement.

## Phases

- [x] **Phase 1 — Branch + `enable_auto_mode` tool in libs/core**
  - Create/switch branch `leonard/kil-692-assistant-auto-mode` in this repo.
  - Add `EnableAutoModeTool` (`libs/core/kiln_ai/tools/built_in_tools/enable_auto_mode_tool.py`),
    `KilnBuiltInToolId.ENABLE_AUTO_MODE`, `tool_registry.py` case; schema `reason?: string`;
    signal-only `run()`. Unit tests mirroring `test_kiln_api_call_tool.py` /
    `test_tool_registry.py`. (Architecture §7.)

- [x] **Phase 2 — App-server auto-run engine** (`app/desktop/studio_server/chat/auto/`)
  - Refactor: extract `iter_upstream_round()` from `ChatStreamSession.stream()` + **golden
    regression test** proving interactive output is unchanged. (Architecture §3.1.)
  - `models.py` (`AutoRunStatus`, `AutoChatSeed`, `AutoRunRecord`), `registry.py`
    (`AutoChatRegistry`: task supervision, concurrency cap, `_trace_index`, lifecycle),
    `runner.py` (`AutoChatRunner` loop: auto-approve, emit-to-bus), per-run `AutoChatEventBus` +
    current-turn buffer (reuse/promote `iter_with_keepalive`). Unit-tested against a fake upstream;
    explicitly assert client-disconnect does not cancel the run. (Architecture §2–§4.1, §9.)

- [x] **Phase 3 — App-server API surface + interception**
  - `enable_auto_mode` interception in `ChatStreamSession` → `auto-mode-consent-required` + return
    (Architecture §3.4). Endpoints `/api/chat/auto/{enable,decline,{run}/stop,{run}/events,sessions}`
    (§4.2). Session-list enrichment (`auto_active`/`auto_run_id`, §4.3). Register
    `connect_chat_auto_api` in `desktop_server.py`. FastAPI `TestClient` tests incl. decline →
    interactive resume.

- [x] **Phase 4 — Web UI**
  - `auto_run_store.ts` (enable/decline/stop/attach; feed per-run SSE into existing
    `StreamEventProcessor`). Consent dialog, footer indicator/toggle/Stop, history
    green-dot/"Working now" grouping, interrupt-on-send; regenerate `api_schema.d.ts`. vitest
    coverage. (`ui_design.md`, Architecture §5.)

- [x] **Phase 5 — External backend wiring + end-to-end** (`/Users/leonardmarcq/Downloads/kiln_server`)
  - Branch `leonard/kil-692-assistant-auto-mode`; repoint `kiln-ai`/`kiln-server` to local editable
    paths (`libs/core`, `libs/server`) + `uv sync`. Register `enable_auto_mode` in
    `CHAT_CLIENT_VISIBLE_TOOLS` + `get_chat_kiln_tool_ids()`; add system-prompt guidance in chat
    `task.kiln` (solo-call, enabled/declined semantics). End-to-end verify flow A (suggest →
    consent → run → disconnect → re-attach → done). Before merge: repoint deps back to a published
    Kiln git rev that includes the tool. (Architecture §7, §11.)

### Revision R1 — Conversation-scoped auto-mode (inject-on-send, persist, disable)

- [x] **Phase 6 — Engine: persistence + injection + `disable_auto_mode`** (libs/core + app server)
  - libs/core: `DisableAutoModeTool` (`KilnBuiltInToolId.DISABLE_AUTO_MODE`, registry case,
    signal-only `run()`, `DISABLE_AUTO_MODE_TOOL_NAME`), mirroring `enable_auto_mode`; tests.
  - App server (`chat/auto/` + `stream_session.py`): decouple the conversation-scoped auto-mode
    flag from burst liveness — add `AutoRunStatus.IDLE`; burst-end (asked/done/error/max_rounds)
    → IDLE + `auto-mode-idle` event (flag stays on, entry not evicted); `auto-mode-off` only on
    explicit disable (`user_stopped`/`user_disabled`); `is_active_for_trace`/`auto_active` reflect
    RUNNING-or-IDLE. Inbound message queue + `POST /api/chat/auto/{run_id}/message` (inject at next
    round boundary when active; start a new burst when idle; echo the user message to the bus).
    Intercept `disable_auto_mode` in both `ChatStreamSession` and `AutoChatRunner` (clear flag,
    `auto-mode-off(user_disabled)`, resolve tool result, continue interactive). Update tests
    (incl. inject-at-boundary, idle persistence, disable interception, drain-before-idle edge).
    (Architecture §13.1–§13.3, §13.5–§13.6.)

- [x] **Phase 7 — Web UI: inject-on-send + persistent flag** (app/web_ui)
  - Send while `autoModeOn` → `POST /api/chat/auto/{run_id}/message` (remove the interrupt/stop-on-send).
    Bind the indicator + Stop to the conversation auto-mode flag (persist across IDLE bursts);
    handle `auto-mode-idle` (stay on, optional working/idle sub-state) vs `auto-mode-off` (clear).
    Consent only once per conversation. Update vitest coverage. (`ui_design.md` §2/§6, Arch §13.4.)

- [x] **Phase 8 — Backend wiring for `disable_auto_mode`** (`/Users/leonardmarcq/Downloads/kiln_server`)
  - Register `disable_auto_mode` in `CHAT_CLIENT_VISIBLE_TOOLS` + `get_chat_kiln_tool_ids()`
    (mirror enable); add system-prompt guidance: call `disable_auto_mode` (alone) when the user
    asks to stop auto-mode, then continue interactively. Verify. (Architecture §13.3.)

- [x] **Phase 9 — Reattach loading state + live working/idle on attach** (app server + web UI)
  - Surface the run's current **working/idle** liveness on attach so reattach reflects true state
    immediately (no "looks done until next event"): the per-run `AutoChatEventBus` emits the current
    working/idle marker on subscribe, and `GET /api/chat/auto/resolve` also returns the run status.
    Web UI: a transient "reconnecting…" loading state during resolve→hydrate→attach (resyncOnLoad +
    history-restore), cleared once attach is established; on attach show the thinking indicator if
    working or "· waiting for you" if idle, driven by the surfaced state. Reuse existing
    indicator/working machinery. Tests. (Architecture §13.)
