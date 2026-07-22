---
status: complete
---

# Phase 1: Desktop FR1 — model loses the auto-mode off-switch

## Overview

Auto mode must turn off only by user action (architecture §3.1, functional
spec FR1). The desktop runtime currently honors a model-initiated
`disable_auto_mode` call via two interceptions (interactive
`resolve_immediate` + auto `resolve_terminal`), a `clear_auto_flag` result
field, an `on_auto_flag_cleared` cascade hook, and a supervisor closure that
publishes the off state and cascade-stops children. This phase deletes that
whole mechanism and replaces it with a single side-effect-free stale-call
backstop: any `disable_auto_mode` call that still arrives (old server during
rollout, pre-upgrade resume) resolves as a refusal tool result — no flag
clear, no child stops, the burst/turn continues. Rehydration of pending
signal siblings resolves a stale pending `disable_auto_mode` with the same
refusal shape (enable keeps the declined shape). After this phase,
`auto_flag` clears only in `_finish_stopped`, the stop/cancel paths, and
`set_auto_flag(false)` — all user-initiated.

Scope guard: no spawn-gating, no consent generalization, no web UI — those
are phases 2 and 3. `spawn_consent_granted` and its engine marking stay
untouched (deleted in phase 2).

## Steps

1. **`chat/runtime/interceptors.py`**
   - Add the refusal constant + backstop interceptor:
     ```python
     DISABLE_AUTO_MODE_STALE_RESULT = json.dumps(
         {"status": "not_available",
          "message": "Auto mode can only be turned off by the user (Stop button)."},
         ensure_ascii=False,
     )

     def intercept_disable_auto_mode_stale(event, ctx) -> InterceptResult | None: ...
     # name != DISABLE_AUTO_MODE_TOOL_NAME → None; else
     # InterceptResult(kind="resolve", result_json=DISABLE_AUTO_MODE_STALE_RESULT)
     ```
   - Delete `intercept_disable_auto_mode_interactive` and
     `intercept_disable_auto_mode_terminal`.
   - `InterceptResult`: delete `clear_auto_flag`. `InterceptKind` shrinks to
     `Literal["resolve", "control"]` — `resolve_terminal` loses its only
     producer (spec calls out its deletion) and `resolve_immediate` loses its
     only producer too (same grep argument; nothing in phases 2–3 uses it —
     the spawn gate is `control`), so both kinds go rather than surviving as
     dead engine branches.
   - Chains: `INTERACTIVE_INTERCEPTORS = (consent, stale)` (spawn gate slots
     in between in phase 2), `AUTO_INTERCEPTORS = (enable_noop, stale)`,
     `SUBAGENT_INTERCEPTORS` unchanged.
   - Drop the now-unused `DISABLE_AUTO_MODE_RESULT` import; rewrite the
     module docstring (no more disable interception / terminal-continuation
     story; document the two remaining kinds and the FR1 backstop).

2. **`chat/stream_session.py`** — delete `DISABLE_AUTO_MODE_RESULT`
   (its only consumers were the deleted interceptors).

3. **`chat/runtime/engine.py`**
   - Delete the `resolve_terminal` and `resolve_immediate` takeover branches;
     the takeover block reduces to the `control` case.
   - Delete `_resolve_terminal` and `_resolve_immediate` methods and the now
     unused `iter_upstream_round` / `RoundState` imports.
   - Delete `EngineIO.on_auto_flag_cleared`.
   - The stale backstop needs no engine change: `kind="resolve"` rides the
     existing `_plain_resolve` / `intercepted` path (answered locally, batch
     proceeds, continuation carries the refusal).

4. **`chat/runtime/supervisor.py`**
   - Delete the `on_auto_flag_cleared` closure in `_engine_io` and its
     `EngineIO(...)` wiring.
   - `rehydrate_pending_approvals`: `preresolved_results` maps per signal
     name — `disable_auto_mode` → `DISABLE_AUTO_MODE_STALE_RESULT` (import
     from `.interceptors`), `enable_auto_mode` → the existing declined shape.
     Update the `_pending_events_from_trace_tail` docstring accordingly.

5. **`chat/runtime/models.py`** — doc-only: the interceptors-field comment
   (old scan-order example), `PendingApprovalBatch.preresolved_results`
   comment (enable→declined, disable→refusal), `interactive_policy` /
   `auto_policy` docstrings (no more inline/terminal disable stories).

6. **`chat/runtime/golden_scenarios.py` + `golden/`**
   - Rewrite scenario 5: `auto_disable_resolve` →
     `auto_disable_stale_refusal`. The model calls `disable_auto_mode` with a
     sibling `add` in the same auto-burst round; expected wire: one normal
     continuation carrying the refusal JSON + the executed sibling result
     (burst continues to the next round, then idles). Delete
     `golden/auto_disable_resolve.json`, regenerate the new fixture from the
     engine (the reference implementation since phase 3 of the runtime
     project).

7. **`chat/test_orchestration.py`** — update the stale comment on
   `test_in_burst_disable_reports_queue_for_the_swapped_parent` (references
   the deleted `resolve_terminal` path; the flag-off-parent queueing it tests
   is still reachable via user-initiated disable races).

## Tests

- `test_interceptors.py`:
  - drift guard byte-pins `DISABLE_AUTO_MODE_STALE_RESULT` (persisted in
    traces).
  - chain-order test updated to the new chains.
  - `TestDisableStale` replaces `TestDisable`: refusal resolve (kind
    `resolve`, exact result) via the interactive chain and the auto chain;
    passes other tools; result carries no flag side effects by construction
    (no `clear_auto_flag` field exists to assert).
- `test_engine.py`:
  - `test_stale_disable_mid_auto_burst_continues_burst` (rewrites
    `test_disable_auto_mode_auto_terminal_resolve`): auto burst, disable +
    sibling; never executed as a tool, refusal on stream + continuation,
    `auto_flag` stays True, burst runs the next round and settles idle.
  - `test_stale_disable_interactive_resolves_and_round_proceeds` (rewrites
    `..._resolves_inline_and_denies_sibling`): interactive turn, disable +
    approval-flagged sibling; disable resolves as refusal without taking
    over the round, the sibling parks for normal approval, flag untouched.
  - `test_stale_disable_never_clears_a_set_flag` (replaces
    `test_interactive_disable_fires_cascade_hook_only_when_flag_was_on`):
    interactive record with `auto_flag=True` (mid-flip race), disable call →
    flag stays True, no cascade machinery exists to fire.
- `test_supervisor.py`: extend `_tail_trace_with_pending_calls` with a
  pending `disable_auto_mode` call; `test_rehydrate_pending_approvals_from_
  trace_tail` asserts enable→declined and disable→refusal preresolutions;
  `test_decide_runless_batch_starts_resume_run` asserts both ride the resume
  continuation with those exact payloads.
- `test_golden_protocol.py`: unchanged harness; the renamed scenario +
  fixture pin the refusal-and-continue wire shape.
