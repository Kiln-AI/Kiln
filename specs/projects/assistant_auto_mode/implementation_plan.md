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

- [ ] **Phase 4 — Web UI**
  - `auto_run_store.ts` (enable/decline/stop/attach; feed per-run SSE into existing
    `StreamEventProcessor`). Consent dialog, footer indicator/toggle/Stop, history
    green-dot/"Working now" grouping, interrupt-on-send; regenerate `api_schema.d.ts`. vitest
    coverage. (`ui_design.md`, Architecture §5.)

- [ ] **Phase 5 — External backend wiring + end-to-end** (`/Users/leonardmarcq/Downloads/kiln_server`)
  - Branch `leonard/kil-692-assistant-auto-mode`; repoint `kiln-ai`/`kiln-server` to local editable
    paths (`libs/core`, `libs/server`) + `uv sync`. Register `enable_auto_mode` in
    `CHAT_CLIENT_VISIBLE_TOOLS` + `get_chat_kiln_tool_ids()`; add system-prompt guidance in chat
    `task.kiln` (solo-call, enabled/declined semantics). End-to-end verify flow A (suggest →
    consent → run → disconnect → re-attach → done). Before merge: repoint deps back to a published
    Kiln git rev that includes the tool. (Architecture §7, §11.)
