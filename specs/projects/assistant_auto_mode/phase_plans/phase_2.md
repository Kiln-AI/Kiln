---
status: complete
---

# Phase 2: App-server auto-run engine

## Overview

Lift the chat round-loop mechanics out of `ChatStreamSession.stream()` into a shared, reusable
async generator (`iter_upstream_round`), then build the server-owned auto-run engine on top of it:
an `AutoChatRegistry` that supervises one `asyncio.Task` per run (decoupled from any HTTP request),
an `AutoChatRunner` that drives the same round loop but auto-approves all client tools and emits to
a per-run event bus instead of yielding, and a per-run `AutoChatEventBus` that replays the
current-turn byte buffer on subscribe then goes live (buffer resets when a `kiln_chat_trace` event
is observed). No HTTP endpoints, no `enable_auto_mode` interception (those are Phase 3). The whole
thing is unit-tested against a fake/stubbed upstream, including a golden regression test proving the
interactive stream is byte-for-byte unchanged.

## Steps

1. **Refactor `stream_session.py`** — extract a module-level
   `iter_upstream_round(client, url, headers, body, round_state) -> AsyncIterator[bytes]` async
   generator holding the POST + SSE parse + forward-bytes + RoundState accumulation + non-200 /
   RemoteProtocolError handling (currently inline in `stream()` lines 104-180). It mutates
   `round_state` in place and yields forward-bytes; on a terminal upstream error it yields the
   standard error SSE bytes and stops. `ChatStreamSession.stream()` is reduced to loop over
   `iter_upstream_round` + apply the existing interactive post-round policy, byte-for-byte unchanged.
   The non-200/RemoteProtocolError branches need a tiny bit of shared state (`seen_upstream_error`,
   `trace_id_for_error`); carry these on `RoundState` so the generator owns them and the caller can
   read `round_state.trace_id` after.

2. **`auto/__init__.py`** — package marker (and convenience re-exports if useful).

3. **`auto/models.py`** — `AutoRunStatus(str, Enum)` (RUNNING/DONE/USER_STOPPED/ERROR/MAX_ROUNDS),
   `AutoChatSeed(BaseModel)` (trace_id, enable_tool_call_id, pending_tool_calls: list[ToolCallInfo],
   extra_messages: list[dict]), `AutoRunRecord(BaseModel)` (run_id, status, current_trace_id,
   seen_trace_ids, reason, created_at, updated_at). `_new_run_id() -> "ar_<base32>"` mirroring
   `_new_job_id`. `_utc_now`.

4. **`auto/events.py`** — `AutoChatEventBus` per run. Reuse `iter_with_keepalive` from
   `jobs/events.py` (import it). `subscribe()` replays `list(run.buffer)` then, if run already
   terminal, yields the `auto-mode-off` terminal bytes and returns; else goes live off an
   `asyncio.Queue`. `publish(b)` puts to all subscriber queues. The buffer + buffer-reset logic
   lives on the run (`AutoChatRun.emit`), not the bus.

5. **`auto/runner.py`** — `AutoChatRunner`. Constructed with seed, url, headers, an `emit` callback
   (the run's `emit`), and the registry `_on_trace` callback. `run()` implements the §3.2 loop:
   emit `auto-mode-on`; build seed body; for each of `MAX_TOOL_ROUNDS`: `iter_upstream_round` →
   emit each byte (run.emit detects `kiln_chat_trace` → reset buffer + `_on_trace`); if no
   finish_tool_calls → status DONE/asked_user, return; build client `ToolCallInfo`s with
   `requiresApproval=False` (auto-approve); emit exec-start; `execute_tool_batch(tool_calls, {})`;
   emit each tool-output + exec-end; if empty results → DONE; else
   `_build_openai_tool_continuation`. After the loop: status MAX_ROUNDS + emit the
   "Maximum tool rounds exceeded" error SSE. `_build_seed_body()` per §3.5.
   SSE formatters (`tool_exec_start`, `tool_output`, `tool_exec_end`, `auto-mode-on/off`,
   `kiln_chat_trace` detection helper) live here / reused.

6. **`auto/registry.py`** — `AutoChatRegistry` singleton modeled on `JobRegistry`. State:
   `_runs: dict[str, AutoChatRun]`, `_trace_index: dict[str,str]`, `_tasks: dict[str, asyncio.Task]`,
   max-concurrent from `KILN_CHAT_AUTO_MAX_CONCURRENT` (default 5), terminal TTL.
   `AutoChatRun` (in-memory, not a pydantic model) holds the record, task, bus, buffer + `emit`.
   Methods: `start(seed, *, reason, upstream_url, headers)` (enforce cap → raise
   `AutoChatConcurrencyError`, mint run_id, create run, seed seen_trace_ids/_trace_index, spawn
   `_supervise`), `get`, `list_active`, `run_id_for_trace`, `is_active_for_trace`, `stop`,
   `_supervise` (run.runner.run() with status/exception handling per §3.3; finally release slot +
   schedule terminal GC), `_on_trace`. Module-level `auto_chat_registry`.

## Tests

- `test_iter_upstream_round` golden / interactive-unchanged: feed synthetic upstream SSE through a
  fake httpx client; assert `ChatStreamSession.stream()` produces the exact bytes (text-delta,
  tool rounds, errors) — regression guard. Plus the existing `test_stream_session.py` tests must
  still pass unchanged.
- Runner happy paths: server-tool-only round → DONE; multi-round with an auto-executed client tool
  (call_kiln_api) → continues then DONE; finish-with-text-only → DONE/asked_user.
- Auto-approve: a tool whose event carries `requires_approval=true` executes with NO
  `tool-calls-pending` event emitted (runner emits exec-start/output/end instead).
- Runner MAX_ROUNDS backstop emits the error SSE and sets MAX_ROUNDS.
- Seed building: enabled / declined-less (no enable) / sibling pending_tool_calls / extra_messages
  variants produce the right continuation body.
- Registry cap: 6th concurrent start raises `AutoChatConcurrencyError`.
- `_on_trace` updates `seen_trace_ids`/`current_trace_id`/`_trace_index`.
- `is_active_for_trace` / `run_id_for_trace` true for seen trace of active run, false after terminal.
- `stop` → CancelledError → USER_STOPPED + auto-mode-off(user_stopped) published.
- Terminal TTL GC removes the run + its trace index entries after the TTL.
- Client/subscriber disconnect does NOT cancel the run: subscribe, drop the subscriber mid-run,
  assert the run keeps advancing to a terminal state.
- Bus/buffer: subscribe replays current-turn buffer then live; buffer resets after a
  `kiln_chat_trace` event; terminal run yields auto-mode-off immediately; keepalive injects pings.
