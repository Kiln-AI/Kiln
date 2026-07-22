---
status: complete
---

# Functional Spec: Assistant Autonomy Lifecycle

## Context: current behavior (verified on `leonard/assistant-subagents` heads)

- Auto mode is a per-conversation `auto_flag` on the desktop runtime's `ConversationRecord`. It already survives burst/task completion (idle auto conversations keep the flag on) and engine errors. It clears on: user Stop, user disable via `/auto`, and **the model calling `disable_auto_mode`** — a terminal interception that clears the flag, swaps the record back to interactive, and cascade-stops sub-agent children. The tool's description says to call it only when the user asks, but nothing enforces that; models call it on their own judgment (e.g. "task done"), which is the behavior this project removes.
- Upstream (kiln_server), `auto_mode` is a per-request bool used only to phrase the max-rounds reminder. It is never persisted; compaction infers "an autonomous run followed" by pattern-matching the trace for `enable_auto_mode` calls.
- Sub-agent spawning is orthogonal to auto mode. The designed first-spawn consent (park + `SubagentConsentBox`, `spawn_consent_granted` memory) is **inert in production**: no upstream code stamps `requires_approval` on `spawn_subagent` (kiln_server has no precondition for it; the tool definitions carry no metadata; the desktop has no name-based fallback — only tests inject it). Interactive spawns therefore run without any consent today.

## FR1: Auto mode turns off only by user action

**Behavior.** Once auto mode is on, it stays on — across bursts, task completions, and errors — until the user turns it off (Stop button / `POST /{sid}/auto {enabled:false}`). The model has no off-switch.

**Changes.**
- kiln_server removes `disable_auto_mode` from the chat toolset unconditionally (all agents, all modes). `enable_auto_mode` stays. Unconditional removal keeps the tool list — and therefore the LLM prompt cache — stable.
- The desktop deletes its `disable_auto_mode` interceptions (interactive and terminal branches), except for a **stale-call backstop**: if a `disable_auto_mode` call still arrives (old server during rollout, or a pre-upgrade conversation resuming with the call pending), resolve it as a refusal tool result — e.g. `{"status": "not_available", "message": "Auto mode can only be turned off by the user (Stop button)."}` — **without** clearing the flag and **without** stopping children. The rehydration path that resolves pending signal siblings treats stale pending `disable_auto_mode` calls the same way.

**Edge cases.**
- Historical traces containing `disable_auto_mode` calls/results must still load, render, and resume (message conversion and compaction tolerate the tool name; they already treat unknown tools generically).
- A user typing "stop auto mode" in chat can no longer be honored by the model. Accepted: the model should direct the user to the Stop button (the refusal payload doubles as that instruction if a model attempts the call). No replacement chat-based off-switch in this project.
- Cascade-stop of sub-agents continues to ride user-initiated stops exactly as today.

## FR2: Sub-agent spawning requires auto mode

**Behavior.** `spawn_subagent` only executes while the conversation's auto mode is on. Enforcement lives in the **desktop runtime** at call time. The server toolset does not vary by mode (orchestration tools stay wired whenever the agent is spawn-capable and the client supports sub-agents), so the prompt cache is unaffected by mode toggles.

**Interactive spawn → soft-upgrade.** When `spawn_subagent` arrives and `auto_flag` is off, the desktop intercepts it and surfaces the existing auto-mode consent flow (same machinery as a model-requested `enable_auto_mode`), with the spawn call in the gating role:

- **Accept** → auto mode turns on for the conversation (normal enable path: policy/kind swap, state event with `auto_flag: true`), the spawn executes, and the burst continues autonomously. Sibling tool calls in the same batch resolve as they would under the enable-consent flow today.
- **Decline** → the spawn call (and any sibling spawn calls in the batch) resolves as `{"status": "declined"}`; auto mode stays off; the turn continues interactively. The model is expected to proceed without sub-agents (its tool description says declines are possible).

The auto-mode consent dialog is reused as-is (its copy already covers sub-agents); the only addition is the spawn-triggered variant showing which spawn prompted it.

**Non-spawn orchestration tools** (`get_subagent_status`, `wait_for_subagents`, `stop_subagent`) are not gated: they only observe/stop already-running children and must keep working after auto mode is later turned off.

**Edge cases.**
- Spawns during an auto burst: unchanged (execute immediately, auto-approved).
- Sub-agents still cannot spawn (depth guard unchanged).
- Auto mode turned off (user Stop without cascade never exists — Stop cascades; user `/auto` disable while idle) with children running: existing semantics unchanged by this project.
- The `spawn_subagent` tool description (kiln_server) is updated to state the new contract: spawning requires auto mode; if auto mode is off the user is asked to enable it and may decline.

## FR3: One consent surface

**Behavior.** Auto-mode consent is the single consent covering autonomous work including sub-agents. The separate first-spawn consent is deleted (it is inert in production anyway — see Context).

**Changes.**
- Desktop: delete `spawn_consent_granted` from `ConversationRecord`, the executed-spawn consent marking, and the `_effective_requires_approval` spawn downgrade.
- Browser: delete `SubagentConsentBox` and its wiring in the transcript; `spawn_subagent` never appears as an approval item (in auto mode it auto-runs; interactively it rides the consent flow of FR2, which uses the auto-mode consent dialog, not the approval box).
- The auto-mode consent dialog copy stays the authoritative disclosure that sub-agents may be spawned.

## FR4: Auto mode is persisted per turn (server)

**Behavior.** kiln_server stamps each persisted turn with whether it ran in auto mode, giving the server durable ground truth about its own autonomous history.

**Changes.**
- `ChatSnapshot` (or its per-turn metadata) gains an optional `auto_mode: bool` recorded from the request that produced the turn. Sub-agent sessions record `true` (their loop always rides `auto_mode: true`).
- Compaction's `_autonomous_run_followed` reads the persisted field. Legacy snapshots without the field fall back to the current `enable_auto_mode` trace-shape heuristic (which remains correct for pre-upgrade traces, since those could still contain `disable_auto_mode` markers).
- No wire/API changes: requests already carry `auto_mode`; the field is server-internal.

**Edge cases.**
- Mixed histories (legacy turns without the field followed by stamped turns): the newest relevant turn's field wins; heuristic only for stretches with no stamped turns.
- The reminder-phrasing use of `auto_mode` is unchanged.

## FR5: Browser shows connection loss, not fake auto-off

**Behavior.** When the observer SSE drops while auto mode is on, the browser keeps showing auto mode as on and indicates a degraded/reconnecting connection instead of flipping to the "off" look. Real off-transitions still come only from `conversation-state` events with `auto_flag: false`.

**Changes.**
- Remove the `applyOffTransition(null)` call in the observer's `onerror` path; surface the existing `connection` state ("closed"/reconnecting) in the chat UI instead (small indicator/banner near the auto-mode footer).
- A queued message is no longer dropped on connection error (today it dies via `onAutoModeOff`); it is dropped only on a real off-transition or when the user clears it.

**Edge cases.**
- On re-attach, the conversation-state replay/marker reconciles the true `auto_flag` (existing behavior); if the run went off while disconnected, the off-transition renders then, with its real reason.
- The desktop-side run is unaffected by observer connection loss (it already keeps running).

## Compatibility & rollout

- **Old desktop + new server:** model never sees `disable_auto_mode` (removed from toolset) — old interception is dead code, harmless. Spawning stays ungated for old desktops (same as today's production behavior, given the inert consent); acceptable.
- **New desktop + old server:** `disable_auto_mode` may still be offered — the desktop backstop refuses it without side effects. Spawn gating works regardless of server version (desktop-enforced).
- No client/server version gates are added; no wire contract changes.

## Out of scope

- Server-side approval enforcement/audit (verdict tracking); deny stays desktop-enforced.
- `AgentPolicy` per-endpoint annotations unchanged.
- Real spawn rate limiting (25/day backstop stays).
- Any chat-based mechanism for turning auto mode off.
