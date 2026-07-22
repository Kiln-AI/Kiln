---
status: complete
---

# Architecture: Assistant Autonomy Lifecycle

Single-doc architecture (medium project, no component docs). Two repos, one PR each, both branched off `leonard/assistant-subagents`. No wire-contract changes between the repos beyond one *additive* consent-event payload variant (§3.3) consumed only by the bundled web UI — no version gating.

Repo roots: `kiln_server` = `/Users/leonardmarcq/dev/kiln_ws_2/kiln_server`, `Kiln` = `/Users/leonardmarcq/dev/kiln_ws_2/Kiln`.

## 1. Summary of moving parts

| Concern | Layer | Files |
|---|---|---|
| Remove `disable_auto_mode` from toolset | kiln_server | `chat/config.py` |
| Spawn tool description update | kiln_server | `tools/subagent_tools.py` |
| Persist `auto_mode` per turn | kiln_server | `chat/storage/chat_snapshot.py`, `chat/stream_orchestration.py` |
| Compaction reads persisted mode | kiln_server | `chat/compaction.py`, `chat/stream_orchestration.py` |
| Delete disable interceptions + add stale backstop | Kiln desktop | `chat/runtime/interceptors.py`, `engine.py`, `supervisor.py`, `models.py` |
| Spawn-requires-auto interceptor + consent variant | Kiln desktop | `chat/runtime/interceptors.py`, `engine.py`, `supervisor.py`, `stream_session.py` (consent SSE builder), `runtime/api.py` (routes) |
| Delete first-spawn consent machinery | Kiln desktop + web | `runtime/models.py`, `engine.py`, `orchestration.py` docs; web `subagent_consent_box.svelte`, `chat_transcript.svelte` |
| Consent dialog spawn variant | Kiln web | `auto_mode_consent_dialog.svelte`, `chat_session_store.ts`, `streaming_chat.ts` |
| No fake auto-off on SSE error | Kiln web | `conversation_store.ts`, `chat.svelte` |

## 2. kiln_server changes

### 2.1 Toolset removal (FR1)

`chat/config.py`:
- `CHAT_CLIENT_VISIBLE_TOOLS` → `["call_kiln_api", "enable_auto_mode"]` (drop `disable_auto_mode`, line 76).
- Drop the `ids.append("kiln_tool::disable_auto_mode")` (line 95) and the `client_tools.update` entry (line 184); both become `enable_auto_mode` only.
- The `DisableAutoModeTool` class in `Kiln/libs/core/kiln_ai/.../disable_auto_mode_tool.py` **stays** (library-completeness contract per its docstring; the desktop backstop imports its name constant). Nothing in kiln_server references it after this change.

Historical traces: message conversion already round-trips arbitrary tool names from stored traces; no change needed. `chat/compaction.py`'s digest logic only pattern-matches `enable_auto_mode`; unaffected.

Tests: update `test_sse_filter.py` (asserts `disable_auto_mode` routes to client) and `test_config.py` tool-list expectations. Add a regression test: a stored trace containing a resolved `disable_auto_mode` call still loads and resumes.

### 2.2 Spawn/enable tool copy (FR2)

`tools/subagent_tools.py` `_SPAWN_DESCRIPTION`: replace the consent sentence ("The user may be asked to approve the first spawn…") with the new contract: *"Spawning requires auto mode. If auto mode is off, calling this asks the user to enable it; the user may decline (you'll receive status "declined") — continue without sub-agents in that case."* Keep the rest verbatim.

`enable_auto_mode_tool.py` (Kiln libs/core) description: append one sentence noting auto mode is also required for spawning sub-agents. (Ships via the kiln-ai pin bump kiln_server already does routinely; if the pin isn't bumped in this PR, the sentence rides the next bump — non-blocking.)

### 2.3 Persist auto mode (FR4)

`chat/storage/chat_snapshot.py`:

```python
class ChatSnapshot(BaseModel):
    ...
    # Whether the turn that persisted this snapshot ran in auto mode.
    # Optional so pre-feature payloads stay loadable; None = unknown (legacy).
    auto_mode: bool | None = None
```

`chat/stream_orchestration.py` `_persist_and_emit_snapshot` (~548): stamp `auto_mode=auto_mode` from the in-scope request flag (already threaded through `_chat_sse_session_inner`). Every persist during a turn stamps the same value; sub-agent sessions naturally record `True` (their loop always sends `auto_mode: true`).

### 2.4 Compaction reads the field (FR4)

`compact_trace` signature gains an explicit override:

```python
async def compact_trace(
    working_prior: list[ChatCompletionMessageParam],
    trigger: CompactionTrigger = "automatic",
    autonomous: bool | None = None,   # None = infer via legacy heuristic
) -> list[ChatCompletionMessageParam]:
```

Digest assembly (~line 612): `autonomous_followed = last_user is not None and (autonomous if autonomous is not None else _autonomous_run_followed(messages, last_user[1]))`.

Call sites in `stream_orchestration.py`:
- Automatic (line ~647, compacting the *loaded prior* trace): pass the loaded snapshot's `auto_mode` (thread it alongside where the prior trace is loaded from the snapshot).
- Manual (line ~511, mid-turn `compact_conversation` tool): pass the current request's `auto_mode` flag.

`_autonomous_run_followed` stays as the legacy fallback for `None` (pre-feature snapshots). Tests: stamped-true, stamped-false (overrides a trace that *contains* `enable_auto_mode` — field wins), and legacy-None (heuristic path) cases.

## 3. Kiln desktop runtime changes

### 3.1 Delete disable interceptions; add the stale backstop (FR1)

`chat/runtime/interceptors.py`:
- Delete `intercept_disable_auto_mode_interactive` and `intercept_disable_auto_mode_terminal`.
- Add one backstop used in **both** the interactive and auto chains:

```python
DISABLE_AUTO_MODE_STALE_RESULT = json.dumps(
    {"status": "not_available",
     "message": "Auto mode can only be turned off by the user (Stop button)."},
    ensure_ascii=False,
)

def intercept_disable_auto_mode_stale(event, ctx):
    """disable_auto_mode is no longer offered upstream; a call can still
    arrive from an old server or a pre-upgrade resume. Refuse without side
    effects: no flag clear, no child stops, burst/turn continues."""
    if event.toolName != DISABLE_AUTO_MODE_TOOL_NAME:
        return None
    return InterceptResult(kind="resolve", result_json=DISABLE_AUTO_MODE_STALE_RESULT)
```

Chains: `INTERACTIVE_INTERCEPTORS = (consent, spawn_gate §3.2, stale)`, `AUTO_INTERCEPTORS = (enable_noop, stale)`. `SUBAGENT_INTERCEPTORS` unchanged (`auto_mode_signals_noop` already no-ops disable for children).

`clear_auto_flag` teardown — with no interceptor setting it, delete the whole mechanism:
- `InterceptResult.clear_auto_flag` field.
- `engine.py` branches at ~493–530 (auto terminal disable; interactive `resolve_immediate` flag-clear + `io.on_auto_flag_cleared` await). The `resolve_terminal` intercept kind loses its only producer — **delete the kind and its engine branch too** (grep confirms no other producer).
- `EngineIO.on_auto_flag_cleared` (~198–208) and the supervisor's `on_auto_flag_cleared` closure (~1482–1498).
- `models.py` doc references to the disable interception (`~504`, `554–576`, `599`); rehydration of pending signal siblings (models.py ~554) resolves a stale pending `disable_auto_mode` with `DISABLE_AUTO_MODE_STALE_RESULT` instead of the declined shape.

After this, `auto_flag` is cleared **only** in `_finish_stopped`, the stop/cancel paths, and `set_auto_flag(false)` — all user-initiated. Golden scenarios covering model-initiated disable are rewritten to expect the refusal resolve with the burst continuing.

### 3.2 Spawn-requires-auto interceptor (FR2)

New interceptor, interactive chain only (auto chain never needs it; subagent chain is covered by the depth guard):

```python
def intercept_spawn_requires_auto(event, ctx):
    """Interactive spawn_subagent: spawning requires auto mode. Surface the
    auto-mode consent flow with the SPAWN call in the gating role and end
    the turn; accept/decline resolves out-of-band (§3.3). Sits after the
    enable_auto_mode consent interception: if the model calls enable+spawn
    together, the enable consent wins and the spawn rides as a sibling."""
    if event.toolName != SPAWN_SUBAGENT_TOOL_NAME:
        return None
    if ctx.record.auto_flag:
        return None   # armed/racing enable: flag on ⇒ spawn may proceed
    siblings = [e for e in ctx.client_events if e is not event]
    return InterceptResult(
        kind="control",
        control_bytes=format_consent_required(
            trigger="spawn_subagent",
            gating_tool_call_id=event.toolCallId,
            reason=None,
            spawn_input=event.input,     # {agent_type, name, prompt}
            siblings=siblings,
        ),
    )
```

Notes:
- Multiple spawns in one batch: the first is gating; the rest are siblings. Accept executes them all (existing sibling execution in `enable_auto`); decline denies them with the standard `DENIED_TOOL_OUTPUT` while the gating call gets `{"status": "declined"}`. *(FR2 refinement: sibling spawns get the standard denied shape, not `{"status":"declined"}` — behaviorally equivalent to the model.)*
- The interactive chain runs only under the gated policy, so no auto-burst path change.
- `get_subagent_status`/`wait_for_subagents`/`stop_subagent` are untouched (no gating).

### 3.3 Consent event + accept/decline generalization

`_format_consent_required_sse` (in `stream_session.py`, re-exported via `runtime/sse.py`) gains the generalized shape. Payload (additive, old fields kept for the enable case):

```jsonc
{
  "type": "auto-mode-consent-required",
  "trigger": "enable_auto_mode" | "spawn_subagent",   // new; absent = enable (compat)
  "enable_tool_call_id": "...",   // enable trigger only (unchanged name, wire compat)
  "gating_tool_call_id": "...",   // always set (== enable_tool_call_id for enable)
  "reason": "...",                // enable trigger only
  "spawn": {"agent_type": "...", "name": "...", "prompt": "..."},  // spawn trigger only
  "sibling_tool_calls": [...]     // siblings, unchanged shape (`pending_tool_calls` is the accept-route request field name)
}
```

Accept path — `ConversationSupervisor.enable_auto` already supports it with **zero signature changes**: the route passes `enable_tool_call_id=None` and the spawn call **prepended to `pending_tool_calls`**. `build_auto_seed_body` tolerates a `None` enable id; siblings (including the spawn) execute via `execute_tool_batch` with the conversation's orchestration ctx — the spawn actually spawns, its `{"status":"spawned",...}` result rides the seed body, and the burst continues under the auto policy. The armed-only branch is unreachable (pending is non-empty).

Decline path — `decline_auto` is reused verbatim: the route passes the spawn's id as the gating id (it resolves as `{"status": "declined"}` — exactly the spawn tool's documented decline shape) and the remaining calls as `siblings` (→ `DENIED_TOOL_OUTPUT`). Rename the parameter `enable_tool_call_id` → `gating_tool_call_id` in `decline_auto` and the route body model for honesty; the HTTP field name in the browser-facing route accepts both spellings (old browser tabs may still send `enable_tool_call_id`).

`runtime/api.py`: the enable/decline route request models add the optional new fields; handlers map them as above. No new endpoints.

### 3.4 Delete first-spawn consent machinery (FR3)

- `models.py`: delete `ConversationRecord.spawn_consent_granted` (+ its comment block ~207–212).
- `engine.py`: delete the executed-spawn consent marking (~650–658 and ~810–818) and the `_effective_requires_approval` spawn downgrade (~1017–1028; the method reduces to `tool_requires_user_approval(event)` — inline it or keep the wrapper, coder's choice by local idiom).
- `orchestration.py`: update the module docstring (consent memory reference).
- Tests `test_spawn_consent_downgrade_skips_park` / `test_approved_spawn_records_consent_on_record` are replaced by §5 tests.

## 4. Kiln web UI changes

### 4.1 Consent dialog spawn variant (FR2/FR3)

- `streaming_chat.ts`: extend `AutoModeConsentRequiredPayload` with `trigger?`, `gating_tool_call_id?`, `spawn?` (all optional; absent = legacy enable shape).
- `chat_session_store.ts` `handleAutoModeConsent` (~646–714): branch on `trigger`. Spawn variant: dialog copy = the auto-mode consent explainer plus a line naming the sub-agent about to be spawned (`spawn.name`, `spawn.agent_type`). Accept → `requestEnable({kind:"auto", session_id, pending_tool_calls: [gating spawn + siblings]})` (no `enable_tool_call_id`). Decline → `conversationStore.decline({gating_tool_call_id, siblings})`.
- `auto_mode_consent_dialog.svelte`: optional `spawn` prop rendering the extra line; button labels unchanged ("Turn on auto mode" framing — that *is* the decision).
- Delete `subagent_consent_box.svelte` and its wiring in `chat_transcript.svelte` (~301–319); the `spawn_subagent` special-case in the pending-approval rendering goes away entirely (spawns never appear as approval items: auto-run under auto policy, consent-flow under interactive).

### 4.2 No fake auto-off on observer error (FR5)

`conversation_store.ts` `source.onerror` (~1410–1441): unify the two branches —

- Never call `applyOffTransition`. Keep `autoModeOn`/`armed`/`offReason` untouched.
- `closeSource()`; `setWorking(false)`; `connection.set("closed")`.
- If auto mode is on **or** a turn was in flight: `reconnecting.set(true)` and schedule a bounded re-attach — `attach(sessionId, {assumeAutoOn: currentFlag})` retried at 2s/5s/10s (3 attempts, timer cleared by `detach`/successful `onopen`). On exhaustion: `reconnecting.set(false)` + `sink.onInlineError("Lost the connection to the assistant…")` with the existing manual paths (next send/ensure re-attaches) as recovery.
- Queued message: no `onAutoModeOff` fires, so the queue survives by construction (FR5); on successful re-attach the existing idle-marker flush ("BUG 2 fix" paths) delivers it.

`chat.svelte`: the auto-mode footer (~720–739) additionally renders a small "reconnecting…" / "connection lost" hint when `autoModeOn && $connection !== "open"` — reusing the existing `autoReconnecting` display pattern (~52–56).

Re-attach correctness: `attach` already replays + reconciles via the on-subscribe `conversation-state` marker; if the run actually went off while disconnected, the marker delivers the real off-transition with its true reason.

## 5. Error handling

- Stale `disable_auto_mode` (any source) → refusal resolve; never mutates flag/children. Logged at info via existing `chat_debug_log` round events (no new log plumbing).
- Spawn consent while a spawn cap/depth condition also applies: interception order runs the consent first; cap errors surface later as tool-result errors when the spawn executes on accept — same as an auto-burst spawn today.
- `enable_auto` failure modes on accept (404 record died, 429 cap, 409 busy) already map in the route; the browser dialog's existing error toast covers them (no new UI).
- FR5 re-attach failures degrade to today's manual-recovery behavior; nothing new is fatal.

## 6. Testing strategy

**kiln_server (pytest):** config toolset assertions; snapshot round-trip with `auto_mode` set/absent; `_persist_and_emit_snapshot` stamping for interactive/auto/subagent requests; `compact_trace` autonomous override (true/false/None×heuristic); legacy-trace-with-disable load/resume regression.

**Kiln desktop (pytest):** interceptor unit tests (stale refusal in both chains — no flag clear, burst continues; spawn gate passes when `auto_flag` on, controls when off, sibling collection; enable-consent outranks spawn gate in a combined batch). Engine tests: batch with gated spawn ends turn without park; stale disable mid-auto-burst continues the burst. Supervisor tests: accept path via `enable_auto(enable_tool_call_id=None, pending=[spawn])` flips policy and executes the spawn (fake orchestration ctx); decline path resolves spawn declined + siblings denied. Rehydration: pending stale disable resolves with the refusal shape. Golden scenarios: update/remove the model-initiated disable scenarios; add a spawn-consent-accept golden covering the seed-body wire shape.

**Kiln web (vitest):** `handleAutoModeConsent` spawn-trigger branch (accept/decline payloads); `conversation_store` onerror keeps `autoModeOn` and schedules re-attach; queued message survives an error/re-attach cycle; consent payload parsing with and without the new fields.

Per repo conventions: run each repo's lint/format/typecheck/test tooling before wrap-up.

## 7. Rollout / compatibility recap

- Old desktop + new server: never sees `disable_auto_mode`; spawns stay ungated for it (today's production behavior). Acceptable.
- New desktop + old server: stale backstop covers `disable_auto_mode`; spawn gating is desktop-local. Consent-event variant is desktop→browser only (bundled together), so no skew there.
- Old browser tab + new desktop (stale bundle after upgrade): decline route accepts the legacy `enable_tool_call_id` spelling; legacy consent payloads (no `trigger`) behave as enable — unchanged.
