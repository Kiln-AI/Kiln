---
status: complete
approved: true
alignment_refs: [A0.3, A0.4, B.12, B.13, B.14, G.2]
opens: []
summary: code_eval properties shape, scorer contract (injected vars + return shape), helper library, error handling, execution model per B.13, trust-gate coordination.
---

# Type: Code Eval

**Author:** sub-agent dispatched 2026-06-03 for Stage 4 gap-fill
**Status:** complete

## TL;DR

- `CodeEvalProperties` stores user Python as an **inline code string** (self-contained EvalConfig; file-ref and import-path rejected). The code is the `code` field; the only other field is `timeout_seconds: int = 30`.
- **Scorer contract** (the function-call agreement between Kiln and user code): user code defines `def score(output, trace, reference_data, task_input, kiln) -> dict[str, float]` and Kiln calls it, reading the returned dict keyed on the Eval's `output_scores` names. No bool convenience — values must be floats in the correct range; use `kiln.pass_fail()` / `kiln.five_star()` helpers. This contract is fully specified here and **resolves `O-codeeval-scorer-contract`**.
- **Helper library** (`kiln`): a lightweight namespace injected into the worker, providing trace-navigation, tool-call extraction, scoring constructors, and assertion helpers. Pure Python, zero heavy imports.
- **Execution model** follows B.13 exactly: `multiprocessing.Process` (spawn mode) + `freeze_support()` + wall-clock timeout via `p.join(timeout)` / `p.kill()`. No WASM, no language-level sandbox, no AST gating. Trust boundary is UX only.
- **Error handling**: worker captures exceptions and crash exit codes; adapter maps them to structured `Score.failed(reason=...)` results. Stdout/stderr captured and forwarded for diagnostics.
- **Trust-gate UX coordination**: this file owns the backend contract; `components/70` (G.2) owns the in-browser editor and ephemeral trust modal.

---

## 1. `CodeEvalProperties` shape (B.12)

### 1.1 Decision: inline code string

User-authored Python lives as an inline string in the `code` field of `CodeEvalProperties`. The EvalConfig JSON file is self-contained -- no external `.py` file reference, no Python import path.

```python
class CodeEvalProperties(BaseModel):
    type: Literal["code_eval"] = "code_eval"
    code: str                         # user-authored Python scorer body
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Wall-clock timeout for a single scorer execution (seconds).",
    )
```

### 1.2 Why inline, not file-ref or import-path

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Inline string** | Self-contained EvalConfig (shareable, diffable, git-friendly). Builder UI writes directly to this field. No path-resolution or import-system coupling. | No IDE support (no `.py` file). Larger JSON for complex scorers. | **Chosen.** |
| **File reference** (relative `.py` path) | IDE support (syntax, lint, debug). Cleaner for long code. | EvalConfig is no longer self-contained -- sharing requires the `.py` file alongside. Path resolution across OSes. Breaks the "EvalConfig JSON = complete config" invariant. | Rejected. |
| **Import path** (`my_package.scorers.safety`) | Full code-reuse; unit-testable scorers. | Requires pip-installable code in the project -- hostile to the PyInstaller bundle (A0.4) and to non-developer users. Effectively a plugin model, which is explicitly closed for V2.0 (E.36). | Rejected. |

The inline approach matches OpenAI Platform's `PythonGrader` (code string in the grader JSON) and is the natural shape for the CodeMirror in-browser editor (G.2). If a user's scorer grows beyond what's comfortable inline, `code_eval` is the wrong tool -- they should request a new built-in type or (post-V2) use a plugin.

### 1.3 Save-time validation

When an `EvalConfig` with `CodeEvalProperties` is saved, the server:

1. **Syntax check:** `compile(code, "<code_eval>", "exec")`. Invalid Python syntax rejects the save with a clear error.
2. **Size cap:** `len(code.encode("utf-8")) <= 64 * 1024` (64 KB). Generous for scoring logic; prevents accidental paste of large files. Matches the order of magnitude of OpenAI's 256 KB cap.
3. **`score` function definition check (best-effort):** Static analysis (AST walk) checks that the code contains a `def score(` definition at module scope. This is advisory -- it cannot catch all dynamic definition patterns, but catches the most common mistake (forgetting to define the `score` function).

No import allowlist or AST gating (per B.13 -- trust boundary is UX, not language-level restrictions).

---

## 2. Scorer contract -- injected variables and return shape

This is the central contract between Kiln and user-authored scorer code. It defines what the user's code receives and what it must produce. **This section resolves `O-codeeval-scorer-contract`.**

### 2.1 `score()` function parameters

User code defines a `score` function at module scope. Kiln calls it with five positional arguments:

```python
def score(output, trace, reference_data, task_input, kiln) -> dict[str, float]:
    ...
    return {"score_name": <float>, ...}
```

| Parameter | Type | Description |
|---|---|---|
| `output` | `str \| dict` | The model's final output for this eval case. String for plain-text tasks; dict for tasks with `output_json_schema`. Sourced from `TaskRun.output.output` (same as `components/40`'s `final_message`). |
| `trace` | `list[dict] \| None` | The full conversation trace in Kiln's modified OpenAI format (`list[ChatCompletionMessageParam]`). `None` when the eval case has no trace (e.g., `EvalDataType.final_answer` runs). Each entry has `role` (system/user/assistant/tool), `content`, and optionally `tool_calls` / `tool_call_id`. |
| `reference_data` | `dict[str, Any] \| None` | The reference data from `EvalInput.reference` for this case. `None` if no reference data is set. |
| `task_input` | `str \| dict` | The original input given to the task being evaluated. Sourced from `TaskRun.input` / `EvalInput.data.user_message.text`. |
| `kiln` | `KilnEvalHelpers` | Helper library namespace (see section 3). Provides trace-navigation, tool-call extraction, scoring constructors, and assertion helpers. |

**Naming rationale:** `output` (not `final_message`) because user-facing code should use the most intuitive name for "what the model produced." `trace`, `reference_data`, and `task_input` match the `components/40` reserved template variable names (minus `final_message` which maps to `output` here for readability). The `kiln` namespace avoids polluting the top-level with helper functions and makes it clear which utilities come from Kiln vs. user code.

**Serialization note:** All injected values are plain Python types (str, dict, list, None) -- no Pydantic models cross the multiprocessing boundary. The adapter serializes inputs to JSON-safe dicts before passing to the worker; the worker deserializes them in the child process. This avoids pickling Kiln model classes across the process boundary (which would require the worker to import them, violating the thin-worker-module constraint from B.13).

### 2.2 Return shape: `dict[str, float]`

The `score()` function must return a `dict[str, float]` whose keys are a subset of the Eval's `output_scores` score names.

- **`float` values** must already be in the correct range for each score's `rating_type`: 0.0-1.0 for `pass_fail` / `pass_fail_critical`; 0.0-5.0 for `five_star`. Use the `kiln.pass_fail(passed)` and `kiln.five_star(rating)` helpers (section 3.3) to produce correct floats from booleans or integers.
- **No bool convenience.** A `bool` value (or any non-float type) is a **hard error** (failed score with a reason), not coerced. This avoids implicit magic; use `kiln.pass_fail(passed)` explicitly.
- **Missing keys** are allowed -- the adapter maps absent scores to `None` on the EvalRun (same as a skip for that score dimension). All keys present in the Eval's `output_scores` but absent from the return dict are surfaced as warnings in the test-run preview.
- **Extra keys** (not in `output_scores`) are silently ignored (consistent with the existing `EvalRun.validate_scores` mechanism per C.9 -- it validates required keys, not surplus ones).

**Error cases:**

| Condition | Behavior |
|---|---|
| `score` function not defined or not callable | `Score.failed(reason="Scorer code does not define a callable 'score' function")` |
| `score()` did not return a dict | `Score.failed(reason="'score()' must return dict[str, float], got <type>")` |
| A value is not a float (including bool) | `Score.failed(reason="Score '<key>' must be float, got <type>. Use kiln.pass_fail() or kiln.five_star() for conversions.")` |
| A float value is outside the valid range for its rating type | `Score.failed(reason="Score '<key>' value <v> is outside valid range [<min>, <max>]")` |
| `score()` raises an exception | `Score.failed(reason="Scorer error: <exception message>")` |
| Worker crashes (nonzero exit, empty queue) | `Score.failed(reason="Scorer crashed (exit code <N>)")` |
| Wall-clock timeout | `Score.failed(reason="Scorer exceeded <N>s wall-clock timeout")` |

### 2.3 Minimal valid example

This is the simplest possible scorer -- the "hello world" that the CodeMirror editor loads with, and the starting point for the `components/70` examples gallery:

```python
def score(output, trace, reference_data, task_input, kiln):
    # Check if the output contains "hello"
    passed = "hello" in output.lower()
    return {"greeting_quality": kiln.pass_fail(passed)}
```

(Assumes the Eval has an `output_score` named `greeting_quality` with type `pass_fail`.)

### 2.4 Richer examples (gallery content for components/70)

These examples populate the "See examples" modal in the code-eval create UI (G.2):

**Parse JSON and compare fields:**
```python
import json

def score(output, trace, reference_data, task_input, kiln):
    parsed = json.loads(output) if isinstance(output, str) else output
    expected = reference_data["expected_fields"]

    matches = sum(1 for k, v in expected.items() if parsed.get(k) == v)
    total = len(expected)

    return {"field_accuracy": matches / total if total > 0 else 0.0}
```

**Check tool usage patterns:**
```python
def score(output, trace, reference_data, task_input, kiln):
    tool_calls = kiln.get_tool_calls(trace)

    used_search = kiln.has_tool_call(tool_calls, "web_search")
    used_forbidden = kiln.has_tool_call(tool_calls, "delete_record")

    return {
        "used_correct_tool": kiln.pass_fail(used_search),
        "avoided_forbidden": kiln.pass_fail(not used_forbidden),
    }
```

**Domain-specific grading with reference:**
```python
import re

def score(output, trace, reference_data, task_input, kiln):
    # Extract numeric answer from output
    numbers = re.findall(r"[-+]?\d*\.?\d+", output)
    predicted = float(numbers[-1]) if numbers else None

    expected = reference_data["expected_value"]
    tolerance = reference_data.get("tolerance", 0.01)

    passed = predicted is not None and abs(predicted - expected) <= tolerance
    return {"numerical_accuracy": kiln.pass_fail(passed)}
```

---

## 3. Eval helper library (`kiln` namespace)

A lightweight set of helpers injected as the `kiln` namespace object. All pure Python, no heavy imports. The helper library runs inside the worker process and must not import Kiln's UI, DB, or model registry modules (B.13 worker-module hygiene).

### 3.1 Trace navigation

```python
kiln.get_tool_calls(trace: list[dict] | None) -> list[dict]
```
Returns a flat list of all tool-call dicts from assistant messages in the trace. Each dict has `name: str`, `arguments: dict | str`, and `id: str`. Returns `[]` if trace is `None` or has no tool calls.

```python
kiln.get_assistant_messages(trace: list[dict] | None) -> list[str]
```
Returns the `content` strings from all assistant-role messages in the trace. Returns `[]` if trace is `None`.

```python
kiln.get_tool_results(trace: list[dict] | None) -> list[dict]
```
Returns a flat list of tool-result dicts from tool-role messages. Each dict has `tool_call_id: str` and `content: str`. Returns `[]` if trace is `None`.

### 3.2 Tool-call matching

```python
kiln.has_tool_call(
    tool_calls: list[dict],
    tool_name: str,
    expected_args: dict | None = None,
) -> bool
```
Returns `True` if any tool call in the list matches `tool_name` (and optionally has `expected_args` as a subset of its arguments). Arguments comparison is shallow-equal for scalar values.

```python
kiln.count_tool_calls(
    tool_calls: list[dict],
    tool_name: str | None = None,
) -> int
```
Counts tool calls, optionally filtered by `tool_name`. If `tool_name` is `None`, counts all.

### 3.3 Scoring constructors

```python
kiln.pass_fail(passed: bool) -> float
```
Returns `1.0` if `passed`, `0.0` otherwise. Convenience for `pass_fail` / `pass_fail_critical` rating types.

```python
kiln.five_star(rating: int) -> float
```
Returns `float(rating)` clamped to `[1.0, 5.0]`. Raises `ValueError` if `rating` is not in `[1, 5]`.

### 3.4 Assertion helpers

```python
kiln.assert_contains(text: str, substring: str) -> bool
```
Returns `True` if `substring` is in `text` (case-sensitive). Does not raise.

```python
kiln.assert_not_contains(text: str, substring: str) -> bool
```
Returns `True` if `substring` is NOT in `text`. Does not raise.

```python
kiln.assert_matches(text: str, pattern: str) -> bool
```
Returns `True` if `re.search(pattern, text)` finds a match. Does not raise.

### 3.5 Library implementation constraints

- The `kiln` namespace is a plain Python object (a module-level instance of a `KilnEvalHelpers` class or a `SimpleNamespace` with bound functions). It is defined inside `sandbox_worker.py` or a sibling `eval_helpers.py` that `sandbox_worker.py` imports.
- **No Pydantic, no Kiln model imports.** The helpers work on plain dicts and strings only. This keeps the worker module thin (B.13 hygiene constraint).
- All functions are synchronous (no async in the worker).
- The helpers intentionally do NOT wrap `json.loads`, `re`, or other stdlib modules -- those are available to user code directly via normal `import`. The helpers exist for trace-shape-specific navigation that users would otherwise have to rewrite.

---

## 4. Execution model (B.13 -- followed exactly)

This section documents the execution model without reopening the sandboxing decision. B.13 is the locked alignment decision; this section carries implementation detail.

### 4.1 Architecture

```
CodeEvalAdapter.run_eval(eval_input)
    |
    +-- trust gate check (project_trust_granted?)
    |     |-- not granted: raise CodeEvalNotTrustedError
    |
    +-- serialize inputs to JSON-safe dict
    |     (output, trace, reference_data, task_input -- all plain types)
    |
    +-- call run_scorer(code, inputs, timeout)
    |     |
    |     +-- multiprocessing.Queue()
    |     +-- multiprocessing.Process(target=_execute_scorer, ...)
    |     |     start method: "spawn" (explicit on Linux; default on macOS/Windows)
    |     |
    |     +-- p.start()
    |     +-- p.join(timeout=timeout_seconds)
    |     +-- if p.is_alive(): p.kill(); p.join(); raise TimeoutError
    |     +-- if p.exitcode != 0 and q.empty(): raise RuntimeError(crash)
    |     +-- return q.get_nowait()
    |
    +-- interpret result
          |-- {"ok": result_dict} -> validate + map to EvalRun scores
          |-- {"error": message}  -> Score.failed(reason=message)
          |-- {"error": message, "stdout": str, "stderr": str}
          |       -> Score.failed with captured output for diagnostics
```

### 4.2 Worker module (`sandbox_worker.py`)

```python
# kiln/eval/sandbox_worker.py
# THIN module. Imports ONLY stdlib + the eval_helpers peer module.
# NO UI framework, NO DB layer, NO model registry, NO `from kiln_ai.*` imports.
# Enforced by lint rule / CI / convention (B.13 gotcha #1).

import multiprocessing
import sys
import io
import traceback

from kiln.eval.eval_helpers import KilnEvalHelpers


def _execute_scorer(
    code: str,
    inputs: dict,
    result_queue: multiprocessing.Queue,
):
    # Capture stdout/stderr from user code
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    # Handle --windowed PyInstaller builds where sys.stdout is None (B.13 gotcha #3)
    sys.stdout = captured_stdout
    sys.stderr = captured_stderr

    try:
        ns = {}
        exec(code, ns)

        result_payload = {
            "stdout": captured_stdout.getvalue(),
            "stderr": captured_stderr.getvalue(),
        }
        if "score" not in ns or not callable(ns["score"]):
            result_payload["error"] = "Scorer code does not define a callable 'score' function"
        else:
            result_payload["ok"] = ns["score"](
                inputs["output"],
                inputs.get("trace"),
                inputs.get("reference_data"),
                inputs["task_input"],
                KilnEvalHelpers(),
            )

        result_queue.put(result_payload)
    except Exception as e:
        result_queue.put({
            "error": f"Scorer error: {e}",
            "traceback": traceback.format_exc(),
            "stdout": captured_stdout.getvalue(),
            "stderr": captured_stderr.getvalue(),
        })
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr


def run_scorer(
    code: str,
    inputs: dict,
    timeout: float,
) -> dict:
    q = multiprocessing.Queue()
    p = multiprocessing.Process(
        target=_execute_scorer,
        args=(code, inputs, q),
    )
    p.start()
    p.join(timeout=timeout)
    if p.is_alive():
        p.kill()
        p.join()
        raise TimeoutError(f"Scorer exceeded {timeout}s wall-clock limit")
    if p.exitcode != 0 and q.empty():
        raise RuntimeError(f"Scorer crashed (exit code {p.exitcode})")
    return q.get_nowait()
```

### 4.3 Entry point wiring

```python
# kiln/__main__.py (or equivalent entry point)
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()  # MUST be first line (B.13)
    # ... rest of Kiln startup
```

On Linux: `multiprocessing.set_start_method("spawn")` called during startup, before any `Process` is created.

### 4.4 Resource limits (P2 -- Unix only)

```python
# In _execute_scorer, before exec(), on Unix only:
import resource

def _apply_rlimits(limits: dict):
    if hasattr(resource, "RLIMIT_CPU") and "cpu" in limits:
        resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu"], limits["cpu"]))
    if hasattr(resource, "RLIMIT_AS") and "mem" in limits:
        resource.setrlimit(resource.RLIMIT_AS, (limits["mem"], limits["mem"]))
```

Default limits: `cpu=30` seconds, `mem=512MB`. These are **P2 -- cut if any complexity arises in implementation.** Wall-clock timeout (section 4.2) is the primary safeguard on all platforms.

Windows: no rlimits enforced. Wall-clock timeout + crash isolation are sufficient for V2.0.

### 4.5 What the execution model enforces / does not enforce

| Enforced | Mechanism | Platform |
|---|---|---|
| Crash isolation | `multiprocessing.Process` (child crash does not take down Kiln) | All |
| Wall-clock timeout | `p.join(timeout)` + `p.kill()` | All |
| CPU cap (P2) | `resource.setrlimit(RLIMIT_CPU)` | Unix only |
| Memory cap (P2) | `resource.setrlimit(RLIMIT_AS)` | Unix only |
| Trust consent | Per-project ephemeral trust gate (components/70 G.2) | All |

| NOT enforced | Why |
|---|---|
| Network access | Wide open. User code can `import requests`. Per B.13. |
| Filesystem access | Wide open. User code can read/write anything the user can. Per B.13. |
| Import restrictions | No AST gating, no import allowlist. Per B.13 (punted by Steve). |
| Windows resource caps | No kernel-level mechanism without `pywin32` Job Objects. Deferred to V2.x. |

### 4.6 Spawn thread-safety (B.13 gotcha #5)

Concurrent spawns from multiple threads can fail on Linux PyInstaller (issue #7410). `CodeEvalAdapter` serializes worker spawns behind a module-level `threading.Lock`. If parallel eval batches include `code_eval` configs, they are executed serially (one `code_eval` at a time). Non-code-eval types are unaffected and can run in parallel.

```python
_SPAWN_LOCK = threading.Lock()

class CodeEvalAdapter(BaseEval):
    async def run_eval(self, item, ...):
        # ... trust check, input serialization ...
        with _SPAWN_LOCK:
            result = run_scorer(
                code=self.eval_config.properties.code,
                inputs=serialized_inputs,
                timeout=self.eval_config.properties.timeout_seconds,
            )
        # ... result interpretation ...
```

---

## 5. `CodeEvalAdapter` -- adapter contract

### 5.1 Class structure

```python
class CodeEvalAdapter(BaseEval):
    """V2 adapter for code_eval EvalConfigType.

    Runs user Python in a multiprocessing child (B.13).
    Subclasses BaseEval (C.11c -- no BaseEvalV2 fork).
    Registered in _V2_ADAPTER_MAP (components/20 section 2.2).
    """

    async def run_eval(self, item: EvalInput, ...) -> EvalScores:
        if not project_trust_granted(self.project):
            raise CodeEvalNotTrustedError(
                "Code evals require trust approval. "
                "Open the eval in the Kiln UI to grant trust."
            )

        props: CodeEvalProperties = self.eval_config.properties
        inputs = self._serialize_inputs(item)

        with _SPAWN_LOCK:
            raw_result = run_scorer(
                code=props.code,
                inputs=inputs,
                timeout=props.timeout_seconds,
            )

        return self._interpret_result(raw_result)
```

### 5.2 Input serialization

The adapter converts the `EvalInput` (or translated `EvalInput` from B2.1) into a plain dict for the worker:

```python
def _serialize_inputs(self, item: EvalInput) -> dict:
    return {
        "output": self._get_output(item),        # str | dict
        "trace": self._get_trace(item),           # list[dict] | None
        "reference_data": item.reference,         # dict | None
        "task_input": self._get_task_input(item),  # str | dict
    }
```

The `_get_output` and `_get_trace` methods read from the runner's side-channel (`EvalJob.stored_output` for `eval_config_eval` mode; fresh run output for `task_run_eval` mode), consistent with how other V2 adapters receive data (D.2/D.3 template variable assembly).

### 5.3 Result interpretation

```python
def _interpret_result(self, raw: dict) -> EvalScores:
    if "error" in raw:
        return Score.failed(
            reason=raw["error"],
            details={
                "traceback": raw.get("traceback"),
                "stdout": raw.get("stdout"),
                "stderr": raw.get("stderr"),
            },
        )

    result_dict = raw["ok"]

    # Validate type
    if not isinstance(result_dict, dict):
        return Score.failed(
            reason=f"'score()' must return dict[str, float], got {type(result_dict).__name__}"
        )

    # Map to EvalScores
    scores = {}
    for score_spec in self.eval.output_scores:
        key = score_spec.name
        if key not in result_dict:
            scores[key] = None  # missing = skip this score dimension
            continue
        val = result_dict[key]
        # bool is a subclass of int in Python -- reject it explicitly
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            return Score.failed(
                reason=f"Score '{key}' must be float, got {type(val).__name__}. Use kiln.pass_fail() or kiln.five_star() for conversions."
            )
        scores[key] = self._validate_range(float(val), score_spec)

    return scores
```

---

## 6. Error handling and diagnostics

### 6.1 Error taxonomy

| Error source | Detection | User-facing message | Diagnostic info |
|---|---|---|---|
| Syntax error in user code | `compile()` at save time | Save rejected with line/column | Full `SyntaxError` message |
| Runtime exception in user code | `except` in `_execute_scorer` | "Scorer error: {exception}" | Full traceback + captured stdout/stderr |
| Worker crash (segfault, C-extension fatal) | `p.exitcode != 0` + empty queue | "Scorer crashed (exit code {N})" | Exit code; no traceback available |
| Wall-clock timeout | `p.is_alive()` after `join(timeout)` | "Scorer exceeded {N}s wall-clock timeout" | None (worker killed) |
| `score` function not defined / not callable | Post-exec namespace check | "Scorer code does not define a callable 'score' function" | Captured stdout/stderr |
| `score()` return is not a dict | Post-exec type check | "'score()' must return dict[str, float]..." | Actual type |
| Score value not a float (including bool) | Adapter type check | "Score '{key}' must be float, got {type}. Use kiln.pass_fail()..." | Actual type |
| Score value out of range | Adapter range check | "Score '{key}' value {v} outside [min, max]" | Expected range |
| `CodeEvalNotTrustedError` | Pre-execution trust check | "Code evals require trust approval..." | N/A |

### 6.2 Stdout / stderr capture

User code's `print()` output is captured via `io.StringIO` redirection in the worker. This serves two purposes:

1. **Diagnostics:** captured output is included in `Score.failed()` details so users can debug their scorer from the test-run preview.
2. **PyInstaller `--windowed` safety (B.13 gotcha #3):** in windowed builds, `sys.stdout` is `None`. Without redirection, `print()` from user code would crash. The worker replaces stdout/stderr before `exec()` and restores them after.

### 6.3 Queue serialization protocol

The worker puts exactly one dict on the `multiprocessing.Queue`:

```python
# Success:
{"ok": result_dict, "stdout": str, "stderr": str}

# User code exception:
{"error": str, "traceback": str, "stdout": str, "stderr": str}

# Missing score function:
{"error": "Scorer code does not define a callable 'score' function", "stdout": str, "stderr": str}
```

All values are JSON-serializable plain types. No Pydantic models, no Kiln objects. The queue uses Python's default pickle serialization (safe because both sides are the same Python process and the payload is plain types).

---

## 7. Trust-gate coordination (B.13 + G.2)

### 7.1 Backend contract

The `CodeEvalAdapter` checks trust before execution:

```python
def project_trust_granted(project) -> bool:
    """Check if the user has granted code-eval trust for this project.

    Trust state is ephemeral (window-scoped, in-memory only per G.2).
    The backend holds a runtime dict keyed by project path.
    Re-asked on each app launch. No disk/DB persistence.
    """
    return _trusted_projects.get(project.path, False)
```

- `_trusted_projects: dict[str, bool]` is a module-level dict, cleared on app restart.
- The `/grant_code_eval_trust` API endpoint (called by the G.2 trust modal) sets `_trusted_projects[project_path] = True`.
- There is no revoke endpoint -- closing the app window clears trust (ephemeral, per G.2).

### 7.2 UI contract (cross-ref to components/70)

The trust modal and its UX are owned by `components/70` (G.2). This file's contract:

- The backend raises `CodeEvalNotTrustedError` if trust is not granted.
- The frontend catches this error and shows the trust modal.
- The trust modal calls `/grant_code_eval_trust` on acceptance.
- The frontend retries the test-run or save after trust is granted.

### 7.3 Trust wording

Per G.2: "never paste code from a stranger or the internet here." The modal explains that code runs with the user's filesystem and network access. Framing mirrors VS Code workspace trust and Claude Code's permission model.

---

## 8. Relationship to other design files

| Cross-ref | What this file owns | What the other file owns |
|---|---|---|
| `components/20` (adapter contract) | `CodeEvalAdapter` subclasses `BaseEval`, registered in `_V2_ADAPTER_MAP` | Two-level dispatch, `BaseEval` contract, `V2EvalType` enum |
| `components/40` (templates + extraction) | `code_eval` does NOT use `extract()` or `JinjaInputTransform` -- it gets raw sources via the helper lib | Template/extraction infra for other V2 types |
| `components/70` (builder + onboarding, G.2) | Scorer contract (injected vars + return shape), helper library surface, examples gallery content, save-time validation | CodeMirror editor, trust modal UI, test-run pane, Save-Without-Testing flow |
| `components/45` (runner architecture) | N/A (code_eval has no special runner requirements) | Runner dispatches `CodeEvalAdapter` via the standard V2 adapter registry |
| `components/90` (open risks, B.14) | `event_ordering` can be expressed via `code_eval` | Lists code-eval residual risks (network/FS wide open, Windows no rlimits) |

---

## 9. B.14 -- `event_ordering` on `code_eval`

Per B.14, `event_ordering` is deferred to post-V2. If/when revisited, the default host is `code_eval`: write the event-ordering check as user Python using the `kiln.get_tool_calls()` and trace-navigation helpers. No separate event-ordering DSL needs to be invented preemptively.

Example of an event-ordering check via code_eval:

```python
def score(output, trace, reference_data, task_input, kiln):
    tool_calls = kiln.get_tool_calls(trace)
    tool_names = [tc["name"] for tc in tool_calls]

    # Verify: search happened before summarize
    search_idx = next((i for i, n in enumerate(tool_names) if n == "search"), None)
    summarize_idx = next((i for i, n in enumerate(tool_names) if n == "summarize"), None)

    ordered = (search_idx is not None and summarize_idx is not None
               and search_idx < summarize_idx)
    return {"correct_order": kiln.pass_fail(ordered)}
```

If this pattern recurs across many projects, it signals demand for a typed `event_ordering` built-in type (per B.14's promotion path).

---

## 10. Implementation phasing (PLAN.md Phase 5)

Per PLAN.md Phase 5 and B.13's implementation budget:

1. **`sandbox_worker.py`** + **`eval_helpers.py`** -- thin worker module + helper library. Lint/CI rule preventing heavy Kiln imports.
2. **`freeze_support()` wiring** -- first line of main entry point.
3. **Linux `spawn` start method** -- explicit `set_start_method("spawn")`.
4. **`CodeEvalAdapter`** -- wired into `_V2_ADAPTER_MAP` (components/20 section 2.2).
5. **Save-time validation** -- syntax check, size cap, result-assignment check.
6. **Trust-gate backend** -- `/grant_code_eval_trust` endpoint + `_trusted_projects` dict.
7. **Unix rlimits (P2)** -- cut if any complexity.
8. **Spawn lock** -- `_SPAWN_LOCK` for thread-safety.
9. **Test-run API** -- server endpoint for the G.2 test pane; same `run_scorer` path, result not persisted.
10. **Light spike at Phase 5 start** -- validate cold-start time on actual Kiln-sized bundle (target 50-150ms); confirm spawn works in PyInstaller on macOS/Linux/Windows.

---

## Alignment reference coverage

| Ref | Decision | Coverage |
|---|---|---|
| A0.3 | Config-first; code is escape hatch | Section 1 (code_eval is the escape hatch, not the default; inline code keeps it config-like) |
| A0.4 | Local-first; PyInstaller bundle stays clean | Section 4 (stdlib multiprocessing, 0 MB overhead; no WASM) |
| B.12 | Hybrid: config-first, code_eval as additional type | Section 1 (CodeEvalProperties shape); Section 5 (CodeEvalAdapter) |
| B.13 | Execution model: multiprocessing spawn + freeze_support + trust-gate UX | Section 4 (full execution model detail, followed exactly) |
| B.14 | event_ordering deferred; host on code_eval | Section 9 (example implementation) |
| G.2 | Code-eval create UI | Section 2 (scorer contract gates gallery content); Section 7 (trust-gate coordination) |

---

## Opens

None. All alignment_refs are fully covered. The scorer contract (section 2) resolves `O-codeeval-scorer-contract` -- `components/70` can remove that open from its frontmatter and finalize its examples-gallery content using the examples in section 2.4.
