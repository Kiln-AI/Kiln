---
status: complete
---

# Phase 5: `code_eval` (Beta)

## Overview

This phase adds the `code_eval` V2 eval type, which runs user-authored Python scorer functions in a `multiprocessing` spawn-based worker process. It is the last unregistered type in `_V2_ADAPTER_MAP`.

The deliverables:

1. **`sandbox_worker.py`** -- a module containing the multiprocessing worker function (`_execute_scorer`) and the spawn/timeout/kill orchestrator (`run_scorer`). Runs user code in a child process with wall-clock timeout.
2. **`KilnEvalHelpers`** -- a pure-Python helper class injected as the `kiln` argument to the user's scorer, providing utility methods.
3. **`CodeEvalAdapter`** -- a `BaseV2Eval` subclass that validates trust, spawns the worker via `run_scorer`, validates returned scores, and returns the standard `(EvalScores, SkippedReason | None, str | None)` tuple.
4. **Trust gate** -- an ephemeral per-project in-memory store. Until the user grants trust for a project, `code_eval` configs return `code_eval_not_trusted` skip tuples.
5. **Trust gate API endpoint** -- a FastAPI POST endpoint in `eval_api.py` to grant trust.
6. **`CodeEvalProperties.timeout_seconds`** -- add the missing timeout field to the data model.
7. **Multiprocessing bootstrap** -- `freeze_support()` and `set_start_method("spawn")` in the desktop entry points.
8. **Tests** -- comprehensive pytest coverage for all new code.

### What this phase does NOT include

- OS-level sandboxing (seccomp, AppArmor, macOS sandbox-exec). The trust gate is the only protection. Network and filesystem access are unrestricted within the child process.
- `setrlimit` memory/CPU caps. Originally spec'd as P2; cut from this phase to reduce complexity. Can be added later as an enhancement to `sandbox_worker.py` without API changes.
- UI for creating/editing code evals or the trust-grant dialog (Phase 6).
- Cold-start spike on PyInstaller bundle -- document as a follow-up validation item; the implementation itself is straightforward and does not depend on spike results.

## Design Decisions

### BaseV2Eval async evaluate contract

`CodeEvalAdapter` subclasses `BaseV2Eval` and implements `async evaluate(self, eval_input: EvalTaskInput) -> tuple[EvalScores, SkippedReason | None, str | None]`. This is the same contract used by all 7 existing V2 adapters (see `base_v2_eval.py` lines 31-41). The adapter uses `asyncio.get_event_loop().run_in_executor(None, run_scorer, ...)` to run the blocking multiprocessing orchestration without blocking the event loop.

### Trust gate integration

The trust gate is checked inside `CodeEvalAdapter.evaluate()`. When trust is not granted, the adapter returns `({}, SkippedReason.code_eval_not_trusted, "Code eval not trusted for project '<project_name>'. Grant trust before running.")`. This is consistent with how the eval runner unpacks the evaluate return value at `eval_runner.py` line 425 -- it expects the 3-tuple and creates the `EvalRun` accordingly. No exception is raised; no runner-level catch is needed.

### freeze_support / spawn wiring

`multiprocessing.freeze_support()` must be the very first call in `if __name__ == "__main__":` blocks for PyInstaller compatibility. `multiprocessing.set_start_method("spawn", force=True)` is called immediately after on all platforms (spawn is already the default on macOS/Windows, but must be explicit on Linux where fork is default and unsafe with threads). Both calls go in:
- `app/desktop/desktop.py` line 183 (before sentry init)
- `app/desktop/dev_server.py` line 22 (before `setup_resource_limits()`)

### Serialized spawns

A module-level `threading.Lock` in `sandbox_worker.py` serializes `multiprocessing.Process` creation. This avoids a known thread-safety issue on Linux with PyInstaller where concurrent `Process()` calls can deadlock. The lock is acquired before `Process()` and released after `p.start()`. The actual execution (blocking on `p.join()`) happens outside the lock.

## Steps

### Step 1: Add `timeout_seconds` to `CodeEvalProperties`

**File: `libs/core/kiln_ai/datamodel/eval.py`**

The current `CodeEvalProperties` (line 191) only has `type` and `code`. Add a `timeout_seconds` field:

```python
class CodeEvalProperties(BaseModel):
    type: Literal[V2EvalType.code_eval] = V2EvalType.code_eval
    code: str
    timeout_seconds: int = Field(default=30, ge=1, le=300)
```

This is the wall-clock timeout for the child process. Default 30s, min 1s, max 5 minutes.

### Step 2: Create `KilnEvalHelpers`

**New file: `libs/core/kiln_ai/adapters/eval/eval_utils/kiln_eval_helpers.py`**

A pure-Python helper class that the user's scorer receives as the `kiln` argument. It provides convenience methods without exposing internal Kiln APIs.

```python
from typing import Any
from pydantic import JsonValue


class KilnEvalHelpers:
    """Helper object passed as the `kiln` argument to user scorer functions.

    Provides utility methods for common scoring patterns.
    """

    def __init__(
        self,
        reference_data: dict[str, JsonValue] | None,
        task_input: str | None,
        trace: list[dict[str, Any]] | None,
    ):
        self._reference_data = reference_data
        self._task_input = task_input
        self._trace = trace

    @property
    def reference_data(self) -> dict[str, JsonValue] | None:
        return self._reference_data

    @property
    def task_input(self) -> str | None:
        return self._task_input

    @property
    def trace(self) -> list[dict[str, Any]] | None:
        return self._trace

    def ref(self, key: str, default: Any = None) -> Any:
        """Shorthand to look up a reference_data key with an optional default."""
        if self._reference_data is None:
            return default
        return self._reference_data.get(key, default)
```

Keep this class intentionally small and self-contained. It must be importable without any heavy Kiln dependencies since it will be serialized/deserialized across the process boundary (passed as constructor args, not pickled as a class).

### Step 3: Create `sandbox_worker.py`

**New file: `libs/core/kiln_ai/adapters/eval/sandbox_worker.py`**

This module contains two functions:

#### 3a: `_execute_scorer` (runs in child process)

This is the target function for `multiprocessing.Process`. It receives the user code string, the scorer arguments, and a `multiprocessing.Queue` for returning results.

```python
import multiprocessing
import traceback
from typing import Any

from pydantic import JsonValue


def _execute_scorer(
    code: str,
    output: str,
    trace: list[dict[str, Any]] | None,
    reference_data: dict[str, JsonValue] | None,
    task_input: str | None,
    result_queue: multiprocessing.Queue,  # type: ignore[type-arg]
) -> None:
    """Target function for the child process. Executes user scorer code.

    The user code must define a `score()` function with this signature:
        def score(output, trace, reference_data, task_input, kiln) -> dict[str, float]

    Results are put on the queue as (True, scores_dict) on success
    or (False, error_string) on failure.
    """
    try:
        from kiln_ai.adapters.eval.eval_utils.kiln_eval_helpers import KilnEvalHelpers

        kiln_helpers = KilnEvalHelpers(
            reference_data=reference_data,
            task_input=task_input,
            trace=trace,
        )

        namespace: dict[str, Any] = {}
        exec(code, namespace)  # noqa: S102

        score_fn = namespace.get("score")
        if score_fn is None:
            result_queue.put((False, "User code must define a 'score()' function"))
            return
        if not callable(score_fn):
            result_queue.put((False, "'score' is defined but is not callable"))
            return

        scores = score_fn(
            output=output,
            trace=trace,
            reference_data=reference_data,
            task_input=task_input,
            kiln=kiln_helpers,
        )

        result_queue.put((True, scores))
    except Exception:
        result_queue.put((False, traceback.format_exc()))
```

Key details:
- The function never raises -- all errors go on the queue as `(False, error_string)`.
- The `exec` call runs user code in an isolated namespace dict, not in the module's globals.
- `KilnEvalHelpers` is imported inside the function (since this runs in a child process, module-level imports from the parent aren't guaranteed).
- The `# noqa: S102` suppresses the Bandit `exec` warning -- this is intentional.

#### 3b: `run_scorer` (runs in parent process)

Orchestrates the spawn, timeout, and result collection. This is a synchronous blocking function (called from `run_in_executor` in the adapter).

```python
import multiprocessing
import queue
import threading
from typing import Any

from pydantic import JsonValue

_spawn_lock = threading.Lock()


def run_scorer(
    code: str,
    output: str,
    trace: list[dict[str, Any]] | None,
    reference_data: dict[str, JsonValue] | None,
    task_input: str | None,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Spawn a child process to execute the user scorer, with wall-clock timeout.

    Returns the scores dict on success.
    Raises RuntimeError on timeout, crash, or user code error.
    """
    result_queue: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]

    with _spawn_lock:
        p = multiprocessing.Process(
            target=_execute_scorer,
            args=(code, output, trace, reference_data, task_input, result_queue),
            daemon=True,
        )
        p.start()

    p.join(timeout=timeout_seconds)

    if p.is_alive():
        p.kill()
        p.join(timeout=5)
        raise RuntimeError(
            f"Code eval scorer timed out after {timeout_seconds}s"
        )

    if p.exitcode != 0:
        try:
            success, payload = result_queue.get_nowait()
            if not success:
                raise RuntimeError(f"Code eval scorer crashed: {payload}")
        except queue.Empty:
            pass
        raise RuntimeError(
            f"Code eval scorer process exited with code {p.exitcode}"
        )

    try:
        success, payload = result_queue.get_nowait()
    except queue.Empty:
        raise RuntimeError(
            "Code eval scorer process exited without returning results"
        )

    if not success:
        raise RuntimeError(f"Code eval scorer error:\n{payload}")

    return payload
```

Key details:
- `_spawn_lock` serializes `Process()` creation + `p.start()` for Linux/PyInstaller thread safety. The lock is released before `p.join()` so multiple scorers can run concurrently after they've started.
- `daemon=True` ensures the child is killed if the parent exits unexpectedly.
- After `p.join(timeout)`, if the process is still alive, `p.kill()` sends SIGKILL (hard kill). A secondary `p.join(5)` reaps the zombie.
- The queue is checked for results only after the process has exited. If the process was killed (timeout) or crashed, the queue may be empty.
- The return type is `dict[str, Any]` (not `dict[str, float]`) because validation happens in the adapter, not the worker. This keeps the worker's responsibility minimal.

### Step 4: Create `CodeEvalAdapter`

**New file: `libs/core/kiln_ai/adapters/eval/v2_eval_code_eval.py`**

This is the V2 adapter that wires together trust checking, worker spawning, and score validation.

```python
import asyncio
import logging
from typing import Any

from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.sandbox_worker import run_scorer
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    EvalConfig,
    EvalScores,
    EvalTaskInput,
    SkippedReason,
)

logger = logging.getLogger(__name__)


# Ephemeral per-project trust store.
# Keys are project paths (str). Values are True (trusted).
# Cleared on process restart. No persistence.
_trusted_projects: set[str] = set()


def grant_code_eval_trust(project_path: str) -> None:
    """Grant code_eval trust for a project (ephemeral, in-memory only)."""
    _trusted_projects.add(project_path)


def revoke_code_eval_trust(project_path: str) -> None:
    """Revoke code_eval trust for a project."""
    _trusted_projects.discard(project_path)


def is_code_eval_trusted(project_path: str) -> bool:
    """Check if a project has code_eval trust."""
    return project_path in _trusted_projects


class CodeEvalAdapter(BaseV2Eval):
    """V2 adapter for code_eval: runs user Python scorer in a subprocess."""

    def __init__(self, eval_config: EvalConfig) -> None:
        super().__init__(eval_config)
        if not isinstance(self.properties, CodeEvalProperties):
            raise ValueError(
                "CodeEvalAdapter requires CodeEvalProperties in the eval config"
            )

    async def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, CodeEvalProperties)

        # Trust gate check
        project_path = self._get_project_path()
        if project_path is None or not is_code_eval_trusted(project_path):
            return (
                {},
                SkippedReason.code_eval_not_trusted,
                "Code eval not trusted for this project. Grant trust before running.",
            )

        # Run scorer in a child process via executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        try:
            raw_scores = await loop.run_in_executor(
                None,
                run_scorer,
                props.code,
                eval_input.final_message,
                eval_input.trace,
                eval_input.reference_data,
                eval_input.task_input,
                props.timeout_seconds,
            )
        except RuntimeError as e:
            raise RuntimeError(f"Code eval failed: {e}") from e

        # Validate returned scores
        validated_scores = self._validate_scores(raw_scores)

        return validated_scores, None, None

    def _get_project_path(self) -> str | None:
        """Walk the parent chain to find the project path for trust checking."""
        parent_eval = self.eval_config.parent_eval()
        if parent_eval is None:
            return None
        task = parent_eval.parent_task()
        if task is None:
            return None
        project = task.parent_project()
        if project is None:
            return None
        return project.path

    def _validate_scores(self, raw_scores: Any) -> EvalScores:
        """Validate that raw_scores is a dict[str, float] with correct keys.

        Rejects bools (bool is a subclass of int, not float), non-float values,
        and mismatched keys.
        """
        if not isinstance(raw_scores, dict):
            raise RuntimeError(
                f"Scorer must return a dict, got {type(raw_scores).__name__}"
            )

        parent_eval = self.eval_config.parent_eval()
        if parent_eval is None:
            raise RuntimeError(
                "CodeEvalAdapter requires a parent Eval with output_scores"
            )

        expected_keys = {score.json_key() for score in parent_eval.output_scores}
        actual_keys = set(raw_scores.keys())

        if expected_keys != actual_keys:
            raise RuntimeError(
                f"Scorer returned keys {sorted(actual_keys)} but eval expects {sorted(expected_keys)}"
            )

        validated: EvalScores = {}
        for key, value in raw_scores.items():
            if isinstance(value, bool):
                raise RuntimeError(
                    f"Score '{key}' is a bool ({value}). Scores must be float values."
                )
            if not isinstance(value, (int, float)):
                raise RuntimeError(
                    f"Score '{key}' has type {type(value).__name__}. Scores must be float values."
                )
            validated[key] = float(value)

        return validated
```

Key design points:

- **Trust gate**: The `_trusted_projects` set is module-level and ephemeral. It uses the project's filesystem path as the key (unique, stable within a session). The helper functions `grant_code_eval_trust`, `revoke_code_eval_trust`, and `is_code_eval_trusted` are importable by the API layer.

- **`_get_project_path`**: Walks `eval_config -> parent_eval() -> parent_task() -> parent_project()` to find the project. Returns `None` if the chain is broken (which triggers the untrusted skip).

- **Score validation**: The adapter does its own validation before the `EvalRun` model validator runs. This provides clearer error messages. It rejects `bool` explicitly (since `isinstance(True, int)` is `True` in Python, a bool could sneak through as a numeric), converts `int` to `float`, and checks key sets match.

- **`run_in_executor`**: Uses the default thread pool executor (`None`) to run the blocking `run_scorer` call. This keeps the async event loop responsive while the child process runs.

### Step 5: Register `CodeEvalAdapter` in the registry

**File: `libs/core/kiln_ai/adapters/eval/registry.py`**

5a. Add import at the top (after the existing adapter imports):

```python
from kiln_ai.adapters.eval.v2_eval_code_eval import CodeEvalAdapter
```

5b. Add entry to `_V2_ADAPTER_MAP`:

```python
_V2_ADAPTER_MAP: dict[V2EvalType, type[BaseV2Eval]] = {
    V2EvalType.exact_match: ExactMatchEval,
    V2EvalType.pattern_match: PatternMatchEval,
    V2EvalType.contains: ContainsEval,
    V2EvalType.set_check: SetCheckEval,
    V2EvalType.tool_call_check: ToolCallCheckEval,
    V2EvalType.step_count_check: StepCountCheckEval,
    V2EvalType.llm_judge: LlmJudgeEval,
    V2EvalType.code_eval: CodeEvalAdapter,
}
```

After this, `v2_eval_adapter_from_config()` will resolve `code_eval` configs to `CodeEvalAdapter` instead of raising `NotImplementedError`.

### Step 6: Add `freeze_support` and `set_start_method` to entry points

#### 6a: `app/desktop/desktop.py`

Insert two lines as the very first statements in the `if __name__ == "__main__":` block (line 183), before the sentry init:

```python
if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)

    # Sentry is gated on DSN presence ...
```

`freeze_support()` is required for PyInstaller on Windows -- without it, frozen executables using multiprocessing will loop infinitely. `set_start_method("spawn", force=True)` ensures all platforms use spawn (consistent behavior; fork is unsafe with threads and can deadlock).

#### 6b: `app/desktop/dev_server.py`

Insert the same two lines at the top of `if __name__ == "__main__":` (line 22), before `setup_resource_limits()`:

```python
if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn", force=True)

    setup_resource_limits()
```

Note: `dev_app = make_app()` at module level (line 16) runs before `__main__`, but this is just FastAPI app construction -- no `multiprocessing.Process` is created at import time, so the ordering is safe.

### Step 7: Add trust-grant API endpoint

**File: `app/desktop/studio_server/eval_api.py`**

Add a new endpoint inside `connect_evals_api(app)` that lets the UI grant code_eval trust for a project. This is an ephemeral, session-only trust grant.

```python
@app.post(
    "/api/projects/{project_id}/grant_code_eval_trust",
    summary="Grant Code Eval Trust",
    tags=["Evals"],
    openapi_extra=DENY_AGENT,
)
async def grant_code_eval_trust_endpoint(
    project_id: Annotated[
        str, Path(description="The unique identifier of the project.")
    ],
):
    from kiln_ai.adapters.eval.v2_eval_code_eval import (
        grant_code_eval_trust,
        is_code_eval_trusted,
    )
    from kiln_server.task_api import project_from_id

    project = project_from_id(project_id)
    grant_code_eval_trust(project.path)
    return {"trusted": is_code_eval_trusted(project.path)}
```

Also add a GET endpoint to check trust status:

```python
@app.get(
    "/api/projects/{project_id}/code_eval_trust",
    summary="Check Code Eval Trust Status",
    tags=["Evals"],
    openapi_extra=DENY_AGENT,
)
async def check_code_eval_trust_endpoint(
    project_id: Annotated[
        str, Path(description="The unique identifier of the project.")
    ],
):
    from kiln_ai.adapters.eval.v2_eval_code_eval import is_code_eval_trusted
    from kiln_server.task_api import project_from_id

    project = project_from_id(project_id)
    return {"trusted": is_code_eval_trusted(project.path)}
```

Design notes:
- `DENY_AGENT` policy -- trust grants should only come from human interaction through the UI, not automated agents.
- `project_from_id` validates the project exists and returns it with its path (used as the trust key).
- Imports are inline to avoid circular dependencies between the server and core library layers.
- No revoke endpoint for now -- trust is ephemeral (cleared on restart). Revoke can be added when the UI needs it.

### Step 8: Cold-start validation

After all code is implemented and tests pass, manually validate the following in the dev server:

1. **Create a code_eval config** via the API (or test fixture) with a simple scorer:
   ```python
   def score(output, trace, reference_data, task_input, kiln):
       return {"accuracy": 1.0 if "hello" in output.lower() else 0.0}
   ```
2. **Run without trust** -- verify the eval run is created with `skipped_reason=code_eval_not_trusted`.
3. **Grant trust** via the POST endpoint, then re-run -- verify scores are produced.
4. **Test timeout** -- create a scorer with `import time; time.sleep(60)` and a 2-second timeout. Verify the process is killed and a `RuntimeError` is raised.
5. **Test bad return** -- scorer returns `{"accuracy": True}`. Verify the bool is rejected with a clear error.

This is a manual smoke-test checklist, not automated. It validates the end-to-end flow in the actual server environment. If building in a PyInstaller bundle, also verify `freeze_support` does not cause issues (the bundled app should start normally and code_eval should function).

## Tests

All test files go in the standard test directories mirroring source structure.

### Test file: `libs/core/kiln_ai/adapters/eval/test_sandbox_worker.py`

Tests for `run_scorer` and `_execute_scorer`:

1. **Happy path**: scorer returns `{"score": 1.0}`. Verify `run_scorer` returns the dict.
2. **Scorer raises exception**: scorer code is `def score(**kwargs): raise ValueError("boom")`. Verify `RuntimeError` with traceback.
3. **Scorer missing `score` function**: code is `x = 1`. Verify `RuntimeError` mentioning "must define a 'score()' function".
4. **Scorer returns non-dict**: code returns a list. Verify error from adapter validation (or worker if pre-validated).
5. **Timeout**: scorer sleeps longer than timeout. Use a short timeout (2s). Verify `RuntimeError` mentioning "timed out". Use `pytest` timeout marker as safety net.
6. **Scorer returns bool value**: `{"score": True}`. This should be returned by the worker (validation is in the adapter), but include it as an integration test when testing through the adapter.
7. **Syntax error in user code**: code is `def score(`. Verify `RuntimeError` with syntax error traceback.
8. **Import in user code**: scorer does `import math; return {"score": math.sqrt(4)}`. Verify it works (stdlib imports are allowed).
9. **`score` is not callable**: code is `score = 42`. Verify error.

### Test file: `libs/core/kiln_ai/adapters/eval/test_v2_eval_code_eval.py`

Tests for `CodeEvalAdapter`:

1. **Trust gate -- not trusted**: create adapter, call `evaluate()` without granting trust. Verify returns `({}, SkippedReason.code_eval_not_trusted, ...)`.
2. **Trust gate -- trusted**: grant trust, call `evaluate()` with a valid scorer. Verify scores are returned.
3. **Trust grant/revoke/check functions**: unit test `grant_code_eval_trust`, `revoke_code_eval_trust`, `is_code_eval_trusted` directly.
4. **Score validation -- bool rejected**: mock `run_scorer` to return `{"accuracy": True}`. Verify `RuntimeError`.
5. **Score validation -- int converted to float**: mock `run_scorer` to return `{"accuracy": 1}`. Verify the adapter converts it to `1.0`.
6. **Score validation -- wrong keys**: mock `run_scorer` to return `{"wrong_key": 1.0}`. Verify `RuntimeError` about key mismatch.
7. **Score validation -- non-dict**: mock `run_scorer` to return `[1.0]`. Verify `RuntimeError`.
8. **Timeout propagation**: mock `run_scorer` to raise `RuntimeError("timed out")`. Verify the adapter re-raises.
9. **Project path resolution**: test `_get_project_path` with a properly parented eval config. Verify it returns the project path.
10. **Project path -- broken chain**: test with an eval config that has no parent eval. Verify returns `None` (triggers untrusted skip).

For tests that need a real `EvalConfig` with `CodeEvalProperties`, create fixtures following the pattern used in existing V2 eval tests (e.g., `test_v2_eval_exact_match.py`). The fixture should create a `Task` -> `Eval` -> `EvalConfig` hierarchy with `config_type=EvalConfigType.v2` and `properties=CodeEvalProperties(code="...", timeout_seconds=5)`.

For tests that call `run_scorer` directly (integration tests), mark them with `@pytest.mark.timeout(30)` as a safety net in case the child process hangs.

### Test file: `libs/core/kiln_ai/adapters/eval/eval_utils/test_kiln_eval_helpers.py`

1. **`ref()` with data**: verify `ref("key")` returns the value.
2. **`ref()` with missing key**: verify returns default.
3. **`ref()` with no reference_data**: verify returns default.
4. **Properties**: verify `reference_data`, `task_input`, `trace` properties return correct values.

### Test file: `app/desktop/studio_server/test_eval_api_trust.py` (or add to existing eval_api test file)

1. **Grant trust endpoint**: POST to `/api/projects/{id}/grant_code_eval_trust`, verify 200 and `{"trusted": true}`.
2. **Check trust endpoint**: GET before granting returns `{"trusted": false}`, after granting returns `{"trusted": true}`.
3. **Invalid project**: POST with bad project_id, verify 404.

### Existing test impact

Verify that existing tests in `test_eval_runner.py` still pass. The registration of `CodeEvalAdapter` in `_V2_ADAPTER_MAP` means `v2_eval_adapter_from_config()` will no longer raise `NotImplementedError` for `code_eval` -- any tests that expect that behavior need to be updated.

## Out of Scope

- **OS sandboxing** (seccomp, AppArmor, macOS sandbox-exec) -- trust gate is the only security boundary. Documented as a Beta limitation.
- **`setrlimit` resource caps** -- originally P2 in component-27. Cut to reduce complexity. Can be added to `_execute_scorer` later without API changes (it would call `resource.setrlimit` at the top of the child process before `exec`).
- **Persistent trust store** -- trust is ephemeral (in-memory set, cleared on restart). Persistence can be added later if needed.
- **Revoke trust API endpoint** -- not needed until the UI is built (Phase 6). The helper function `revoke_code_eval_trust` exists for testing but has no API surface.
- **Code eval UI** (create form, CodeMirror editor, trust dialog) -- Phase 6.
- **Per-type result rendering for code_eval** -- Phase 6.
- **Network/filesystem restriction in child process** -- documented limitation. Users can `import os`, `open()`, `requests.get()`, etc. in their scorer code. The trust gate is the user's acknowledgment of this risk.
- **Cold-start PyInstaller bundle spike** -- the implementation does not depend on this. If `freeze_support` + spawn causes issues in the bundled app, it can be debugged post-merge. The dev server is the primary validation target.
