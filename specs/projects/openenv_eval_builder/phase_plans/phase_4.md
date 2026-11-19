---
status: complete
---

# Phase 4: Core library for grounded cases

## Overview

The `libs/core` pieces the studio server (phase 5) and the builder UI (phase 6) build on. The
grounding prompt gains the rules tested on the Haiku runs. A grounded reference renders to the
markdown saved as `judge_guidance`. Golden task runs can carry reference data that a judge reads
during calibration. An eval records the OpenEnv server its cases were grounded in. The episode
lifecycle the eval runner uses (start, bind, end with the final state, release on error) moves to
one shared context manager, and the synthetic user runner uses it to drive a grounded case's every
turn in one episode. The simulated user stops accepting not-found replies in grounded cases. No
model or server is called for real in tests: the LLM is stubbed, the OpenEnv server is the
in-process fake.

## Steps

1. `libs/core/kiln_ai/eval_grounding/prompt.py`: insert the three tested paragraphs from the Haiku
   runs after the "keep testing what the specification tests" paragraph, verbatim: named things
   were made up (use one of the same kind or add it with setup; drop for no_fit only when nothing
   of that kind exists and setup can't add it), keep the scenario's situation (add it with setup),
   and try at least one other way before dropping for no_fit or rehearsal_failed.

2. New `libs/core/kiln_ai/eval_grounding/judge_guidance.py`:

   ```python
   def render_judge_guidance(reference: GroundedReference) -> str
   ```

   Headings `## Starting point`, `## Facts`, `## Expected outcome`, `## Allowed`,
   `## Must not happen`. A fact is `- <text>` then an indented line
   ``  Checked with `tool` (args JSON): result excerpt``. An empty list prints `None.`.
   Exported from `eval_grounding/__init__.py`.

3. `libs/core/kiln_ai/datamodel/task_run.py`: `TaskRun.reference: dict[str, JsonValue] | None =
   None`, described as ground truth a judge reads when the run is a golden eval item, keyed by
   reference name (same meaning as `EvalInput.reference`).

4. `libs/core/kiln_ai/datamodel/eval.py`:
   - `EvalTaskInput.from_trace`: a `TaskRun` source with `reference` set gives that as
     `reference_data`, whether or not the source is the trace. Otherwise unchanged. Update the
     `reference_data` field description.
   - `Eval.openenv_server_id: ID_TYPE | None = None`: the OpenEnv server the eval's inputs were
     grounded in; every input's `openenv_reset.openenv_server_id` names it.

5. New `libs/core/kiln_ai/openenv/episode_scope.py`:

   ```python
   @dataclass
   class EpisodeScope:
       episode: OpenEnvEpisode
       _ended: OpenEnvEpisode | None = None
       @property
       def ended(self) -> OpenEnvEpisode  # raises RuntimeError before the scope ends

   @asynccontextmanager
   async def openenv_episode_scope(
       manager: OpenEnvSessionManager,
       server: OpenEnvServer,
       reset_kwargs: dict[str, JsonValue],
       tools: dict[str, OpenEnvTool],
   ) -> AsyncIterator[EpisodeScope]
   ```

   Starts the episode, binds it with `set_episode`, yields, resets the binding, then ends the
   episode and keeps the result as `scope.ended`. On any error (including cancel) in the body it
   releases the episode and re-raises. `tools` is an addition to the architecture's signature:
   `EpisodeContext` needs the server's tools, and both callers already hold them.

6. `libs/core/kiln_ai/adapters/eval/eval_runner.py`: `_run_v2_job_in_openenv.generate` uses
   `openenv_episode_scope`; the final-state check and save stay in the runner. Drop the now-unused
   imports.

7. `libs/core/kiln_ai/synthetic_user/case.py`: `SyntheticUserCase` gains
   `openenv_reset: OpenEnvReset | None = None` and `judge_guidance: str | None = None`.

8. `libs/core/kiln_ai/synthetic_user/prompt.py`: `render_system_prompt(info, *, grounded=False)`.
   When grounded, the "accept a not-found reply" bullet is left out and the last ending bullet
   refers to "the rule above about what exists". `SyntheticUserDriver` takes `grounded: bool =
   False` and passes it through.

9. `libs/core/kiln_ai/synthetic_user/runner.py`:
   - `run_cases_batch(..., openenv_session_manager: OpenEnvSessionManager | None = None)`; the
     shared session manager when None.
   - The driver is built with `grounded=case.judge_guidance is not None`.
   - A case with `openenv_reset` is driven inside `openenv_episode_scope`: the target adapter gets
     `open_openenv_session=False`, and after the scope ends `scope.ended` is set as the leaf run's
     `openenv_episode`, before the chain is saved. A case without one is driven as today.
   - The server and its tools are resolved once per server per batch (`refresh` and `list_tools`),
     on first use, under a per-batch lock; a failure is not cached.
   - A server id that isn't in the target task's project fails the case
     (`openenv_server_not_found`). A transient OpenEnv error (`is_transient_openenv_error`) is
     retried like a transient provider error.

## Tests

- `eval_grounding/test_prompt.py`: the system prompt carries the three new rules for every answer
  style.
- `eval_grounding/test_judge_guidance.py`:
  - headings in order with starting point and list items;
  - a fact renders its text, tool, args as JSON and excerpt;
  - empty lists print "None." under their headings.
- `datamodel/test_eval_model.py` (or the existing `EvalTaskInput` tests):
  - a golden `TaskRun` with `reference` scored as itself gives that reference;
  - a `TaskRun` source with `reference` that is not the trace gives that reference, not
    `reference_answer`;
  - without `reference`, behavior unchanged (existing tests);
  - `Eval.openenv_server_id` defaults to None and round-trips through save and load.
- `datamodel/test_task_run.py` (existing file): `TaskRun.reference` defaults to None and
  round-trips.
- `openenv/test_episode_scope.py`, against the fake server:
  - the body sees the episode bound; after the scope the binding is gone, `scope.ended` has
    `final_state`, and the manager holds no sessions;
  - an error in the body releases the episode, re-raises, and unbinds;
  - `scope.ended` before the end raises.
- `adapters/eval/test_eval_runner_openenv.py`: existing tests pass through the scope.
- `synthetic_user/test_prompt.py`: grounded prompt drops the not-found bullet and keeps the
  invent-nothing bullet; the default prompt is unchanged.
- `synthetic_user/test_driver.py`: `grounded=True` reaches the rendered prompt.
- `synthetic_user/test_runner.py`, with the fake server and a saved project:
  - a case with `openenv_reset` drives every turn in one episode (the adapter stub sees the same
    bound episode each turn), the adapter gets `open_openenv_session=False`, and the leaf run
    carries the ended episode with `final_state`; no sessions are left open;
  - a case without one opens no episode and keeps the default adapter config;
  - a case with `judge_guidance` builds a grounded driver;
  - an unknown OpenEnv server id fails the case with `openenv_server_not_found`;
  - a failed drive inside the episode releases it.
- `synthetic_user/test_case.py`: the new fields default to None and validate.
