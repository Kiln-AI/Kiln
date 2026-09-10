---
status: complete
---

# Phase 2: Desktop FR2/FR3 — spawn requires auto mode, one consent surface

## Overview

Sub-agent spawning now requires auto mode (functional spec FR2), enforced in
the desktop runtime at call time, and the inert first-spawn consent machinery
is deleted (FR3) so auto-mode consent is the single consent surface. Three
moving parts (architecture §3.2–§3.4), desktop only:

1. A new `intercept_spawn_requires_auto` interceptor in the interactive chain
   (between the enable-consent interception and the stale-disable backstop):
   an interactive `spawn_subagent` with `auto_flag` off surfaces the
   auto-mode consent flow with the SPAWN call in the gating role and ends the
   turn; accept/decline resolves out-of-band.
2. The consent SSE + accept/decline routes generalize: the
   `auto-mode-consent-required` payload gains `trigger` /
   `gating_tool_call_id` / `spawn` (additive; old fields kept for the enable
   case), accept reuses `enable_auto` with `enable_tool_call_id=None` and the
   spawn prepended to `pending_tool_calls` (zero signature changes), decline
   renames its parameter to `gating_tool_call_id` (route accepts the legacy
   `enable_tool_call_id` spelling for stale browser tabs).
3. First-spawn consent deletion: `ConversationRecord.spawn_consent_granted`,
   the engine's executed-spawn consent marking (both call sites), and the
   `_effective_requires_approval` spawn downgrade all go.

Carry-over from phase 1's review: the `rehydrate_pending_approvals`
signal-only-tail comment also acknowledges a stale `disable_auto_mode`-only
tail.

Scope guard: desktop code only (`app/desktop/studio_server/chat/`); the
browser-side consent dialog work is phase 3. No kiln_server changes.

## Steps

1. **`chat/stream_session.py`** — generalize `_format_consent_required_sse`:

   ```python
   def _format_consent_required_sse(
       *,
       trigger: Literal["enable_auto_mode", "spawn_subagent"],
       gating_tool_call_id: str,
       siblings: list[ToolInputAvailableEvent],
       reason: str | None = None,
       spawn: dict[str, Any] | None = None,
   ) -> bytes: ...
   ```

   Payload: `type`, `trigger`, `gating_tool_call_id`, `sibling_tool_calls`
   always; `enable_tool_call_id` (== gating id) + `reason` only for the
   enable trigger (wire compat with legacy browser bundles); `spawn`
   (`{agent_type, name, prompt}` — the spawn call's input) only for the
   spawn trigger. The sibling list keeps its `sibling_tool_calls` wire name
   (the browser reads it today; the architecture's `pending_tool_calls`
   label refers to the accept ROUTE field the siblings feed into).

2. **`chat/runtime/interceptors.py`**
   - `intercept_enable_auto_mode_consent` calls the generalized formatter
     (`trigger="enable_auto_mode"`, `gating_tool_call_id=event.toolCallId`,
     `reason=event.input.get("reason")`).
   - New `intercept_spawn_requires_auto`: passes non-spawn events; passes
     when `ctx.record.auto_flag` is on (armed/racing enable ⇒ spawn may
     proceed); otherwise `kind="control"` with the spawn-trigger consent
     event (first spawn in the batch gates; the rest ride as siblings).
   - `INTERACTIVE_INTERCEPTORS = (consent, spawn_gate, stale)`; auto and
     subagent chains unchanged. Module docstring updated.

3. **`chat/runtime/engine.py`** (FR3 deletion)
   - Delete the executed-spawn consent marking in `run` and
     `_execute_resumed_batch`.
   - Delete `_effective_requires_approval`; both call sites use
     `tool_requires_user_approval(e)` directly (the parked/non-parked
     comment simplifies accordingly).
   - Drop the now-unused `SPAWN_SUBAGENT_TOOL_NAME` / `DENIED_TOOL_OUTPUT`
     imports; update the takeover-branch comment (control = enable consent
     OR spawn gate).

4. **`chat/runtime/models.py`**
   - Delete `ConversationRecord.spawn_consent_granted` + its comment block.
   - `interactive_policy` docstring mentions the spawn gate.
   - `build_auto_seed_body` docstring notes the spawn-consent accept shape
     (no enable id; the gating spawn's result rides `sibling_results`).

5. **`chat/runtime/supervisor.py`**
   - `enable_auto`: docstring + sibling-execution comment cover the
     spawn-consent accept entry shape (`enable_tool_call_id=None`, spawn
     first in `pending_tool_calls`; armed-only branch unreachable because
     pending is non-empty). No signature change.
   - `decline_auto`: parameter rename `enable_tool_call_id` →
     `gating_tool_call_id`; docstring generalized (gating call — enable or
     spawn — resolves `{"status": "declined"}`, siblings denied).
   - Module docstring drops the consent-memory bullet.
   - `rehydrate_pending_approvals`: extend the signal-only-tail early-return
     comment (a signal-only tail can also be a stale `disable_auto_mode`-only
     tail, not just a lost enable consent).

6. **`chat/runtime/api.py`**
   - `DeclineAutoModeContext.gating_tool_call_id` with
     `validation_alias=AliasChoices("gating_tool_call_id",
     "enable_tool_call_id")` (legacy spelling accepted); handler passes the
     renamed kwarg.
   - Field comments on `CreateConversationRequest`
     (`enable_tool_call_id`/`pending_tool_calls`) and the
     create/set-auto docstrings cover the spawn-consent accept/decline
     shapes.

7. **`chat/orchestration.py` + `chat/test_orchestration.py`** — drop the
   spawn-consent bullet/reference from the module docstrings (doc-only).

8. **`chat/runtime/golden_scenarios.py` + `golden/`** — new scenario
   `auto_spawn_consent_accept_seed`: the accept-path seed body
   (`build_auto_seed_body(trace_id=…, enable_tool_call_id=None,
   sibling_results={spawn_id: spawned-result})`) driven through the auto
   policy for one tool round; fixture captured from the engine (the
   reference implementation).

## Tests

- `test_interceptors.py`:
  - chain-order test updated to `(consent, spawn_gate, stale)`.
  - `TestEnableConsent` asserts the generalized payload (`trigger`,
    `gating_tool_call_id` == `enable_tool_call_id`, `reason`, no `spawn`).
  - New `TestSpawnRequiresAuto`: passes other tools; passes when
    `auto_flag` on; controls when off with
    `trigger="spawn_subagent"`, `gating_tool_call_id`, `spawn` payload,
    sibling collection, and no `enable_tool_call_id`/`reason` keys.
- `test_engine.py`:
  - Delete `test_spawn_consent_downgrade_skips_park`,
    `test_approved_spawn_records_consent_on_record`,
    `test_denied_spawn_does_not_record_consent`,
    `test_resume_batch_marks_spawn_consent_on_executed_spawn`.
  - `test_interactive_spawn_without_auto_emits_consent_and_ends_turn`:
    spawn + sibling batch → one spawn-trigger consent event, nothing
    executed, no continuation, turn idles, no park.
  - `test_interactive_spawn_with_auto_flag_on_proceeds`: interactive record
    with `auto_flag=True` (mid-flip race) → the spawn reaches execution
    (resolves to the ctx-less "unavailable" error in the harness).
  - `test_enable_consent_outranks_spawn_gate_in_combined_batch`: enable +
    spawn in one round → the ENABLE consent event wins, spawn rides as a
    sibling.
- `test_supervisor.py`:
  - `test_enable_auto_accepts_spawn_consent_pending_executes_spawn`:
    `enable_auto(enable_tool_call_id=None, pending_tool_calls=[spawn])`
    flips the policy and executes the spawn via `execute_tool_batch` with
    the conversation's orchestration ctx (patched batch executor asserts
    the ctx + call); the seed body carries the spawn's `role:tool` result
    and no enable row.
  - `test_decline_auto_starts_interactive_declined_continuation` renamed
    kwarg; decline covers the spawn-gating shape (spawn id declined +
    sibling denied).
  - Rehydration comment carry-over is doc-only (existing tests unchanged).
- `test_api.py`:
  - `test_decline_accepts_gating_and_legacy_spelling`: both request
    spellings resolve the gating call as declined.
  - `test_create_auto_spawn_consent_accept_executes_pending_spawn`: POST
    with `session_id` + `pending_tool_calls=[spawn]`, no
    `enable_tool_call_id` (patched batch executor) → 200, flip + seed body
    carries the spawn result.
- `test_golden_protocol.py`: unchanged harness; the new
  `auto_spawn_consent_accept_seed` fixture pins the accept seed-body wire
  shape.
