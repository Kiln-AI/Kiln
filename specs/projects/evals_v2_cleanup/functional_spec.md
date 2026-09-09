---
status: complete
---

# Functional Spec: Evals V2 cleanup

## 0. Scope

Eight discrete fixes from the Evals V2 spec-fidelity review (2026-06-23), all now **ship-blocker** (D27/D29 promoted from post-ship per scosman, 2026-06-24). None touch the eval **create container** owned by Project 1 — this project is parallel-safe with it.

| ID | Surface | One-liner |
|----|---------|-----------|
| D14 | backend (`eval_helpers.py`) | `get_tool_calls()` must read real OpenAI-format traces |
| D15 | backend (`eval_helpers.py`) | `get_assistant_messages()` must return `list[str]` |
| D27 | backend (`eval.py`) | `expected_tools` non-empty at save |
| D28 | backend (`eval.py`) | `ArgMatch` regex compiled at save |
| D29 | backend (`eval.py`) | `reference_key` `min_length=1` at save |
| D30 | backend (`eval.py`) | useless-template check is AST-based, not a `{{`-scan |
| D31 | backend + frontend | surface V2 `llm_judge` reasoning in run results |
| D35 | frontend | warning when `n_excluded > 0` on aggregate views |

Decision provenance: [`DECISIONS.md`](../evals_v2/spec_fidelity_review/DECISIONS.md). Evidence: `confirm_K.md` (D14/D15), `confirm_J.md` (D27–D30), `confirm_H.md` (D31), `confirm_L.md` (D35).

---

## 1. Cross-cutting contract change: `V2EvalResult` (enables D31)

Today every V2 adapter implements `evaluate(eval_input) -> tuple[EvalScores, SkippedReason | None, str | None]` and the `llm_judge` adapter **discards** the judge model's chain-of-thought (`v2_eval_llm_judge.py:165` gets `run_output` but drops `run_output.intermediate_outputs`). There is no channel to carry reasoning to storage.

**Change:** replace the 3-tuple return with a typed object.

```python
class V2EvalResult(BaseModel):
    scores: EvalScores
    skipped_reason: SkippedReason | None = None
    skipped_detail: str | None = None
    intermediate_outputs: dict[str, str] | None = None
```

- **Producers (all 8 V2 adapters):** return `V2EvalResult(...)`. Only `llm_judge` populates `intermediate_outputs` (from the judge run's `intermediate_outputs`, e.g. `{"chain_of_thought": "..."}`). The other 7 leave it `None`.
- **Consumers (5 call sites):**
  - `base_eval.py:249` (`BaseV2EvalBridge.run_eval`) — on skip still raises; otherwise returns `(result.scores, result.intermediate_outputs)` so the fresh-generation path also propagates reasoning.
  - `eval_runner.py` `_run_v2_job` — **3 branches** (`from_eval_input`, `task_run_eval`, default `eval_config_eval`) read `result.*` and pass `intermediate_outputs=result.intermediate_outputs` into the constructed `EvalRun`. (Today these branches build `EvalRun` with no `intermediate_outputs` at all.)
  - `eval_api.py:996` (`test_v2_eval`) — reads `result.*` and includes reasoning in the response (§6).

This is an internal contract; no datamodel/storage migration (`EvalRun.intermediate_outputs` already exists and is `dict[str,str] | None`).

---

## 2. D14 / D15 — `KilnEvalHelpers` trace navigation

`KilnEvalHelpers` (`eval_helpers.py`) is a stdlib-only utility set users import into code-eval scorers. Two methods read traces incorrectly. The shipped code-eval example gallery depends on `get_tool_calls`.

### 2.1 The real trace format

Kiln traces follow the OpenAI convention. Tool calls are **not** top-level entries; they are nested inside `role: "assistant"` messages:

```jsonc
{
  "role": "assistant",
  "content": null,
  "tool_calls": [
    {"id": "call_1", "type": "function",
     "function": {"name": "search", "arguments": "{\"q\": \"cats\"}"}}
  ]
}
```

The correct extraction already exists at `v2_eval_tool_call_check.py:41-66` — reuse that logic (extract `function.name`, JSON-parse `function.arguments`).

### 2.2 `get_tool_calls(trace) -> list[dict]`

- **Today (broken):** filters entries where `role == "tool_call"` or `type == "tool_call"` — a shape that **never occurs** in real traces → returns `[]` for any real tool-using trace. Tests passed only because `test_code_eval_samples.py:294` used a synthetic `role: "tool_call"` trace.
- **Fixed:** iterate `role == "assistant"` messages, flatten each `tool_calls` entry to:
  ```python
  {"name": <function.name or "">,
   "arguments": <json.loads(function.arguments) → dict, {} on parse failure>,
   "id": <tool_call.id or None>}
  ```
  - `name` and `arguments` keys are what `has_tool_call` / `count_tool_calls` consume — keep those methods working unchanged.
  - `id` is added to match the spec §3.1 contract (`name`, `arguments`, `id`).
  - `arguments` is always a `dict` (parsed from the JSON string; `{}` on `JSONDecodeError`/`TypeError` or non-dict result).
  - `None` / empty trace → `[]`.

### 2.3 `get_assistant_messages(trace) -> list[str]`

- **Today (wrong type):** returns `list[dict]` (full assistant entries).
- **Fixed:** return the **content string** of each `role == "assistant"` message. Messages whose `content` is missing or not a string (e.g. a tool-call-only assistant turn with `content: null`) are **omitted** from the list. `None` / empty trace → `[]`.
- Breaking signature change, but it matches the documented spec contract and **no shipped gallery example** calls this method → safe.

### 2.4 Quality gate (hard requirement)

Approval of D14/D15 **requires a manual run** of both methods against a **real Kiln trace containing actual tool calls** (e.g. captured from a live tool-using task run), confirming `get_tool_calls` returns the calls and `get_assistant_messages` returns content strings. Agent-authored fixtures are **insufficient** — the original bug shipped precisely because tests used a fabricated trace shape. Unit tests must additionally include a real-format fixture (assistant + nested `tool_calls`), replacing/augmenting the synthetic `role: "tool_call"` fixture.

---

## 3. D27–D30 — save-time validators in `eval.py`

All four add validation to V2 `*Properties` (or the `EvalConfig` template validator) so footguns fail at **save** time rather than silently misbehaving at runtime. Backend-only. They share `eval.py` with Project 1's `set_check` enum work but touch **different classes** — coordinate, low conflict risk.

### 3.1 D28 — `ArgMatch` regex compiled at save (was ship-blocker)

- **Where:** `ArgMatch` (`eval.py:154-156`), `match_mode == "regex"`.
- **Behavior:** add a `model_validator(mode="after")` that, when `match_mode == "regex"`, calls `re.compile(str(value))` and raises `ValueError` with a clear message on `re.error`. Mirror the existing `PatternMatchProperties.validate_pattern` (`eval.py:114-122`).
- **Why insidious:** runtime wraps `re.search` in `try/except re.error` returning `False` (`v2_eval_tool_call_check.py:161-164`) — an invalid regex **silently never matches**, with no feedback.

### 3.2 D30 — AST-based useless-template check (was ship-blocker)

- **Where:** `EvalConfig.validate_v2_templates_and_expressions`, the `LlmJudgeProperties` branch (`eval.py:706-712`).
- **Today:** surface scan — `if "{{" not in tmpl and "{%" not in tmpl: raise`. Catches only the zero-variable case.
- **Bypass it misses:** `{{ reference_data.expected_output }}` contains `{{` so it passes, yet references only `reference_data` — the rendered judge prompt is **identical regardless of model output**, making the eval meaningless.
- **Fixed:** parse the template AST and inspect top-level variable references. The render namespace is exactly `EvalTaskInput.model_dump()` = `{final_message, trace, reference_data, task_input}`. Reject the save unless **at least one** referenced top-level variable is in `{final_message, trace, task_input}` (i.e. not `reference_data`-only and not variable-free).
  - Implementation: `jinja2.meta.find_undeclared_variables(_template_env.parse(prompt_template))` returns the set of top-level names; a sub-path like `trace[0].content` still surfaces top-level `trace`. Require `referenced ∩ {final_message, trace, task_input} ≠ ∅`.
  - Error message must explain the template never reads model output and suggest e.g. `{{ final_message }}`.
- Keep the existing `compile_template_or_raise` call (syntax check) ahead of this check.

### 3.3 D27 — `expected_tools` non-empty at save (promoted to ship-blocker)

- **Where:** `ToolCallCheckProperties.expected_tools` (`eval.py:166`).
- **Behavior:** require non-empty (`min_length=1` or a `model_validator`), raising a clear `ValueError` on empty.
- **Why:** empty list → vacuous pass for `all`/`ordered`/`never`, always-fail for `any` — a check that silently always passes/fails by mode.

### 3.4 D29 — `reference_key` `min_length=1` at save (promoted to ship-blocker)

- **Where:** the three `reference_key: str | None` fields — `ExactMatchProperties` (`eval.py:96`), `ContainsProperties` (`eval.py:129`), `SetCheckProperties` (`eval.py:144`).
- **Behavior:** when set, must be non-empty. `None` remains valid (the XOR validators allow exactly one of `reference_key` / `expected_value` to be `None`); only an **empty string** is newly rejected. Use `min_length=1` on the field (preserving the `| None`), or a validator — whichever keeps the existing XOR semantics intact.
- **Why:** `""` is not `None`, so it passes the XOR check today, then always skips at runtime (`"" not in reference_data`).

### 3.5 Shared notes

- Each validator must produce a user-facing `ValueError` message suitable for surfacing in the create UI's save error.
- These all run at `EvalConfig`/`*Properties` construction, so they gate **both** the persisted-save path and the `test_v2_eval` transient-config path (which builds an `EvalConfig`).

---

## 4. D31 — surface V2 `llm_judge` reasoning in run results

### 4.1 Backend (capture + persist + expose)

- `LlmJudgeEval.evaluate` populates `V2EvalResult.intermediate_outputs` from the judge run's `intermediate_outputs` (the `SIMPLE_CHAIN_OF_THOUGHT` judge produces `chain_of_thought`). On skip, `intermediate_outputs` stays `None`.
- `_run_v2_job` persists it to `EvalRun.intermediate_outputs` across all three V2 branches (§1).
- All other V2 types (`code_eval` included) carry `None` — **no model reasoning exists** for them. `code_eval` stdout capture is **out of scope**.

### 4.2 Frontend (display) — run-result detail page only

- **Location:** the per-type renderer `llm_judge_result.svelte` (the "Result" cell of the run-result table at `run_result/+page.svelte`). Not a re-enabled column.
- **Mechanism:** pass `intermediate_outputs` (from `result.intermediate_outputs`) as a new prop to the V2 result component. `llm_judge_result.svelte` renders a **"View reasoning"** affordance when reasoning is present; clicking it **opens a modal** (reuse the existing `Dialog` pattern — same family as `thinking_dialog`) showing the full `reasoning`/`chain_of_thought` text. **Not** an inline expand/collapse.
- Renderers for types without reasoning (`code_eval` etc.) render no reasoning affordance.
- The legacy V1 "Thinking" column behavior is unchanged.

### 4.3 Test pane (boundary)

- `test_v2_eval` returns `intermediate_outputs` on `TestV2EvalResponse` (backend only — §6). Building the Test-Your-Judge pane's reasoning UI is **Project 1's** create-container surface and is **out of scope here**; we only make the data available.

### 4.4 Non-goals for D31

- No reasoning on aggregate/compare views (those show mean scores across many runs — per-run reasoning doesn't belong there).
- No new datamodel field; `EvalRun.intermediate_outputs` already exists.

---

## 5. D35 — `n_excluded` warning on aggregate views

When some dataset cases were skipped/excluded, aggregate scores silently understate coverage. Surface a warning so the mean isn't misread.

### 5.1 Behavior

- **Trigger:** `n_excluded > 0` for a run config (or judge, on the judge-comparison surface).
- **UI:** a small **info "(i)" symbol** (info-circle glyph; reuse the existing `InfoTooltip` affordance pattern at `$lib/ui/info_tooltip.svelte`, which the compare view already imports) carrying a **tooltip** with the count, e.g. *"{n_excluded} of {n_used + n_excluded} cases were skipped and are not reflected in this score."*
- **Color by severity (skip ratio = `n_excluded / (n_used + n_excluded)`):**
  - `> 0%` and `≤ 20%` → **yellow** (warning color).
  - `> 20%` → **red** (error color).
- **Distinct** from the existing `percent_complete < 1.0` "incomplete" warning (missing runs) — both can appear; they describe different conditions. Place the (i) symbol near the affected run-config row / score cell.

### 5.2 Surfaces & data

- **Primary — compare view** (`run_config_comparison_table.svelte`, `EvalResultSummary`): `n_excluded` lives in each `ScoreSummary` (`results[run_config_id][score_key].n_excluded`) and is identical across a run config's score keys (set per run config at `eval_api.py:605`). Read it once per run-config row.
- **Secondary — judge-comparison view**: `RunConfigEvalResult.n_excluded` (`eval_api.py:423`) is already exposed; apply the same icon+tooltip if that surface renders aggregate scores. (Confirm exact component during architecture.)
- Data already flows through the API and generated TS schema — **frontend-only** change.

### 5.3 Scope decision (pushback)

The original spec copy ("…required reference data missing", per-`SkippedReason`) implies a per-reason breakdown. The aggregate API exposes only a **count** (`n_excluded`), not a per-reason tally, and different rows may skip for different reasons. **Decision:** the tooltip reports counts only; per-reason copy is **not** in scope (per-item skip reasons are already shown individually in `eval_result_scores.svelte`). Surfacing per-reason aggregates would require new API work — explicitly excluded.

---

## 6. API contract changes

| Endpoint / model | Change |
|---|---|
| `TestV2EvalResponse` (`eval_api.py:212`) | add `intermediate_outputs: dict[str, str] | None = None` |
| `evaluate()` (internal, all V2 adapters) | return `V2EvalResult` instead of the 3-tuple (§1) |

No new HTTP routes, no request-shape changes, no datamodel/storage migrations. The OpenAPI schema + generated TS client must be regenerated for the `TestV2EvalResponse` field.

---

## 7. Edge cases & error handling

- **D14 malformed `tool_calls`:** non-dict `function`, missing `name`, or unparseable `arguments` → that call still yields `{"name": "", "arguments": {}, "id": …}` (no exception); helpers never raise on bad traces.
- **D14/D15 non-assistant / mixed trace:** only `role == "assistant"` entries are considered; user/tool/system entries ignored.
- **D15 content shapes:** assistant message with `content: null` or list-typed content → omitted (only string content returned).
- **D30 valid edge templates:** `{{ task_input }}`, `{{ trace[0].content }}`, `{% if final_message %}…{% endif %}` all pass (reference a non-`reference_data` reserved var). `{{ reference_data.x }}` alone and literal-only templates are rejected.
- **D28 non-regex `ArgMatch`:** `exact`/`contains` modes skip compilation.
- **D29 `None` vs `""`:** `None` still valid (XOR-controlled); only `""` newly rejected.
- **D31 skipped run:** `skipped_reason` set → `intermediate_outputs` is `None`; renderer shows the existing skip badge, no reasoning affordance.
- **D31 empty reasoning:** judge returns no chain-of-thought → `intermediate_outputs` `None`/empty → no "View reasoning" affordance.
- **D35 zero exclusions / severity boundary:** `n_excluded == 0` → no icon. Ratio exactly `20%` → yellow; `> 20%` → red. `n_used == 0 && n_excluded > 0` → ratio is 100% → red icon shown (all cases skipped); mean score is already `None`/"unknown".

---

## 8. Out of scope

- The eval **create container** and Test-Your-Judge pane UI (Project 1).
- `code_eval` stdout/`print()` capture as pseudo-reasoning.
- Per-`SkippedReason` aggregate breakdown / new aggregation API (§5.3).
- Everything classified Override-spec / no-action / Defer in `DECISIONS.md` (D06, D16–D20, D32–D34, D36–D40). D16 and D32 moved to other projects.

---

## 9. Quality bar / acceptance

- All eight decisions implemented; project checks (lint, type, format, py + web tests, schema) green.
- **D14/D15:** manual real-trace verification performed (§2.4) **before** approval; real-format unit fixtures added.
- **D27–D30:** unit tests proving each validator rejects the bad case and accepts the good case at save time (including D30's `reference_data`-only bypass and D28's bad regex).
- **D31:** end-to-end — a batch `llm_judge` run persists `intermediate_outputs`; the run-result page opens reasoning in a modal; `code_eval` shows none; `test_v2_eval` returns the field. Regenerated TS client committed.
- **D35:** warning icon + tooltip appears on the compare view when `n_excluded > 0` and is absent when `0`; coexists correctly with the incomplete-runs warning.
