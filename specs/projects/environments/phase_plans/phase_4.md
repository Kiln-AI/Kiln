---
status: complete
---

# Phase 4: Single-turn environment sessions for runs

## Overview

Today only the eval runner opens an OpenEnv episode, so a run config that reaches an environment's tools fails outside evals. This phase opens a session for every adapter run whose tools reach one environment: the run API, the Python library and Kiln task tool sub-runs all go through `BaseAdapter`, so all three get it. The session is reset with optional `env_reset_kwargs`, held for the run, and its settled record is saved on the run as `env_episode`. Setup failures become typed `EnvironmentRunError`s that the run API maps to HTTP statuses, before any model call. Multi-turn conversations (one session across turns) are phase 5; until then each multi-turn turn behaves like a single-turn run, marked with a TODO.

## Steps

1. `libs/core/kiln_ai/environments/session_manager.py`
   - Add `OpenEnvCapacityError(OpenEnvTransientError)`, raised where the manager today raises a transient error for a `capacity_reached` reply and for a session closed while answering `reset`. Eval retry behaviour is unchanged because it subclasses the transient error, and the eval-specific `_CAPACITY_HINT` stays on its message.
   - `OpenEnvRejectedError` gains `server_message: str | None` (the environment's own text), set by `_request`, so callers can show it without Kiln's prefix.

2. New `libs/core/kiln_ai/environments/run_session.py`:
   ```python
   EnvironmentRunErrorKind = Literal["reach", "not_found", "unreachable", "at_capacity",
       "reset_rejected", "session_ended", "fork_refused", "not_started_with_env",
       "kwargs_without_env"]

   class EnvironmentRunError(Exception):
       def __init__(self, kind: EnvironmentRunErrorKind, message: str): ...

   @dataclass
   class EnvRunHandle:
       context: EpisodeContext
       episode: EnvironmentEpisode | None = None   # the settled record, set on normal exit

   @asynccontextmanager
   async def environment_for_run(task, run_config_properties, reset_kwargs,
                                 session_manager=None) -> AsyncIterator[EnvRunHandle | None]
   ```
   - An active episode (`get_episode()`) yields None: sub-runs and eval jobs use the caller's episode.
   - Tool ids come from a kiln_agent run config's `tools_config`. No tools, or no project, means no environment.
   - `single_environment_id` → `reach` on `EnvironmentReachError` (its short `message`).
   - No environment: `reset_kwargs is not None` raises `kwargs_without_env`, else yield None.
   - Missing environment → `not_found` ("OpenEnv [id] wasn't found.").
   - `refresh` + `list_tools`, then `start_episode(env, reset_kwargs or {})`. `OpenEnvCapacityError` → `at_capacity`; `OpenEnvRejectedError` on reset → `reset_rejected` ("[name] rejected the reset arguments: [server message]"); any other `OpenEnvError` → `unreachable` ("Can't reach OpenEnv [name] at [url]. Check the server is running.").
   - Set the episode, yield the handle, always reset the context var. On exception `release` and re-raise; on normal exit `end_episode` and store it on the handle. If ending fails, log a warning and keep the started episode (no final state), so a finished run isn't lost.

3. `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`
   - `AdapterConfig.env_reset_kwargs: dict[str, JsonValue] | None = None`.
   - `invoke_returning_run_output` (the path `invoke` takes) wraps the existing body in `environment_for_run(...)`, outside the `KilnRunError` wrapping. After it exits, set `run.env_episode` from the handle and save the run again if it was saved (`run.path is not None`).

4. `libs/server/kiln_server/run_api.py`
   - `RunTaskRequest.env_reset_kwargs: dict[str, JsonValue] | None`, copied into `AdapterConfig`.
   - `run_task` catches `EnvironmentRunError` and raises `HTTPException` with its message, status from a kind → status table (400 reach/kwargs_without_env/reset_rejected, 404 not_found, 409 session_ended/fork_refused/not_started_with_env, 502 unreachable, 503 at_capacity).

5. Text the spec says changes: `run_context.py`'s comment and `EpisodeContext` docstring, `tool_registry.py`'s docstring and the outside-an-episode error message, which no longer say only evals open episodes.

6. Regenerate `app/web_ui/src/lib/api_schema.d.ts` for the new request field.

## Tests

- `libs/core/kiln_ai/environments/test_run_session.py` (new), against the in-process test environment server:
  - no tools / tools reaching no environment: yields None, starts nothing
  - kwargs with no environment → `kwargs_without_env`
  - two environments → `reach` with the short message
  - missing environment → `not_found`
  - start, set, end: tools resolve inside, `final_state` recorded, context var cleared, no sessions left
  - exception inside releases the session and re-raises
  - an already-active episode yields None and opens nothing
  - unreachable server → `unreachable`; capacity → `at_capacity`; reset rejected → `reset_rejected` with the server's message
  - failed `end_episode` keeps the episode without final state
- Adapter integration (same file): a real `LiteLlmAdapter` with the model call stubbed calls an environment tool; the saved run carries `env_episode` with final state and reset kwargs, re-read from disk; an unsaved run still gets `env_episode`; a reach error surfaces as `EnvironmentRunError`, not `KilnRunError`.
- `libs/core/kiln_ai/environments/test_session_manager.py`: capacity raises `OpenEnvCapacityError`; a rejection carries `server_message`.
- `libs/server/kiln_server/test_run_api.py`: `env_reset_kwargs` reaches `AdapterConfig`; each error kind maps to its status and message (parametrized).
