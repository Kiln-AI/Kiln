# Cluster K — code_eval scorer contract & helper library

Skeptic review of findings from `unit_27-code-eval.md`, components/27 section 2.

---

## 27-R14: Range validation at execution time vs. persist time

**Skeptic verdict:** UPHELD_DOWNGRADE
**Corrected verdict:** PARTIAL
**Corrected severity:** minor

**Reasoning:** The spec (§2.2 error table) says a float outside valid range yields `Score.failed(reason=...)` at execution time. The code omits range validation in `_validate_scores` (`v2_eval_code_eval.py:105-127`). However, the **batch eval runner** creates an `EvalRun(scores=scores)` which triggers the Pydantic `model_validator` at `eval.py:530-587` -- this catches out-of-range values and raises `ValueError`. The divergence is real but narrowly scoped: only the **test pane** (which returns scores via `TestV2EvalResponse` at `eval_api.py:999`) skips range validation, so out-of-range scores silently pass through in the test-run preview. User impact is minor: a scorer returning 6.0 for a five_star would look OK in the test pane but fail when the batch runner tries to persist it.

**Evidence:**
- `v2_eval_code_eval.py:105-127` — no range check.
- `eval.py:530-587` — `EvalRun.validate_scores` checks ranges at persist time.
- `eval_api.py:996-1003` — test endpoint returns scores without `EvalRun` construction.
- Spec §2.2 error table row: "A float value is outside the valid range…"

---

## 27-R20: `kiln.get_tool_calls` returns raw trace entries, not normalized dicts

**Skeptic verdict:** UPHELD
**Corrected verdict:** PARTIAL
**Corrected severity:** major (upgraded from minor)

**Reasoning:** This is more severe than the initial reviewer assessed. The spec (§3.1) says `get_tool_calls` returns dicts with `name`, `arguments`, `id`. The code (`eval_helpers.py:16-24`) filters for entries where `role == "tool_call"` or `type == "tool_call"`. But the actual Kiln trace format uses the OpenAI convention: tool calls are nested inside `role: "assistant"` messages under `tool_calls: [{function: {name, arguments}, id}]`. Evidence:

1. `v2_eval_tool_call_check.py:41-66` — the built-in ToolCallCheckEval correctly extracts tool calls from `role: "assistant"` messages via `msg.get("tool_calls")` and normalizes to `{name, arguments}`.
2. `test_litellm_adapter_tools.py:110-123` — confirms real traces have `trace[2]["role"] == "assistant"` with `trace[2]["tool_calls"][0]["function"]["name"]`.
3. `EvalTaskInput.from_task_run` (`eval.py:338-340`) copies `task_run.trace` directly — no format conversion.

The shipped example code (spec §2.4 "Check tool usage"; frontend `code_eval_helpers.ts:199-203`) uses `kiln.get_tool_calls(trace)` followed by `kiln.has_tool_call(tool_calls, "search")`. The tests pass only because `test_code_eval_samples.py:294-297` uses a synthetic trace with `role: "tool_call"` entries — a format that does NOT occur in real Kiln traces. In a real batch eval run, `get_tool_calls` would return an empty list for any trace containing tool calls, and the example code would silently report no tool calls found.

The spec §9 event-ordering example also uses `tc["name"]` on the output of `get_tool_calls`, which would likewise break with real traces.

This is a user-facing contract mismatch + shipped example that will fail in production. Severity: **major**.

**Evidence:**
- `eval_helpers.py:16-24` — filters `role == "tool_call"`.
- `v2_eval_tool_call_check.py:41-66` — correct extraction from `role: "assistant"` + `msg.get("tool_calls")`.
- `test_code_eval_samples.py:294-297` — test uses `role: "tool_call"` (not the real trace format).
- `test_litellm_adapter_tools.py:110-123` — real trace uses `role: "assistant"` with nested `tool_calls`.
- Spec §9 example: `tool_names = [tc["name"] for tc in tool_calls]`.

---

## 27-R21: `kiln.get_assistant_messages` returns `list[dict]` not `list[str]`

**Skeptic verdict:** UPHELD
**Corrected verdict:** PARTIAL
**Corrected severity:** minor

**Reasoning:** The spec (§3.1) says `get_assistant_messages(trace) -> list[str]` — "Returns the content strings from all assistant-role messages." The code (`eval_helpers.py:27-33`) returns full message dicts (`list[dict[str, Any]]`), not content strings. The test at `test_eval_helpers.py:51` confirms: `msgs[0]["content"] == "Hello"` (dict access).

No shipped example uses `get_assistant_messages` directly, so this doesn't break any gallery code. User code following the spec signature would call e.g. `for msg in kiln.get_assistant_messages(trace): print(msg)` expecting strings and get dicts instead. Impact is minor because: (a) users can adapt quickly, (b) no example code breaks.

**Evidence:**
- Spec §3.1: `kiln.get_assistant_messages(trace: list[dict] | None) -> list[str]`
- `eval_helpers.py:27-33` — return type is `list[dict[str, Any]]`.
- `test_eval_helpers.py:51` — `msgs[0]["content"]` shows dict return.

---

## 27-R41: Trust check returns skip tuple instead of raising `CodeEvalNotTrustedError`

**Skeptic verdict:** UPHELD_DOWNGRADE
**Corrected verdict:** PARTIAL
**Corrected severity:** trivial

**Reasoning:** The spec (§5.1) says `raise CodeEvalNotTrustedError(...)`. The code (`v2_eval_code_eval.py:61-65`) returns `(SkippedReason.code_eval_not_trusted, ...)` instead. However, the skip reason propagates correctly:

1. **Test pane:** `create_eval_config/+page.svelte:267` checks `result.skipped_reason === "code_eval_not_trusted"` and shows the trust dialog.
2. **Batch runner:** `eval_runner.py:480-481` passes `skipped_reason.value` into the `EvalRun` persist, so the skip is recorded properly.

The skip-tuple approach is functionally equivalent and arguably cleaner than exception-based flow control. No user-visible behavior difference. Severity downgraded to trivial — this is an implementation style choice, not a defect.

**Evidence:**
- Spec §5.1: `raise CodeEvalNotTrustedError(...)`.
- `v2_eval_code_eval.py:61-65` — returns skip tuple.
- `+page.svelte:267` — frontend handles `code_eval_not_trusted` skip reason.

---

## 27-R46: Extra `revoke_code_eval_trust` function exists

**Skeptic verdict:** UPHELD_DOWNGRADE
**Corrected verdict:** PARTIAL
**Corrected severity:** trivial

**Reasoning:** The spec (§7.1) says "There is no revoke endpoint." The code (`v2_eval_code_eval.py:32-33`) has a `revoke_code_eval_trust` function. However, it is NOT exposed via any HTTP endpoint — no route in `eval_api.py` calls it. It's an internal utility function, not a violation of the spec's "no revoke endpoint" intent. The spec says trust clears on app restart, and this function exists as defensive infrastructure (e.g., for future testing or cleanup). Harmless and consistent with the spec's intent.

**Evidence:**
- Spec §7.1: "There is no revoke endpoint — closing the app window clears trust."
- `v2_eval_code_eval.py:32-33` — function exists.
- `eval_api.py` — no HTTP route exposes `revoke_code_eval_trust`.
