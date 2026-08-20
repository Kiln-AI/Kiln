# Spec-Fidelity Review: Unit 27-code-eval — Type: code_eval (Beta)

**Spec file:** `components/27_type_code_eval.md`
**Reviewer:** spec-fidelity audit agent

---

## Summary

Requirements: 52 total — MET 40, PARTIAL 4, MISSING 3, CONTRADICTED 2, DEFERRED_OK 2, CANNOT_VERIFY 1

---

## Requirements Table

### Section 1: CodeEvalProperties shape

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|----|----------|---------|----------|-------------|----------------------|----------|------------|
| 27-R01 | data_model | MET | — | CodeEvalProperties has `type: Literal["code_eval"]` field | §1.1 | `libs/core/kiln_ai/datamodel/eval.py:193` — `type: Literal[V2EvalType.code_eval] = V2EvalType.code_eval` | — |
| 27-R02 | data_model | MET | — | CodeEvalProperties has `code: str` field | §1.1 | `eval.py:194` — `code: str` | — |
| 27-R03 | data_model | MET | — | CodeEvalProperties has `timeout_seconds: int = Field(default=30, ge=1, le=300)` | §1.1 | `eval.py:195` — `timeout_seconds: int = Field(default=30, ge=1, le=300)` | — |
| 27-R04 | validation | MET | — | Save-time syntax check via `compile(code, "<code_eval>", "exec")` | §1.3 | `eval.py:206-208` — `compile(self.code, "<code_eval>", "exec")` | — |
| 27-R05 | validation | MET | — | Save-time size cap: `len(code.encode("utf-8")) <= 64 * 1024` | §1.3 | `eval.py:199-202` — `len(code_bytes) > 64 * 1024` | — |
| 27-R06 | validation | MET | — | Save-time `score` function definition check via AST walk at module scope | §1.3 | `eval.py:210-221` — `ast.parse` + checks for `FunctionDef` named `score` | — |
| 27-R07 | validation | MET | — | No import allowlist or AST gating per B.13 | §1.3 | No AST import checks in code. Confirmed. | — |

### Section 2: Scorer contract

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|----|----------|---------|----------|-------------|----------------------|----------|------------|
| 27-R08 | contract | MET | — | `score` function receives 5 args: output, trace, reference_data, task_input, kiln | §2.1 | `sandbox_worker.py:68-74` — calls `score_fn(output=..., trace=..., reference_data=..., task_input=..., kiln=helpers)` | Spec says "five positional arguments", code passes as keyword args. Functionally equivalent; user code using positional definition still works. MET. |
| 27-R09 | contract | MET | — | Return shape is `dict[str, float]` whose keys match `output_scores` names | §2.2 | `v2_eval_code_eval.py:106-108` — `_validate_scores` requires exact key match | — |
| 27-R10 | contract | MET | — | Strict exact-key-match: missing or extra keys both raise RuntimeError | §2.2 | `v2_eval_code_eval.py:109-111` — raises `RuntimeError(f"Score key mismatch: got {sorted(actual_keys)}, expected {sorted(expected_keys)}")` | — |
| 27-R11 | contract | MET | — | bool value is rejected explicitly (not coerced) | §2.2 | `v2_eval_code_eval.py:115-118` — `if isinstance(value, bool): raise RuntimeError(...)` | — |
| 27-R12 | contract | MET | — | int values silently coerced to float | §2.2 | `v2_eval_code_eval.py:119-120` — `if isinstance(value, int): value = float(value)` | — |
| 27-R13 | contract | MET | — | Non-numeric type raises RuntimeError | §2.2 | `v2_eval_code_eval.py:121-123` — `if not isinstance(value, float): raise RuntimeError(...)` | — |
| 27-R14 | contract | MISSING | minor | Float value outside valid range for its rating type -> `Score.failed(reason="Score '<key>' value <v> is outside valid range [<min>, <max>]")` | §2.2 error table | `v2_eval_code_eval.py` — `_validate_scores` does NOT check range. No `_validate_range` method exists. Range is only validated later by EvalRun's model_validator on persist. | No per-score range validation in the adapter at execution time as spec requires. The spec illustrates `self._validate_range(float(val), score_spec)` but this is absent from the implementation. |
| 27-R15 | contract | MET | — | `score` function not defined or not callable -> error message about missing score function | §2.2 | `sandbox_worker.py:49-66` — checks and puts error in queue | — |
| 27-R16 | contract | MET | — | `score()` did not return a dict -> RuntimeError | §2.2 | `v2_eval_code_eval.py:88-91` — `if not isinstance(raw_scores, dict): raise RuntimeError(...)` | — |
| 27-R17 | contract | MET | — | `score()` raises exception -> error with message | §2.2 | `sandbox_worker.py:83-91` — `except Exception: result_queue.put({"error": ...})` | — |
| 27-R18 | contract | MET | — | Worker crashes (nonzero exit, empty queue) -> error with exit code | §2.2 | `sandbox_worker.py:125-126` — `raise RuntimeError(f"Scorer crashed (exit code {p.exitcode})")` | — |
| 27-R19 | contract | MET | — | Wall-clock timeout -> error with timeout message | §2.2 | `sandbox_worker.py:117-120` — `raise RuntimeError(f"Code eval scorer timed out after {timeout}s")` | — |

### Section 3: Helper library (KilnEvalHelpers)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|----|----------|---------|----------|-------------|----------------------|----------|------------|
| 27-R20 | helper | PARTIAL | minor | `kiln.get_tool_calls(trace) -> list[dict]` returns flat list of all tool-call dicts with `name`, `arguments`, `id` fields | §3.1 | `eval_helpers.py:16-23` — returns entries where `role == "tool_call"` or `type == "tool_call"`. Does NOT extract `name`/`arguments`/`id` fields; returns raw trace entries. | Spec says each dict has `name: str`, `arguments: dict|str`, `id: str`. Code returns raw trace dicts which may have different shapes (e.g., `tool_name` instead of `name`). The `has_tool_call` method compensates by checking both `name` and `tool_name`, but `get_tool_calls` itself doesn't normalize. |
| 27-R21 | helper | PARTIAL | minor | `kiln.get_assistant_messages(trace) -> list[str]` returns content strings | §3.1 "Returns the content strings from all assistant-role messages" | `eval_helpers.py:27-33` — returns `list[dict[str, Any]]` (full message dicts), not `list[str]` | Spec says return type is `list[str]` (content strings). Code returns `list[dict]` (full message objects). |
| 27-R22 | helper | MET | — | `kiln.get_tool_results(trace) -> list[dict]` with `tool_call_id` and `content` | §3.1 | `eval_helpers.py` — matches OpenAI-dialect `role == "tool"` messages (the shape Kiln stores; carries `tool_call_id` + `content`), plus legacy `role`/`type == "tool_result"` defensively. Prior matching (`tool_result` only) never occurred in real traces and always returned `[]` — fixed 2026-07-13 (PR #1568 remediation). | — |
| 27-R23 | helper | MET | — | `kiln.has_tool_call(tool_calls, tool_name, expected_args=None) -> bool` | §3.2 | `eval_helpers.py:48-68` — signature matches, subset comparison implemented | — |
| 27-R24 | helper | MET | — | `kiln.count_tool_calls(tool_calls, tool_name=None) -> int` | §3.2 | `eval_helpers.py:70-82` — signature matches | — |
| 27-R25 | helper | MET | — | `kiln.pass_fail(passed: bool) -> float` returns 1.0/0.0 | §3.3 | `eval_helpers.py:86-89` — `return 1.0 if passed else 0.0` | — |
| 27-R26 | helper | MET | — | `kiln.five_star(rating: int) -> float` raises ValueError if not in [1,5] | §3.3 | `eval_helpers.py:91-101` — raises ValueError, accepts int|float | — |
| 27-R27 | helper | MET | — | `kiln.assert_contains(text, substring) -> bool` case-sensitive, does not raise | §3.4 | `eval_helpers.py:105-110` — returns `needle in haystack`, wrapped in try/except | — |
| 27-R28 | helper | MET | — | `kiln.assert_not_contains(text, substring) -> bool` does not raise | §3.4 | `eval_helpers.py:112-117` | — |
| 27-R29 | helper | MET | — | `kiln.assert_matches(text, pattern) -> bool` via `re.search`, does not raise | §3.4 | `eval_helpers.py:119-128` | — |
| 27-R30 | helper | MET | — | Helper library is plain Python, no Pydantic / Kiln model imports | §3.5 | `eval_helpers.py:1-8` — imports only `re` and `typing.Any` | — |
| 27-R31 | helper | MET | — | All functions are synchronous | §3.5 | Confirmed: all methods are `@staticmethod`, no async | — |

### Section 4: Execution model

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|----|----------|---------|----------|-------------|----------------------|----------|------------|
| 27-R32 | execution | MET | — | `multiprocessing.Process` with spawn start method | §4.1, §4.2 | `sandbox_worker.py:110` — `ctx = multiprocessing.get_context("spawn")` | — |
| 27-R33 | execution | MET | — | Wall-clock timeout via `p.join(timeout)` + `p.kill()` | §4.2 | `sandbox_worker.py:115-119` | — |
| 27-R34 | execution | MET | — | `freeze_support()` called at entry point | §4.3 | `app/desktop/desktop.py:186` — `multiprocessing.freeze_support()` as first line in `__main__`; also `dev_server.py:25` | — |
| 27-R35 | execution | MET | — | Linux spawn start method set explicitly | §4.3 | `app/desktop/desktop.py:187` — `multiprocessing.set_start_method("spawn", force=True)` | — |
| 27-R36 | execution | DEFERRED_OK | — | Unix rlimits (P2, cut if complexity arises) | §4.4 "P2 -- cut if any complexity" | Not implemented in `sandbox_worker.py`. Spec explicitly says P2/cut. | — |
| 27-R37 | execution | MET | — | Spawn lock for thread-safety (concurrent spawns serialized) | §4.6 | `sandbox_worker.py:15,112` — `_spawn_lock = threading.Lock()`, used with `with _spawn_lock:` around Process creation | — |
| 27-R38 | execution | MET | — | Worker module is thin: no UI/DB/model-registry imports | §4.2 | `sandbox_worker.py:1-13` — imports only stdlib + `threading`; `KilnEvalHelpers` imported inside `_execute_scorer` function | — |
| 27-R39 | execution | MET | — | stdout/stderr captured via io.StringIO; handles PyInstaller --windowed None stdout | §4.2, §6.2 | `sandbox_worker.py:33-39` — captures stdout/stderr before exec | — |

### Section 5: CodeEvalAdapter

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|----|----------|---------|----------|-------------|----------------------|----------|------------|
| 27-R40 | adapter | MET | — | CodeEvalAdapter subclasses BaseEval (or equivalent) | §5.1 | `v2_eval_code_eval.py:42` — `class CodeEvalAdapter(BaseV2EvalBridge)` which itself extends `BaseEval` | — |
| 27-R41 | adapter | PARTIAL | minor | Trust check: if not trusted, raise `CodeEvalNotTrustedError` | §5.1 "raise CodeEvalNotTrustedError" | `v2_eval_code_eval.py:61-65` — returns `(SkippedReason.code_eval_not_trusted, ...)` tuple instead of raising an exception. Functionally works (frontend handles both), but differs from spec's "raise" approach. | Returns skip tuple instead of raising exception. |
| 27-R42 | adapter | MET | — | Input serialization: output, trace, reference_data, task_input as plain types | §5.2 | `v2_eval_code_eval.py:68-73` — constructs dict with these four keys | — |
| 27-R43 | adapter | MET | — | Async lock serializes code_eval executions | §4.6 + §5.1 | `v2_eval_code_eval.py:24,75` — `_code_eval_execution_lock = asyncio.Lock()`, used with `async with` | — |

### Section 7: Trust gate

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|----|----------|---------|----------|-------------|----------------------|----------|------------|
| 27-R44 | trust | MET | — | Trust state is ephemeral, in-memory, cleared on app restart | §7.1 | `v2_eval_code_eval.py:22` — `_trusted_projects: set[str] = set()` module-level, no persistence | — |
| 27-R45 | trust | MET | — | `/grant_code_eval_trust` API endpoint sets trust | §7.1 | `eval_api.py:1743-1756` — POST endpoint calls `grant_code_eval_trust(str(project.path))` | — |
| 27-R46 | trust | PARTIAL | minor | No revoke endpoint; spec says "closing the app window clears trust" | §7.1 "There is no revoke endpoint" | `v2_eval_code_eval.py:32-33` — `revoke_code_eval_trust` function exists (contradicts spec's "no revoke endpoint"). However, no HTTP endpoint exposes it and trust clears on restart. | Extra `revoke_code_eval_trust` function exists but is not exposed via API; technically harmless. |
| 27-R47 | trust | CONTRADICTED | major | Trust modal copy: "never paste code from a stranger or the internet here" + explains filesystem/network access | §7.3 "Per G.2: 'never paste code from a stranger or the internet here.' The modal explains that code runs with the user's filesystem and network access." | `create_eval_config/+page.svelte:716-721` — Modal says: "This eval runs Python code on your machine. Only proceed if you trust eval code inside this project." | Missing required phrasing about never pasting from strangers/internet. Does not mention filesystem or network access as spec requires. |

### Frontend (cross-ref to components/70 G.2 requirements within this unit's scope)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|----|----------|---------|----------|-------------|----------------------|----------|------------|
| 27-R48 | UX | MET | — | CodeMirror 6 with `@codemirror/lang-python`, lazy-loaded | components/70 §2 "CodeMirror 6 with @codemirror/lang-python — Python only" | `code_editor.svelte:19,25` — dynamic imports of `@codemirror/lang-python`, loaded in `onMount` | — |
| 27-R49 | UX | MISSING | minor | "Python" label top-left of the editor box | components/70 §2 "'Python' label top-left of the box" | `code_editor.svelte` — no "Python" label rendered anywhere. `code_eval_form.svelte:79` — label says "Score Function" | Spec requires visible "Python" label on the editor; not implemented. |
| 27-R50 | UX | MET | — | Loads with a minimal valid eval example on open | components/70 §2 + spec 27 §2.3 | `code_eval_form.svelte:15` — `code: generate_default_code(output_scores)` | — |
| 27-R51 | UX | MET | — | "See examples" tabbed modal with multiple cases | components/70 §2 + spec 27 §2.4 | `code_eval_form.svelte:118-152` — Dialog with tabs, each showing example code | — |
| 27-R52 | UX | CONTRADICTED | minor | Each example tab has "Use this template" button | components/70 §2 "each with a 'Use this template' button" | `code_eval_form.svelte:128` — button labeled "Use This Example" | Button text says "Use This Example" instead of spec-required "Use this template". |
| 27-R53 | UX | DEFERRED_OK | — | Format/lint buttons are cut | components/70 §2 "Format / lint buttons are cut" | Not present in code. Correctly omitted. | — |
| 27-R54 | UX | MET | — | Beta label on code_eval form | components/70 §2 "Beta label under the header" | `code_eval_form.svelte:68-69` — `<span class="badge...">Beta</span>` | — |
| 27-R55 | UX | MET | — | "Save Without Testing" confirm modal exists | components/70 §Save | `create_eval_config/+page.svelte:725-747` — Dialog titled "Save Without Testing?" | — |
| 27-R56 | UX | MISSING | minor | "Save Without Testing" modal copy: "I know, you're a great coder, but it never hurts to run it once." | components/70 §Save | `+page.svelte:743-745` — actual copy: "You haven't tested this judge yet. Running a quick test helps catch issues before saving. Are you sure you want to save without testing?" | Spec mandates specific whimsical copy; implementation uses different wording. |
| 27-R57 | UX | MISSING | minor | "Save Without Testing" modal buttons: red "Save Without Testing" / "Cancel" | components/70 §Save "Buttons: red Save Without Testing / Cancel" | `+page.svelte:731-732` — buttons are "Cancel" and "Save Anyway" (with `isError: true` for red styling) | Button label is "Save Anyway" not "Save Without Testing" as spec requires. |
| 27-R58 | UX | CANNOT_VERIFY | — | CodeMirror built as reusable component | components/70 §2 "Built as a reusable component" | `code_editor.svelte` exists as standalone component in `$lib/components/` — appears reusable. Cannot fully verify no other code-eval-specific coupling without exhaustive search. Likely MET. | — |

---

## Verifier-Added Requirements (source: verifier_added)

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Location | Evidence | Divergence |
|----|----------|---------|----------|-------------|----------------------|----------|------------|
| 27-R59 | contract | MET | — | Spec 27 §2.1: `kiln` parameter is a `KilnEvalHelpers()` instance | §2.1 | `sandbox_worker.py:43,73` — `helpers = KilnEvalHelpers()`, passed as `kiln=helpers` | — |
| 27-R60 | contract | MET | — | Spec 27 §6.3: Worker puts exactly one dict on the queue | §6.3 | `sandbox_worker.py` — all paths put exactly one dict (success at :76, missing-fn at :50/:59, exception at :84) | — |
