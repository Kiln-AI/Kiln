---
status: complete
---

# Phase 5: Multi-turn environment sessions

## Overview

Phase 4 opens and settles one OpenEnv session per run. For a multi-turn task that means each turn gets a fresh environment, so the agent's history and the environment's state drift apart. This phase keeps one session open across a conversation's turns: the first turn opens it, each later turn continues it from the latest turn only, each turn saves the environment's state at its end, and the session closes after 30 idle minutes, at app exit, or when the conversation's latest turn is deleted. Every way of losing the session surfaces as a typed `EnvironmentRunError` before the model is called.

## Steps

1. `libs/core/kiln_ai/environments/session_manager.py`
   - Protocol `EnvironmentSessionManager` gains `async def read_state(self, episode) -> dict[str, JsonValue]`: send `state`, keep the session open.
   - `OpenEnvSessionManager.read_state`: under the session's lock. No live session raises `OpenEnvError`. A failure drops the session exactly as `call_tool` does (kept only on `OpenEnvRejectedError`).
   - `OpenEnvSessionManager.__init__` creates `self.conversations = ConversationSessions()`; `shutdown()` awaits `self.conversations.close_all()` before closing sessions.
   - `shared_conversation_sessions() -> ConversationSessions` returns `shared_session_manager().conversations`, so the registry has the manager's lifetime and no global of its own.

2. New `libs/core/kiln_ai/environments/conversations.py`
   ```python
   @dataclass
   class HeldSession:
       context: EpisodeContext
       turn_run_ids: set[str]
       last_used: float = 0.0

   class ConversationSessions:
       def __init__(self, clock=time.monotonic, idle_seconds=1800, reap_interval_seconds=60): ...
       def take(self, parent_run_id: str) -> HeldSession | None
       def put(self, latest_run_id: str, held: HeldSession) -> None   # stamps last_used, adds the id to turn_run_ids, starts the reaper
       def holds_turn(self, run_id: str) -> bool
       async def release_runs(self, run_ids: Iterable[str]) -> None
       async def reap(self) -> None
       async def close_all(self) -> None
   ```
   - Mutations are synchronous dict operations with no await between read and write, so no lock is needed. Releases happen after entries are removed.
   - Reaper: an `asyncio.Task` created on `put` when none is running on the current loop; loops `sleep(reap_interval)` then `reap()`, and exits when the registry is empty. `close_all` cancels it.
   - Release failures are logged, never raised.

3. `libs/core/kiln_ai/environments/run_session.py`
   - `environment_for_run(task, run_config_properties, reset_kwargs, parent_run=None, session_manager=None, conversations=None)`.
   - `EnvRunHandle.run_id: str | None`, set by the caller to the id of the run the body produced.
   - Single-turn tasks: unchanged.
   - Multi-turn, no parent: start the episode, run the turn, then `read_state` into `handle.episode.final_state` and `put(run_id, held)`.
   - Multi-turn with parent: `take(parent.id)`; if none: `holds_turn` → `fork_refused`, parent has `env_episode` → `session_ended`, else `not_started_with_env`. A held session on a different environment is put back and refused with `not_started_with_env`. `reset_kwargs` are ignored.
   - Turn raises: first turn releases. Later turns release when the error ended the environment's session (an `OpenEnvError` that `tool_call_error_ends_session`); otherwise `put(parent.id, held)` so the turn can be retried.
   - `read_state` failure: log; episode saved without final state; the session is held again only if it is still live (a rejection).
   - Remove the phase 4 TODO.

4. `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`: pass `parent_task_run` to `environment_for_run` and set `env_run.run_id = run.id` after the body.

5. `libs/server/kiln_server/run_api.py`
   - `delete_run` and `delete_runs`: after deleting, `await shared_conversation_sessions().release_runs(deleted ids)`.
   - `run_task`: when the conversation was deleted during generation and the new run is removed, release its session too.

## Tests

- `test_session_manager.py`: `read_state` returns the state and keeps the session open (a later tool call works); a dropped connection raises and removes the session; a rejected `state` keeps it; no live session raises `OpenEnvError`; `shutdown` closes held conversation sessions.
- `test_conversations.py`: put/take re-keys and removes; `holds_turn` for earlier turns; `take` of an unknown id; `reap` with an injected clock releases only idle entries; `release_runs` releases matching keys only; `close_all` releases everything and cancels the reaper; the reaper runs and stops when empty; release failure is logged, not raised.
- `test_run_session.py` (multi-turn class): first turn holds the session and records state; second turn continues the same episode and ignores reset kwargs; fork from an earlier turn → `fork_refused`; parent with `env_episode` but nothing held → `session_ended`; parent without `env_episode` → `not_started_with_env`; held session on another environment → refused and put back; non-ending error puts the session back under the parent; session-ending error releases it; first-turn error releases; failed `read_state` keeps the episode without state; no `run_id` set releases. Adapter-level: three turns through the real `LiteLlmAdapter` share one episode and each saves its own state.
- `test_run_api.py`: three turns via the run API share one episode with per-turn final state (real test environment server, stubbed model); deleting the latest turn releases the session and the next turn gets 409; bulk delete releases; the multi-turn error kinds map to 409.
