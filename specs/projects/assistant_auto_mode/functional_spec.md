---
status: complete
---

# Functional Spec: Assistant Auto-Mode

## 1. Summary

Auto-mode lets the Kiln assistant run a **burst of unattended agentic work** for a single chat
conversation: it auto-approves and executes tool calls (Kiln API calls, kicking off background
jobs, etc.) without pausing for the user, and the work continues **server-side even if the user
closes the browser**. Auto-mode turns itself off as soon as the assistant stops to ask the user
something or decides it is done. The user can stop it manually at any time.

Auto-mode is a per-conversation, in-memory, server-side state. It is never persisted to disk.

## 2. System Context (how chat works today)

Three layers are involved. Auto-mode is implemented in the **app server**; the external backend
gets one small addition (a tool).

```
Browser ──/api/chat (SSE)──► App server ──/v1/chat/ (SSE)──► External "Kiln Copilot" backend
(web_ui)                     (studio_server/chat)            (kiln_server, owns the model + agent)
```

- The **external backend** runs its own agent loop (≤25 rounds per call), auto-executing its
  *own* server tools (`skill`, `model_info`, …). It **hands control back to the app server** only
  when (a) the model wants a **client-visible tool** — today that is `call_kiln_api` — or (b) the
  model emits a plain-text turn with no tool calls (it is asking the user a question or is done).
  Each handoff persists a conversation **snapshot** and emits a `kiln_chat_trace` SSE event with a
  new `trace_id`.
- The **app server** executes client-visible tools (e.g. `call_kiln_api` via `KilnApiCallTool`),
  enforces per-tool **approval** (some tools have `requires_approval=true`), and runs the
  multi-round continuation loop (`ChatStreamSession.stream()`, backstop `MAX_TOOL_ROUNDS=100`).
  **Today this loop lives inside the browser's `/api/chat` HTTP request and dies when the browser
  disconnects.**
- The **browser** drives the loop: it streams `/api/chat`, renders SSE, shows approval UI for
  pending tools, and continues via `/api/chat/execute-tools`. State is browser sessionStorage;
  history/continuation use `trace_id`.

**The core change:** when auto-mode is on, the app server's continuation loop is lifted out of the
browser's request into a **server-owned, in-memory runner** that auto-approves every tool call and
keeps looping with the browser as an optional observer.

## 3. Terminology

- **Conversation / session** — one chat thread. Identified to the user by its latest persisted
  snapshot. Continuation advances the `trace_id` each round (backend mints a new id per snapshot).
- **Runner** — the in-memory, app-server-owned object that drives the auto-mode loop for one
  conversation, decoupled from any HTTP request. Analogous to a supervised task in the background
  job system, but bespoke to chat streaming.
- **Auto run** — one burst of unattended work: from the moment auto-mode turns on until it turns
  off (assistant asks/done, user stop, error, or backstop).
- **`enable_auto_mode`** — a new tool the external backend exposes to the model; the app server
  intercepts the call and prompts the user for consent.

## 4. Core Behaviors

### 4.1 Triggering auto-mode

Auto-mode can be triggered two ways. **Both always prompt the user for consent** (every time —
see §4.2):

1. **Backend tool call.** The model (in the external backend) decides auto-mode would help and
   calls `enable_auto_mode`. This surfaces to the app server as a client-visible tool call. The
   app server intercepts it and, instead of executing it silently, emits a **consent-required**
   event to the browser.
2. **User UI toggle.** The user clicks an "enable auto mode" control in the chat UI. Same consent
   dialog. **Manual enable only *arms* the conversation's auto-mode flag — it does NOT fire an
   empty turn** (sending an empty message set errors at the backend with "No messages were sent").
   The indicator turns on; the **next message the user sends** starts the first auto burst (via the
   inject/`/message` path, §4.3.2). If a turn is already in flight when enabled, it simply continues
   under auto-mode.

> **Revision R1 — conversation-scoped auto-mode.** Auto-mode is no longer a single burst that
> auto-disables when the assistant pauses. Once enabled it stays on for the **whole conversation**
> until the user **explicitly** stops it (Stop button or a typed request the assistant honors via
> `disable_auto_mode`). Sending a message while a run is working **injects** the message into the
> ongoing run rather than stopping it. This revises §4.2, §4.4, §4.5, §5, and §6 below.

### 4.2 Consent

- Consent is requested when auto-mode transitions **off → on** for a conversation. Because
  auto-mode now **persists for the whole conversation** (Revision R1), this is normally **once per
  conversation** — not once per burst and not per user message. It is requested again only if the
  user has explicitly turned auto-mode off and it is later re-triggered.
- The consent prompt explains the implications: auto-mode will run tool calls **without asking for
  approval**, may **kick off costly jobs** (e.g. reflective optimization), **uses tokens / incurs
  cost**, and will **keep running on the server even if you close this window**. The user can
  **Accept** or **Decline**.
- **Accept** → auto-mode turns on for this conversation; the runner takes over (§4.3).
- **Decline** →
  - If triggered by the backend tool: the `enable_auto_mode` tool call is resolved with a
    "declined" result and the normal (manual-approval) chat flow continues.
  - If triggered by the UI toggle: nothing changes; the toggle returns to off.

### 4.3 What auto-mode does (the auto run)

Once on, for this conversation:

- The app server runs the continuation loop in a **server-owned runner**, independent of the
  browser connection.
- **Every tool call auto-executes, including tools that normally require approval.** The runner
  ignores `requires_approval` metadata while auto-mode is on. (This is the explicit point of
  auto-mode; the consent prompt covers the blanket risk.)
- Each round: receive backend handoff → if there are client-visible tool calls, execute them all,
  feed results back to the backend (`/v1/chat/` continuation with the advancing `trace_id`), and
  loop. Background jobs started via `call_kiln_api` are fire-and-forget from chat's perspective —
  the tool returns the job-creation response and the job runs in the existing background-job
  system; the assistant continues without waiting.
- The conversation snapshot/`trace_id` continues to be persisted by the backend each round, so the
  conversation is always recoverable up to the last completed round.

#### 4.3.1 Persistence across bursts (Revision R1)

- The auto-mode **flag is conversation-scoped** and persists until explicitly stopped. It is
  decoupled from any single "burst" of runner activity.
- A **burst** is one stretch of runner work. When the assistant yields a plain-text turn (a
  question for the user, or "I'm done"), the **burst ends but auto-mode stays ON**. The
  conversation simply goes **idle** (the green indicator remains shown), waiting for the user.
- When the user sends the next message while idle, a new burst starts **automatically in
  auto-mode** — **no new consent prompt** (consent was already given for this conversation).

#### 4.3.2 Sending a message while a run is working (Revision R1)

- Sending a message **does not stop** auto-mode. The message is **injected into the ongoing run**:
  it is queued and delivered to the assistant at the next round boundary (alongside the pending
  tool results), so the assistant incorporates it on its next step and keeps going. The run never
  stops on send.
- If the conversation is idle (between bursts) when the user sends, the message starts a new burst
  (per §4.3.1).

### 4.4 Disabling auto-mode

Under Revision R1, auto-mode turns **off** for the conversation **only on an explicit user
action** — never just because the assistant finished a burst or asked a question:

1. **User clicks Stop (graceful).** The **Stop** control adjacent to the auto-mode indicator does
   **not** hard-cancel / cut off the in-flight output. It lets the **current turn finish**
   streaming, then clears the conversation's auto-mode flag and returns to **normal mode**. Any
   tool calls from that final turn (and everything after) are then **subject to the normal approval
   policy** — i.e. if the final turn requested client tool calls, they are surfaced for approval
   (the existing `tool-calls-pending` flow) instead of being auto-executed. Net effect: "finish
   what you're saying, then go back to asking me." (This replaces the earlier prompt-cancel
   behavior.)
2. **User explicitly asks to stop, in chat.** When the user's message asks to stop auto-mode (e.g.
   "stop auto mode", "go back to asking me each time"), the assistant calls the **`disable_auto_mode`**
   tool, which the app server intercepts to clear the conversation's auto-mode flag and end the
   run. This is the reliable, symmetric counterpart to `enable_auto_mode`.

The following **end the current burst but do NOT disable auto-mode** (the flag stays on; the
conversation goes idle and resumes auto on the next message):

- **Assistant asks the user / is done** (plain-text handoff with no client tool calls).
- **Error.** An unrecoverable runner error (e.g. backend unreachable) ends the burst and is
  surfaced; the flag remains on so the user can retry or stop. The conversation is preserved at the
  last persisted snapshot.
- **Backstop reached.** The `MAX_TOOL_ROUNDS` (100) per-burst backstop ends the burst with a
  notice; the flag stays on.

After auto-mode is explicitly turned off, the conversation returns to normal interactive mode (and
could be re-enabled later with a fresh consent prompt).

### 4.5 Surviving disconnect + returning

- The runner is **owned by the app server**, not by the browser request. Closing the browser tab,
  navigating away, or losing the network does **not** stop the auto run.
- **Chat History merge / indicator.** When the user opens History → Chat History, conversations
  that are **actively running auto-mode** are visually distinguished (e.g. a green "working" dot;
  exact treatment in `ui_design.md`). This requires the history view to know which listed
  conversations have an active runner (§6.3).
- **Hydrate + re-attach.** When the user opens an actively-running conversation:
  1. The UI hydrates the completed history from the **latest persisted trace** (existing
     `GET /api/chat/sessions/{id}` flow).
  2. The UI **attaches to the live runner stream** for the in-progress round. On attach, the
     runner **replays the buffered events of the current in-progress turn** (those emitted since
     the last persisted snapshot) so the UI catches up with no gap, then streams live events.
  3. The "⏵⏵ auto mode on" indicator is shown, along with the Stop control.
- Multiple browsers/tabs may observe the same active runner simultaneously (pure-observer model).

### 4.6 Concurrency

- Multiple conversations may be in auto-mode at the same time, each with its own runner.
- A global concurrency cap (configurable, mirroring the jobs registry's
  `KILN_JOBS_MAX_CONCURRENT` style) bounds simultaneous runners; excess requests are rejected with
  a clear error (auto-mode is interactive-initiated, so queueing is not expected — reject rather
  than silently queue). Default cap TBD in architecture (suggest a small number, e.g. 5).

### 4.7 App-server restart

- Runners are **in-memory only**. On app-server restart or crash, all active auto runs are lost
  and auto-mode is off everywhere.
- Conversations remain recoverable from the last persisted backend trace (up to the last completed
  round). There is **no auto-resume**. If the user returns after a restart, the conversation loads
  normally (no green dot, no live stream) and they may continue or re-trigger auto-mode.

## 5. The `enable_auto_mode` tool (backend addition)

- A new tool exposed to the model by the external backend, registered as a **client-visible** tool
  (like `call_kiln_api`) so control returns to the app server when it is called.
- **Schema:** minimal — optional `reason` / `summary` string the model provides to explain *why*
  it is suggesting auto-mode (shown in the consent prompt to give the user context). No other
  parameters required.
- **System-prompt guidance:** the backend's assistant instructions are updated to describe when to
  suggest auto-mode (e.g. "when the user has approved a multi-step plan whose steps are
  tool/job-driven and can run unattended") and that it must not assume auto-mode is granted — the
  user may decline, in which case it should proceed interactively.
- The app server **never silently executes** `enable_auto_mode`; it always routes it through the
  consent flow. The tool's result returned to the backend is `enabled` or `declined`.

### 5.1 The `disable_auto_mode` tool (Revision R1)

- A second client-visible backend tool, symmetric with `enable_auto_mode`, the model calls **when
  the user asks to stop auto-mode** (e.g. "stop auto mode", "stop doing this automatically", "ask
  me before each step again").
- **Schema:** minimal (no required params; an optional `reason` is fine).
- The app server **intercepts** it (never executes it as a normal tool): it clears the
  conversation's auto-mode flag, ends the run, and resolves the tool result so the backend
  continues interactively. No consent prompt (turning *off* is always allowed).
- **System-prompt guidance:** instruct the model to call `disable_auto_mode` (alone) when the user
  signals they want auto-mode to stop, then continue interactively.

## 6. API & Contracts (app server)

New/changed app-server endpoints. Exact shapes finalized in architecture; this fixes the contract
intent. All live under the chat API.

### 6.1 SSE event additions (on the `/api/chat` stream)

- `auto-mode-consent-required` — emitted when an `enable_auto_mode` tool call is intercepted.
  Payload: `{ reason?: string, tool_call_id: string }`. The stream pauses awaiting the user's
  decision (analogous to the existing `tool-calls-pending` pattern).
- `auto-mode-on` / `auto-mode-off` — state-change markers so any connected observer updates the
  indicator. Under Revision R1 these track the **conversation-scoped flag**, so `auto-mode-off` is
  emitted **only** on explicit disable: `reason` ∈ (`user_stopped` | `user_disabled`). Burst-level
  endings that do **not** clear the flag are signalled separately:
- `auto-mode-idle` — a burst ended (assistant asked/done, error, or backstop) but auto-mode is
  **still on**; the conversation is idle awaiting the user. Carries a `reason`
  (`asked_user` | `done` | `error` | `max_rounds`). The indicator stays shown (idle styling
  optional).

### 6.2 Control endpoints

- `POST /api/chat/auto/enable` — called after the user accepts consent. Body identifies the
  conversation (current `trace_id`) and, for the backend-tool path, the `tool_call_id` of the
  intercepted `enable_auto_mode`. The app server resolves that tool call as `enabled`, creates the
  runner, and begins the auto run. Returns a handle for observing the run.
- `POST /api/chat/auto/decline` — user declined a backend-tool-triggered consent. Resolves the
  tool call as `declined` and resumes the normal stream. (UI-toggle decline needs no server call.)
- `POST /api/chat/auto/{run}/stop` — user-initiated stop (Stop button). Disables the conversation's
  auto-mode flag and cancels any in-flight burst. Idempotent; returns 202.
- `POST /api/chat/auto/{run}/message` (Revision R1) — send a user message into an auto-mode
  conversation **without disabling it**. If a burst is active, the message is **queued** and
  injected at the next round boundary; if idle, it **starts a new burst** in auto-mode. Returns
  promptly; the resulting events arrive on the run's observer stream (§6.3). The browser uses this
  (not `/api/chat`) to send while auto-mode is on. `disable_auto_mode` is handled via interception
  of the backend tool (no dedicated endpoint needed), the same way `enable_auto_mode` is.

### 6.3 Observation endpoints

- **Active-state is joined server-side, not correlated in the browser.** The runner registry
  maintains a reverse index `leaf_trace_id → runner`, updated each time the backend emits
  `kiln_chat_trace` (the app server reads that stream, so it learns each new leaf id at persist
  time; it accumulates the whole chain, not just the latest leaf). The existing
  `GET /api/chat/sessions` proxy is **enriched** so each row carries `auto_active: bool`, computed
  against the registry in one place. The browser just renders the flag — it never correlates two
  moving lists. Opening a row resolves the runner via the same reverse index to attach the live
  stream (§6.3).
  - *Residual race:* a `GET /sessions` landing in the sub-millisecond window between the backend
    writing leaf N+1 and the runner consuming its `kiln_chat_trace` event; self-heals on the next
    poll/SSE tick. Negligible for a status dot.
  - *Optional bulletproof upgrade (nice-to-have):* since the backend is already being modified for
    `enable_auto_mode`, add a stable `conversation_id` (the root snapshot id, propagated forward
    along the `previous_snapshot_id` chain) to `ChatSnapshot`, `ChatSessionListItem`, and the
    `kiln_chat_trace` event, then correlate on that never-changing id for a zero-race join.
- `GET /api/chat/auto/{run}/events` (or equivalent per-conversation SSE) — pure-observer live
  stream for re-attach. On connect: replays buffered current-turn events, then streams live chat
  SSE events. Client disconnect only unsubscribes; it never stops the runner. (Modeled on the jobs
  system's `/api/jobs/events` observer pattern.)

### 6.4 Reused existing contracts

- `GET /api/chat/sessions`, `GET /api/chat/sessions/{id}`, hydration via `task_run.trace`, and
  `trace_id` continuation are unchanged and reused for history listing and hydration.

## 7. Edge Cases & Error Handling

- **User declines consent** → §4.2. Backend tool resolved `declined`; normal flow.
- **Browser disconnects mid-run** → runner keeps going; on return, re-attach (§4.5).
- **User opens a *non-active* conversation** → normal hydration, no live stream, no green dot.
- **Stop pressed mid-tool-batch** → the runner cancels cooperatively. In-flight tool HTTP calls
  may complete or be abandoned; because tools are idempotent-ish API calls and jobs are tracked
  independently, a partially-applied batch is acceptable. Auto-mode marked off; conversation kept
  at the last persisted snapshot. (A tool already mid-flight that started a background job: the job
  continues in the jobs system independently — stopping auto-mode does not cancel started jobs.)
- **Tool call errors during a run** → the error result is fed back to the backend (existing
  behavior) and the assistant decides how to proceed; the run continues. The run only ends on an
  *unrecoverable runner* error (§4.4.3).
- **Backend unreachable / 5xx during continuation** → run ends with `error`; surfaced to any
  observer; conversation preserved at last snapshot.
- **Two triggers race** (backend tool + user toggle near-simultaneously) → first consent that
  resolves wins; the other is a no-op (already on).
- **Concurrency cap exceeded** → enable request rejected with a clear error message.
- **Re-attach gap** → handled by current-turn event buffering (§4.5.2); if buffer is unavailable,
  the UI falls back to showing the hydrated history and a "working…" state until the next snapshot.
- **App-server restart mid-run** → §4.7 (lost, conversation preserved, no auto-resume).

## 8. UI Surfaces (functional level; details in `ui_design.md`)

- **Consent dialog** — explains implications (no approvals, costly jobs, token cost, keeps running
  after close); Accept / Decline; shows the model's `reason` when present.
- **Auto-mode indicator** — "⏵⏵ auto mode on" under the message input, in green, visible whenever
  the active conversation has a running auto run.
- **Stop control** — a "Stop auto-mode" action available while a run is active.
- **History list treatment** — green "working" dot (or a separate grouping) on conversations with
  an active runner; clicking hydrates + re-attaches.
- **UI toggle** — an "enable auto mode" affordance in the chat input area (off by default).

## 9. Constraints, Safety & Limits

- **No automatic cost/round/time cap** beyond: the user **Stop** control, the existing
  `MAX_TOOL_ROUNDS=100` app-server backstop, and the backend's internal 25-round-per-call limit.
  **Noted concern (pushback):** because the app server re-invokes the backend each round, the
  backend's 25-round limit resets per continuation, so the only real ceiling is `MAX_TOOL_ROUNDS`.
  A long-lived auto run with the browser closed could therefore consume up to ~100 rounds of
  tokens/jobs before stopping on its own. Recommend keeping `MAX_TOOL_ROUNDS` as the hard backstop
  and treating a cost/round budget as a fast-follow if this proves risky in practice.
- **In-memory only** — no on-disk persistence of auto-mode state (matches the jobs system).
- **Security/cost** — consent is the gate. Because consent is requested every time, the user is
  always aware before a burst of unattended spending begins.
- **Concurrency** — bounded global cap (§4.6).

## 10. Out of Scope (initial version)

- Auto-resume of auto runs after an app-server restart.
- Persistent (cross-restart) record of which conversations were in auto-mode.
- Cost/token budgets and wall-clock timeouts (possible fast-follow per §9).
- Selective auto-approval (e.g. auto-approve all except destructive) — initial version
  auto-approves everything while on.
- Auto-mode for anything other than the chat assistant.

## 11. Open Concerns / Pushback

1. **Runaway cost with browser closed** (§9). The "Stop button only" choice means a closed browser
   removes the human circuit-breaker until `MAX_TOOL_ROUNDS`. **Accepted by user**; revisit a
   budget cap as a possible fast-follow.
2. **`enable_auto_mode` requires a human present to consent.** If the backend suggests auto-mode
   but the browser is closed, no one can consent — so the *initial* enable always needs a connected
   browser. Only *continuation* survives disconnect. **Accepted by user**; the model's prompt
   guidance should suggest auto-mode while the user is engaged.
3. **Conversation identity vs advancing `trace_id`.** **Resolved.** There is no stable
   conversation id in the backend today (the user-facing id is the current leaf, which advances
   each round). Rather than correlate two moving lists in the browser, the **app server joins
   active-state server-side**: a `leaf_trace_id → runner` reverse index (fed by the
   `kiln_chat_trace` events the runner already consumes) enriches the proxied `GET /api/chat/sessions`
   list with `auto_active`. Residual race is sub-millisecond and self-healing. An optional stable
   `conversation_id` backend field makes it zero-race. See §6.3.
