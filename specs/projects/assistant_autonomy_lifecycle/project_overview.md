---
status: complete
---

# Assistant Autonomy Lifecycle

Now that the assistant has sub-agents, the approval flow and auto mode need a better model. Three behavioral changes plus one persistence remodel, agreed after mapping the current flow across kiln_server, the desktop `studio_server` runtime, and the browser observer.

**Cross-repo project.** Changes land in both repos, each on a new branch off `leonard/assistant-subagents`, with a PR back into that branch per repo. The full spec chain lives in this repo (Kiln — most of the work is here); `kiln_server` carries a mirror of this overview plus its own implementation plan.

## The changes

### 1. Auto mode stays on until the user turns it off

Today auto mode already survives task/burst completion (an idle auto conversation keeps `auto_flag=True`). The one non-user off-path is the model calling the `disable_auto_mode` tool — a terminal interception that clears the flag and cascade-stops sub-agents, and models call it on their own judgment when they consider a task done. Remove `disable_auto_mode` from the toolset entirely (unconditionally, so the prompt prefix stays cache-stable). Auto mode then turns off only via user actions (Stop button, `/auto` disable). Historical traces containing `disable_auto_mode` calls must still load.

### 2. Sub-agent spawning only in auto mode

Spawning is currently orthogonal to auto mode (interactive conversations can spawn after a one-time consent). Gate it on auto mode — enforced in the **desktop runtime** at call time, not by varying the server toolset per mode, because a mode-dependent toolset would invalidate the LLM prompt cache on every toggle. An interactive `spawn_subagent` call **soft-upgrades**: it surfaces the existing auto-mode consent dialog; accepting enables auto mode and lets the spawn proceed, declining resolves the spawn as declined.

### 3. Single consent surface

With spawning gated on auto mode, the separate first-spawn consent (`spawn_consent_granted` record memory, `SubagentConsentBox` in the browser, the first-spawn approval marking) is redundant — the auto-mode consent dialog already covers sub-agents. Delete it.

### 4. Persist auto mode (the remodel)

`auto_mode` today is a per-request bool the server uses only to phrase one reminder, never persisted; the server infers its own autonomous history from trace shape (`_autonomous_run_followed` in compaction pattern-matches for `enable_auto_mode` calls). Stamp the mode onto the persisted turn server-side and have compaction read the field instead. Necessary anyway: removing `disable_auto_mode` makes shape inference even less reliable (no "off" marker at all).

### 5. Browser: no fake auto-off on connection errors

The browser currently flips its UI to "auto mode off" when the observer SSE drops, even though the real flag is still on. Show a reconnecting/degraded state instead.

## Out of scope

- Server-side approval enforcement/audit (verdict tracking). Deny stays desktop-enforced.
- Moving the `AgentPolicy` per-endpoint annotations — they stay in kiln_server untouched.
- Real spawn rate-limiting (the 25/day backstop stays).
