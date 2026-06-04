---
status: complete
---

# Architecture: Assistant Auto-Mode

## 0. Approach & Scope

The whole feature is, at heart, **lifting the existing app-server chat loop out of the browser's
HTTP request into a server-owned, in-memory runner that auto-approves tool calls**, plus the
plumbing to observe/re-attach to that runner, plus a small backend tool to let the model suggest
it.

The single most important simplifying insight: **in every trigger path the interactive
`/api/chat` stream `return`s *before* the runner starts** (it returns at `tool-calls-pending`
today, and will also return at a new `auto-mode-consent-required`). So the runner always begins a
**fresh upstream continuation** from a `trace_id` + seed messages. There is **no live-stream
handoff** to coordinate — a major reduction in complexity.

Three codebases change:

| Layer | Repo / path | Change |
|---|---|---|
| **libs/core (`kiln-ai`)** | `libs/core/kiln_ai/tools/` | New built-in tool `EnableAutoModeTool` (mirrors `kiln_api_call_tool.py`): new `KilnBuiltInToolId.ENABLE_AUTO_MODE`, `tool_registry.py` case, schema `enable_auto_mode(reason?: string)`. Lives here so the external backend picks it up via its `kiln-ai` dependency. |
| **App server (primary)** | `app/desktop/studio_server/chat/` | New `auto/` package: registry, runner, per-run event bus; refactor of `ChatStreamSession` to share round mechanics + intercept `enable_auto_mode`; new endpoints; session-list enrichment. |
| **Web UI** | `app/web_ui/src/.../assistant/` + `lib/chat/` | Consent dialog, footer indicator/toggle/stop, history "working" treatment, an auto-run store that subscribes to the per-run SSE and drives enable/decline/stop. |
| **External backend** | `kiln_server` at `/Users/leonardmarcq/Downloads/kiln_server` (separate repo, pkg `kiln-service`) | Repoint `kiln-ai`/`kiln-server` deps at this repo's local `libs/core`+`libs/server` (`uv sync`); register `enable_auto_mode` as a client tool + system-prompt guidance. (Cross-repo — §7, §11.) |

It mirrors patterns already in the repo: the **background-job system** (`jobs/registry.py`,
`jobs/events.py`, `jobs/api.py`) for the registry/task-supervision/SSE-observer shape, and the
existing `ChatStreamSession` for the round loop.

## 1. Data Model

### 1.1 App-server runtime entities (in-memory only)

```python
# app/desktop/studio_server/chat/auto/models.py

class AutoRunStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"            # assistant asked the user / finished naturally
    USER_STOPPED = "stopped" # user hit Stop
    ERROR = "error"          # unrecoverable runner/upstream error
    MAX_ROUNDS = "max_rounds"

class AutoChatSeed(BaseModel):
    """Everything needed to begin (or resume into) an auto run as a fresh upstream continuation."""
    trace_id: str
    enable_tool_call_id: str | None = None      # resolve this enable_auto_mode call as "enabled"
    pending_tool_calls: list[ToolCallInfo] = [] # sibling client tools to auto-execute first (usually empty)
    extra_messages: list[dict[str, Any]] = []   # e.g. a new user message (manual idle path)

class AutoRunRecord(BaseModel):
    run_id: str                 # "ar_<base32>" (mirror jobs _new_job_id)
    status: AutoRunStatus
    current_trace_id: str       # latest persisted leaf the runner has seen
    seen_trace_ids: list[str]   # whole chain this run has touched (for history correlation)
    reason: str | None = None   # model-supplied reason from enable_auto_mode
    created_at: datetime
    updated_at: datetime
    # terminal runs are kept for TERMINAL_TTL_SECONDS so a late re-attach still gets auto-mode-off
```

`AutoChatRun` (not serialized) holds the live machinery: the `AutoRunRecord`, the `asyncio.Task`,
the per-run `AutoChatEventBus`, and the **current-turn byte buffer** (`list[bytes]`).

### 1.2 SSE event vocabulary additions

On the **interactive `/api/chat` stream** (emitted by the refactored `ChatStreamSession`):

- `auto-mode-consent-required` — `{ "type": "auto-mode-consent-required", "trace_id": str,
  "enable_tool_call_id": str, "reason": str|null, "sibling_tool_calls": [ <pending item>, ... ] }`.
  The stream then `return`s (same shape as the existing `tool-calls-pending` pattern).

On the **per-run auto stream** (`GET /api/chat/auto/{run_id}/events`) the bytes are the **same
chat SSE events** the runner produces (`text-delta`, `reasoning-*`, `tool-input-*`,
`kiln-tool-execution-start/end`, `tool-output-available`, `kiln_chat_trace`, `error`) — identical
vocabulary to today so the existing `StreamEventProcessor` consumes them unchanged — plus:

- `auto-mode-on` — `{ "type": "auto-mode-on", "run_id": str }`
- `auto-mode-off` — `{ "type": "auto-mode-off", "run_id": str, "reason": "done"|"asked_user"|
  "user_stopped"|"error"|"max_rounds" }`

### 1.3 Session-list enrichment

`ChatSessionListItem` (app-server `routes.py`) gains two optional fields:

```python
class ChatSessionListItem(BaseModel):
    id: str
    title: str | None = None
    updated_at: datetime | None = None
    auto_active: bool = False        # NEW
    auto_run_id: str | None = None   # NEW (for direct re-attach)
```

Populated by joining each row's `id` against the registry (§4.5).

## 2. Component: `AutoChatRegistry`

`app/desktop/studio_server/chat/auto/registry.py` — process singleton, modeled on
`JobRegistry`.

State:
- `_runs: dict[str, AutoChatRun]`
- `_trace_index: dict[str, str]` — `leaf_trace_id → run_id` (every seen trace id maps to its run)
- `_tasks: dict[str, asyncio.Task]`
- `_semaphore` / cap from `KILN_CHAT_AUTO_MAX_CONCURRENT` (default **5**)

Methods:
- `start(seed: AutoChatSeed, *, reason, upstream_url, headers) -> AutoRunRecord` — enforce cap
  (reject with a clear error if exceeded — auto-mode is interactive, no queueing), mint `run_id`,
  create `AutoChatRun`, seed `seen_trace_ids=[seed.trace_id]` + `_trace_index[seed.trace_id]=run_id`,
  spawn the supervising task (`asyncio.create_task(self._supervise(run))`), return the record.
- `get(run_id)`, `list_active()` (status==RUNNING), `run_id_for_trace(trace_id) -> str|None`
  (active runs only).
- `stop(run_id)` — cancel the task (cooperative); the task's handler sets `USER_STOPPED` and
  publishes `auto-mode-off`.
- `_supervise(run)` — owns the run lifetime (decoupled from any HTTP request, exactly like
  `JobRegistry._supervise`): `try: await run.runner.run()` with the status/exception handling in
  §3.3; `finally:` release the semaphore slot and schedule terminal GC after `TERMINAL_TTL`.
- `_on_trace(run, new_trace_id)` — callback the runner invokes when it observes a `kiln_chat_trace`:
  append to `seen_trace_ids`, set `current_trace_id`, `_trace_index[new]=run_id`, `_touch`.
- `is_active_for_trace(trace_id) -> (bool, run_id|None)` — used by session-list enrichment.

**Client disconnect never touches the task** (the task lives here, not in the HTTP response) —
this is the property that makes work survive the UI closing.

## 3. Component: `AutoChatRunner` + shared round mechanics

### 3.1 Refactor: extract shared per-round upstream driver

Today `ChatStreamSession.stream()` (lines 105–180) inlines: POST upstream → parse SSE → forward
bytes → accumulate `RoundState`. Extract this into a module-level async generator reused by both
the interactive session and the runner:

```python
# stream_session.py (or a new shared module)
async def iter_upstream_round(
    client: httpx.AsyncClient, url: str, headers: dict[str, str],
    body: dict[str, Any], round_state: RoundState,
) -> AsyncIterator[bytes]:
    """POST one upstream round; yield forward-bytes as they stream; mutate round_state in place.
    Yields a terminal error-bytes payload and stops on non-200 / RemoteProtocolError per today's
    logic (lines 115–180). Sets round_state.{finish_tool_calls, tool_input_events, assistant_text,
    trace_id}."""
```

`ChatStreamSession.stream()` is reduced to: loop → `async for b in iter_upstream_round(...): yield b`
→ apply the **interactive** post-round policy (existing lines 182–229) **plus the new
`enable_auto_mode` interception (§3.4)**. Behavior is otherwise byte-for-byte unchanged, preserving
all current non-auto chat behavior (verified by existing tests).

### 3.2 `AutoChatRunner`

`app/desktop/studio_server/chat/auto/runner.py`. Constructed with the seed, upstream url/headers,
the per-run bus, the buffer, and the registry `_on_trace` callback. Core loop:

```python
async def run(self):
    self._emit_control({"type": "auto-mode-on", "run_id": self.run_id})
    body = self._build_seed_body()          # §3.5
    async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
        for _ in range(MAX_TOOL_ROUNDS):    # 100 backstop, shared constant
            rs = RoundState()
            async for b in iter_upstream_round(client, self.url, self.headers, body, rs):
                self._emit(b)               # buffer + publish (and detect kiln_chat_trace → reset buffer + registry._on_trace)
            if rs.trace_id:
                body = {**body, "trace_id": rs.trace_id, "messages": []}
            if not rs.finish_tool_calls:
                self.status = DONE          # assistant text only → asked user / done
                return
            client_events = [e for e in rs.tool_input_events
                             if not tool_input_executor_is_server(e)]
            # AUTO-APPROVE: build ToolCallInfo with requiresApproval=False → execute_tool_batch skips the gate
            tool_calls = [ToolCallInfo(toolCallId=e.toolCallId, toolName=e.toolName,
                                       input=e.input, requiresApproval=False)
                          for e in client_events]
            self._emit(tool_exec_start(len(tool_calls)))
            results = await execute_tool_batch(tool_calls, {})   # reused unchanged
            for tc_id, out in results.items(): self._emit(tool_output(tc_id, out))
            self._emit(tool_exec_end(len(results)))
            if not results:
                self.status = DONE
                return
            body = _build_openai_tool_continuation(body, rs.assistant_text,
                                                   rs.tool_input_events, results)  # reused unchanged
        self.status = MAX_ROUNDS            # exhausted backstop
```

Reuses `RoundState`, `tool_input_executor_is_server`, `execute_tool_batch`, `execute_tool`,
`_build_openai_tool_continuation`, the SSE formatters, and `EventParser` **unchanged**. The only
behavioral difference from interactive mode is: **no approval gate** (all `requiresApproval=False`)
and **emit-to-bus instead of yield**.

### 3.3 Status / error / cancellation handling (in `_supervise`)

- Natural finish (`DONE`/`MAX_ROUNDS`) → publish `auto-mode-off` with reason `done`/`max_rounds`
  (use `asked_user` vs `done` heuristically: if the last assistant turn had text and no tool calls
  we report `asked_user`; both are functionally "off"). For `MAX_ROUNDS` also emit an `error`
  chat event with the existing "Maximum tool rounds exceeded" message.
- Non-200 / `RemoteProtocolError` / unexpected exception → `iter_upstream_round` already emits the
  standard `error` SSE bytes; runner sets `ERROR`, publishes `auto-mode-off(error)`.
- `asyncio.CancelledError` (user Stop / shutdown) → set `USER_STOPPED`, publish
  `auto-mode-off(user_stopped)`, re-raise. In-flight `execute_tool_batch` await may be cancelled;
  a tool that already kicked off a background job is fine — that job runs independently in the jobs
  system (functional spec §7).

### 3.4 `enable_auto_mode` interception (interactive path)

In `ChatStreamSession`'s post-round handling, **before** the existing approval gate: if any
`tool_input_event.toolName == ENABLE_AUTO_MODE_TOOL_NAME` (`"enable_auto_mode"`, new constant):

```python
enable_evt = first such event
reason = enable_evt.input.get("reason")          # optional, from the tool args
siblings = [non-server client events excluding enable_evt]
yield _format_consent_required_sse(trace_id=round_state.trace_id,
                                   enable_tool_call_id=enable_evt.toolCallId,
                                   reason=reason, siblings=siblings)
return
```

The model is instructed to call `enable_auto_mode` **alone** (§7 backend guidance); `siblings` is
normally empty. If non-empty, it is carried through so accept/decline can resolve every
`tool_call_id` (the backend requires a result for each).

### 3.5 Seed → first upstream body

`_build_seed_body()` constructs the OpenAI-shaped continuation:

- Start `messages = list(seed.extra_messages)` (manual idle path: the new user message;
  otherwise empty).
- If `seed.enable_tool_call_id`: append `{"role":"tool","tool_call_id": enable_id,
  "content": '{"status":"enabled"}'}`.
- For each `seed.pending_tool_calls` (rare siblings): auto-execute now via `execute_tool_batch`
  and append their `role:tool` results.
- Body = `{"trace_id": seed.trace_id, "messages": messages}`.

(The backend continues from `trace_id` with these tool results — same continuation contract
`/execute-tools` already uses.)

## 4. Component: per-run event bus, buffering, endpoints

### 4.1 `AutoChatEventBus` (per run)

Mirrors `JobEventBus` (asyncio.Queue per subscriber, set of subscribers, `iter_with_keepalive`
reused verbatim from `jobs/events.py` — promote it to a shared util or import it). Difference:
**on subscribe, replay the current-turn buffer before going live.**

```python
async def subscribe(self) -> AsyncGenerator[bytes, None]:
    sub = _ByteSubscriber()
    self._subs.add(sub)
    try:
        for b in list(self._run.buffer):  # replay in-progress turn
            yield b
        if self._run.status != RUNNING:   # already finished → emit terminal marker and stop
            yield auto_mode_off_bytes(self._run)
            return
        while True:
            yield await sub.queue.get()
    finally:
        self._subs.discard(sub)
```

`_emit(b)` on the run: append to `buffer`, `publish` to all subscribers. **Buffer reset:** when a
`kiln_chat_trace` event is observed (a snapshot was just persisted), clear `buffer` *after*
forwarding that event — so the buffer always holds exactly "events since the last persisted
snapshot" = the in-progress turn. This is what makes gapless re-attach work (functional spec
§4.5.2): completed turns come from `GET /api/chat/sessions/{trace}`; the in-progress turn comes
from the buffer replay.

### 4.2 Endpoints (`app/desktop/studio_server/chat/auto/api.py`)

| Endpoint | Behavior |
|---|---|
| `POST /api/chat/auto/enable` | Body: `AutoChatSeed` + optional `reason`. Calls `registry.start(...)`. Returns `{ run_id }`. (Used by both backend-tool accept and manual paths.) |
| `POST /api/chat/auto/decline` | Body: `{ trace_id, enable_tool_call_id, siblings: [...] }`. Builds a continuation body resolving enable→`{"status":"declined"}` and any siblings→`DENIED_TOOL_OUTPUT`, returns `CancellableStreamingResponse(ChatStreamSession(seed).stream())` — i.e. resume **interactive** streaming. |
| `POST /api/chat/auto/{run_id}/stop` | `registry.stop(run_id)`; 202. Idempotent. |
| `GET /api/chat/auto/{run_id}/events` | `CancellableStreamingResponse` over `iter_with_keepalive(run.bus.subscribe(), KEEPALIVE)`. Pure observer — disconnect only unsubscribes. 404 if unknown (already GC'd → UI falls back to hydrate-only). |
| `GET /api/chat/auto/sessions` | `[{ run_id, current_trace_id, status, reason }]` for active runs (optional; the enriched session list usually suffices). |

All under the existing `tags=["Copilot"]`, `@no_write_lock` where they mutate, and `DENY_AGENT`
(these must never be agent-invokable).

### 4.3 Session-list enrichment

`list_chat_sessions` (routes.py) computes, per returned row,
`auto_active, auto_run_id = registry.is_active_for_trace(row.id)` and sets the new fields. This is
the **server-side join** (functional spec §6.3): one place, one instant, no two-list correlation in
the browser. Residual sub-ms race is self-healing.

### 4.4 Wiring

`connect_chat_auto_api(app)` registered in `app/desktop/desktop_server.py` next to
`connect_chat_api(app)` and `connect_jobs_api(app)`. The registry is a module-level singleton like
`job_registry`.

## 5. Web UI

### 5.1 `auto_run_store.ts` (new, `lib/chat/`)

Owns auto-run lifecycle for the active conversation, mirroring `jobs_store.ts` connection handling:
- `requestEnable(seed)` → `POST /api/chat/auto/enable` → on `{run_id}`, open
  `EventSource('/api/chat/auto/{run_id}/events')` and feed bytes into the **existing**
  `StreamEventProcessor` (reused — the events are the same vocabulary), plus handle
  `auto-mode-on/off`.
- `decline(...)` → `POST /api/chat/auto/decline`, then consume the returned interactive stream via
  the existing `streamChat` reader path.
- `stop(run_id)` → `POST .../stop`.
- `attach(run_id)` → open the events SSE for re-attach (after `hydrateSessionFromSnapshot`).
- Exposes `autoModeOn`, `runId`, `offReason` stores for the footer/indicator.

`chat_session_store.ts` integration: when the interactive stream emits
`auto-mode-consent-required`, surface it (open the consent dialog). On accept → `auto_run_store`
takes over; the chat store stops driving `/api/chat` for this turn.

### 5.2 Components (per `ui_design.md`)

- `auto_mode_consent_dialog.svelte` — uses `Dialog`; copy from ui_design §3; Accept→enable,
  Cancel→decline.
- Footer block in `chat.svelte` (~L1070, by `ChatCostDisclaimer`): muted `⏵⏵ Auto mode` ghost
  (off) ↔ green `⏵⏵ auto mode on · Stop` (on), bound to `auto_run_store.autoModeOn`.
- `chat_history.svelte`: render `auto_active` rows with the green dot + "Working…" and the
  "Working now" group; selecting an active row calls `selectSession` then
  `auto_run_store.attach(row.auto_run_id)`.
- Interrupt-on-send (ui_design §2): if `autoModeOn`, `sendMessage` first calls
  `auto_run_store.stop()` then sends interactively.

### 5.3 Generated API types

Re-run the OpenAPI type generation so `api_schema.d.ts` picks up the new endpoints and the
`auto_active`/`auto_run_id` fields (existing `npm` codegen step).

## 6. Key Flows

**A. Backend-suggested, user closes laptop, returns:**
1. `/api/chat` streaming; backend model calls `enable_auto_mode(reason)` → backend returns control,
   persists snapshot, emits `kiln_chat_trace(N)`.
2. App server intercepts → emits `auto-mode-consent-required` → `return`. Browser shows dialog.
3. User Accept → `POST /api/chat/auto/enable {trace_id:N, enable_tool_call_id}` →
   `registry.start` spawns runner (status RUNNING; `_trace_index[N]`). Browser opens
   `/auto/{run}/events`, shows green indicator.
4. Runner resolves enable=enabled, continues rounds, auto-executing `call_kiln_api` (e.g. kicking
   off a reflective-optimization **job**), advancing trace N→N+1→… (`_on_trace` updates index).
5. User closes browser → SSE unsubscribes; **runner keeps going** (task owned by registry).
6. User returns, opens History → row for the conversation shows green dot (`is_active_for_trace`).
   Clicks → hydrate from latest trace + `attach(run_id)` → buffer replay catches up the in-progress
   turn, then live.
7. Model emits a plain-text turn (question/done) → runner sets DONE → `auto-mode-off(asked_user)`
   → indicator clears; conversation fully persisted; user resumes interactively.

**B. Manual toggle, idle:** user toggles → consent → `POST /auto/enable {trace_id, extra_messages:[userMsg]}`
(no enable_tool_call_id) → runner runs that turn unattended.

**C. Manual toggle, mid-approval:** interactive stream already returned `tool-calls-pending`;
Accept → `POST /auto/enable {trace_id, pending_tool_calls:[...]}` → runner auto-executes the
pending tools and continues.

**D. Stop:** user clicks Stop → `POST /auto/{run}/stop` → task cancelled → `auto-mode-off(user_stopped)`.

**E. Decline:** Cancel → `POST /auto/decline` → interactive stream resumes with enable→declined.

## 7. The tool (libs/core) + backend (kiln_server) wiring

**Tool implementation lives in this repo's `libs/core`** (so the external backend inherits it via
its `kiln-ai` dependency), mirroring `call_kiln_api`:

- `libs/core/kiln_ai/tools/built_in_tools/enable_auto_mode_tool.py`: `EnableAutoModeTool` with
  name `enable_auto_mode`, description, and `parameters_schema` = optional `reason: string`.
- `KilnBuiltInToolId.ENABLE_AUTO_MODE` + a case in `tool_registry.py::tool_from_id`.
- `run()` is a **signal no-op** (returns a `ToolCallResult` like `{"status":"enabled"}`): in chat
  it is never executed — the backend treats it as client-visible (returns control) and the app
  server intercepts it. `run()` exists only to keep the libs/core tool surface complete/standalone
  (per the "libs/core is a standalone library" invariant). **Do not** add it to the app server's
  `FUNCTION_NAME_TO_TOOL_ID` — interception by name happens first, and we never want it executed.

**External backend wiring** (`/Users/leonardmarcq/Downloads/kiln_server`, branch
`leonard/kil-692-assistant-auto-mode`):

- `pyproject.toml`: repoint `kiln-ai` and `kiln-server` from their pinned `git`/`rev` sources to
  this repo's local paths as editable installs, e.g.
  `kiln-ai = { path = "/Users/leonardmarcq/Downloads/Kiln/libs/core", editable = true }` and the
  analogous `kiln-server` → `libs/server`; then `uv sync`. This makes the new tool available to the
  backend without publishing.
- In `kiln-fastapi-api`'s `api/kiln_fastapi_api/chat/config.py`: add `"enable_auto_mode"` to
  `CHAT_CLIENT_VISIBLE_TOOLS` and add `kiln_tool::enable_auto_mode` to `get_chat_kiln_tool_ids()`,
  so the backend exposes the tool's schema to the model and returns control (persists snapshot +
  emits `kiln_chat_trace`) when it is called.
- System-prompt guidance in the chat `task.kiln`: when to suggest auto-mode (a multi-step,
  tool/job-driven plan the user has signed off on), that it must call `enable_auto_mode` **alone**
  (no sibling tool calls that turn), that the user may decline (`{"status":"declined"}` → proceed
  interactively), and that on `{"status":"enabled"}` it should carry on doing the work.
- No backend `run()` is needed (client-visible/intercepted).

## 8. Error Handling Strategy

- Upstream non-200 / protocol errors: handled inside `iter_upstream_round` (reused logic) — emits
  the standard `error` SSE; runner → ERROR + `auto-mode-off(error)`. Conversation preserved at last
  snapshot.
- Tool errors: returned to the backend as tool results (existing behavior); run continues. Only an
  unrecoverable runner error ends the run.
- Concurrency cap exceeded: `enable` returns HTTP 429 with a clear message; UI shows it in the
  consent dialog area.
- Re-attach to a GC'd/terminal run: `events` 404 or immediate `auto-mode-off` → UI falls back to
  hydrate-only ("Catching up…" then normal).
- App-server restart: registry is empty on boot; no auto-resume (functional spec §4.7). Any browser
  still polling sees `auto_active=false` and re-attach 404 → clean degrade.
- Logging: reuse module loggers; log run lifecycle transitions and upstream errors with `run_id` +
  `trace_id`, matching the jobs system's logging detail.

## 9. Testing Strategy

Frameworks: `pytest`/`pytest-asyncio` (server), `vitest` (web UI) — as elsewhere in the repo.

**App server (unit, with a fake upstream):**
- `iter_upstream_round` refactor: golden test that `ChatStreamSession.stream()` output is unchanged
  vs. current behavior (regression guard) — feed recorded upstream SSE fixtures.
- Runner happy path: server-tool-only rounds → DONE; multi-round with `call_kiln_api` auto-executed
  (no approval gate hit) → continues; finish-with-text → DONE/asked_user.
- Auto-approve: a tool with `requiresApproval=true` is executed without any pending event emitted.
- `enable_auto_mode` interception: turn containing it emits `auto-mode-consent-required` and
  returns; siblings carried.
- Seed building: enabled/declined/sibling/extra_messages variants produce correct continuation
  bodies.
- Registry: cap enforcement (429), `_on_trace` index updates, `is_active_for_trace`, stop →
  CancelledError → USER_STOPPED, terminal TTL GC, **client disconnect does not cancel the task**
  (drop a subscriber mid-run; assert the run keeps advancing).
- Bus/buffer: subscribe replays current-turn buffer then live; buffer resets on `kiln_chat_trace`;
  keepalive injects pings; terminal run yields `auto-mode-off` immediately.
- Endpoints: enable/decline/stop/events/sessions-enrichment via FastAPI `TestClient`; decline
  resumes interactive stream; session list `auto_active` join.

**Web UI (vitest + mocked EventSource/fetch):**
- `auto_run_store`: enable→attach→events feed into `StreamEventProcessor`; off-event clears state;
  stop; decline path; re-attach (hydrate + attach) renders without gaps; events 404 → fallback.
- Consent dialog accept/decline wiring; footer state transitions; interrupt-on-send; history green
  dot/grouping from `auto_active`.

**Integration (optional, high value):** end-to-end flow A against a stub backend exercising
disconnect + re-attach + completion.

## 10. Design Patterns & Rationale

- **Registry-owned supervised task** (not request-scoped generator): the only way work survives the
  UI closing; copies the jobs system's proven shape.
- **Pure-observer SSE with buffer replay**: decouples observation from execution and gives gapless
  re-attach without persisting transient events.
- **Maximal reuse of `ChatStreamSession` mechanics**: one extracted `iter_upstream_round` keeps
  interactive and auto paths from diverging; auto path differs only by "no approval gate" +
  "emit to bus".
- **Fresh-continuation-only**: avoids live-stream handoff entirely (the big simplification).
- **Server-side join for active-state**: avoids brittle client correlation of an advancing id.

## 11. Pushback / Risks / Open Items

- **Cross-repo dependency (backend tool).** Resolved sequencing: the tool ships in this repo's
  `libs/core` first; the external backend (`/Users/leonardmarcq/Downloads/kiln_server`) consumes it
  via local editable deps + registers it as a client tool (§7). The app server is built/tested
  against a fake upstream throughout. End-to-end verification happens once the backend branch is
  wired and `uv sync`'d. Local editable deps are a dev convenience; before merging the backend
  branch, repoint `kiln-ai`/`kiln-server` back to a published Kiln git rev that includes the tool.
- **Runaway cost** (functional spec §9, accepted): only Stop + `MAX_ROUNDS=100` bound a
  browser-closed run. The architecture leaves a clean seam for a future budget cap (track usage off
  the stream in the runner, stop on threshold) — not built now.
- **`MAX_ROUNDS` semantics differ slightly from interactive.** Interactive resets the 100-round
  budget per `/api/chat` request; an auto run consumes it across the whole burst. That's the
  intended ceiling; documented so it isn't surprising.
- **Single-process assumption.** In-memory registry assumes one app-server process (true for the
  desktop app). Not designed for multi-process/horizontal scaling — matches the jobs system.

## 12. One-Phase Decision

Single `architecture.md`; no separate `/components` docs. The pieces (registry, runner, bus, UI
store, backend contract) are cohesive and fully specified here.
