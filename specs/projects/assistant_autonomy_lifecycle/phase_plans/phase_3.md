---
status: complete
---

# Phase 3: Web UI FR2/FR3/FR5 — consent spawn variant, one consent surface, observer resilience

## Overview

The browser side of the project (architecture §4, `app/web_ui` only). Two
halves:

1. **§4.1 consent dialog spawn variant (FR2/FR3).** The desktop now emits a
   generalized `auto-mode-consent-required` payload (phase 2's
   `_format_consent_required_sse`): `trigger` / `gating_tool_call_id` always,
   `enable_tool_call_id` + `reason` only for the enable trigger (legacy
   compat), `spawn` (`{agent_type, name, prompt}`) only for the spawn
   trigger. The browser parses the new fields (all optional; absent = legacy
   enable shape), branches accept/decline on the trigger — spawn-accept
   enables auto mode with the gating spawn prepended to `pending_tool_calls`
   and NO `enable_tool_call_id`; decline posts the gating id (renamed
   `gating_tool_call_id` server-side, verified in `runtime/api.py` +
   regenerated `api_schema.d.ts`) — and the auto-mode consent dialog gains a
   line naming the sub-agent about to be spawned. `SubagentConsentBox` and
   its transcript wiring are deleted: spawns never appear as approval items
   (auto-run under the auto policy, consent-flow under interactive).

2. **§4.2 observer error resilience (FR5).** The main observer's SSE
   `onerror` never fakes an auto-off: `autoModeOn`/`armed`/`offReason` stay
   untouched. Instead, when auto mode is on or a turn was in flight, a
   bounded re-attach runs (2s/5s/10s, 3 attempts, cancelled by `detach` or a
   successful open) reusing the existing `attach` + `reconnecting`
   affordances; on exhaustion an inline error surfaces and the existing
   manual paths (next send/ensure) remain the recovery. The queued message
   survives by construction (no `onAutoModeOff` fires). `chat.svelte`'s
   auto-mode footer shows a "reconnecting…" / "connection lost" hint while
   auto is on and the connection isn't open.

## Steps

1. **`src/lib/chat/streaming_chat.ts`**
   - `StreamEvent` gains the consent-generalization fields:
     `trigger?: string`, `gating_tool_call_id?: string`,
     `spawn?: { agent_type?: string; name?: string; prompt?: string } | null`.
   - New `AutoModeConsentTrigger = "enable_auto_mode" | "spawn_subagent"` and
     `SpawnConsentInfo { agentType; name; prompt }`.
   - `AutoModeConsentRequiredPayload` becomes
     `{ trigger; gatingToolCallId; reason; spawn; siblingToolCalls }` — the
     redundant `enableToolCallId` field is dropped internally (the wire
     compat lives in parsing: `gating_tool_call_id` falls back to
     `enable_tool_call_id`; absent `trigger` = enable).
   - `autoModeConsentPayloadFromEvent` maps defensively: unknown trigger →
     enable; `reason` only for enable; `spawn` parsed only for the spawn
     trigger and null on a malformed value.

2. **`src/lib/chat/conversation_store.ts`** (types + FR5)
   - `DeclineAutoModeContext.enable_tool_call_id` →
     `gating_tool_call_id` (matches the regenerated schema; the desktop route
     still accepts the legacy spelling for stale tabs, but this bundle sends
     the new one).
   - `attach()`'s `onerror`: never `applyOffTransition`. Keep flag stores
     untouched; `closeSource()`, `setWorking(false)`,
     `connection.set("closed")`; if `autoModeOn` or the drop was mid-turn
     (and a session id is in hand), `scheduleReattach(sid)`, else
     `reconnecting.set(false)`.
   - New bounded re-attach: `REATTACH_BACKOFF_MS = [2000, 5000, 10000]`,
     attempt counter + timer store-level; `scheduleReattach` sets
     `reconnecting` true and re-runs
     `attach(sid, undefined, false, get(autoModeOn))` after the backoff; on
     exhaustion resets the counter, clears `reconnecting`, and surfaces the
     existing "Lost the connection to the assistant…" inline error. The
     timer is cleared in `closeSource()` (so `detach`/manual re-attach
     cancel it); the counter resets on `onopen`, on any received message,
     and on `detach`.

3. **`src/lib/chat/chat_session_store.ts`** `handleAutoModeConsent`
   - Branch on `payload.trigger`. Accept, spawn variant: seed =
     `{ kind: "auto", session_id, pending_tool_calls: [gating spawn call
     (rebuilt from gatingToolCallId + the spawn input), ...siblings] }` — no
     `enable_tool_call_id`, no `reason`. Accept, enable variant: unchanged
     shape but keyed off `gatingToolCallId`.
   - Decline (both variants): `{ gating_tool_call_id, siblings }`.

4. **`src/routes/(app)/assistant/auto_mode_consent_dialog.svelte`** — hold
   the payload's `spawn` like `reason` is held; render a callout line naming
   the sub-agent (`spawn.name`, `spawn.agentType`) when present. Title,
   explainer copy, and button labels unchanged ("Turn on auto mode" IS the
   decision).

5. **Delete `src/routes/(app)/assistant/subagent_consent_box.svelte`** and
   its wiring in `chat_transcript.svelte` (import + the
   `toolName === "spawn_subagent"` special case in the pending-approval
   rendering — the branch collapses to the plain `ToolApprovalBox`).

6. **`src/routes/(app)/assistant/chat.svelte`** — subscribe
   `main_conversation_store.connection`; in the auto-mode footer block,
   render "reconnecting…" (with the existing spinner affordance) while
   `$autoModeOn && $autoReconnecting`, and "connection lost" while
   `$autoModeOn && $connection === "closed" && !$autoReconnecting`.

## Tests

- `streaming_chat.test.ts` — `autoModeConsentPayloadFromEvent`:
  - legacy payload (no trigger) → enable trigger, gating id falls back to
    `enable_tool_call_id`, `spawn` null.
  - spawn payload → spawn trigger, gating id, parsed `spawn`, null `reason`.
  - malformed `spawn` value (non-object) → `spawn` null, no throw.
- `chat_session_store.test.ts`:
  - existing enable accept/decline tests updated to the new payload shape;
    decline asserts `gating_tool_call_id`.
  - spawn accept → `requestEnable` seed carries the gating spawn first in
    `pending_tool_calls` plus siblings, and NO `enable_tool_call_id`/`reason`
    keys.
  - spawn decline → `decline({ gating_tool_call_id, siblings })`, no enable.
  - queued message survives an observer connection drop (only
    `onWorkingChange(false)` fires — no `onAutoModeOff`, queue intact).
- `conversation_store.test.ts`:
  - consent handoff test updated to the generalized payload; new spawn-shape
    handoff test.
  - decline body test updated to `gating_tool_call_id`.
  - observer error (auto): flag stays on, no off signal, `reconnecting`
    true, re-attach fires after 2s to the same events URL (fake timers).
  - bounded backoff: repeated failures re-attach at 2s/5s/10s then surface
    ONE inline error, `reconnecting` false, flag STILL on.
  - a successful re-attach (open + marker) resets the attempt budget.
  - `detach()` during the backoff window cancels the pending re-attach.
  - mid-turn interactive drop schedules a re-attach too; idle interactive
    drop stays silent (no timer, no error).
- `auto_mode_consent_dialog.test.ts` — payload builder updated; spawn line
  renders name + agent type for the spawn variant and is absent otherwise;
  the primary button label stays "Turn on auto mode".
