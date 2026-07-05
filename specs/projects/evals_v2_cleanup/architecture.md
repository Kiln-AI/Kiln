---
status: complete
---

# Architecture: Evals V2 cleanup

Single architecture doc (no component breakdown) — eight surgical fixes, well under the complexity that warrants per-component docs. UI design folded in here (skipped standalone `ui_design.md` per scosman — two small additions to existing components).

The one shared spine is the **`V2EvalResult`** contract migration (§1); everything else is independent. Build §1 first, then the rest can land in any order.

---

## 1. `V2EvalResult` contract migration (backend spine)

### 1.1 New model

Add to `libs/core/kiln_ai/datamodel/eval.py` (next to `EvalTaskInput`, reusing the already-defined `EvalScores`, `SkippedReason`):

```python
class V2EvalResult(BaseModel):
    """Result of a single V2 eval `evaluate()` call."""
    scores: EvalScores = Field(default_factory=dict)
    skipped_reason: SkippedReason | None = None
    skipped_detail: str | None = None
    intermediate_outputs: dict[str, str] | None = None
```

### 1.2 Producers — `evaluate()` in all 8 adapters

Change the abstract signature on `BaseV2EvalBridge.evaluate` (`base_eval.py:240-243`) from
`-> tuple[EvalScores, SkippedReason | None, str | None]` to `-> V2EvalResult`.

Each adapter's `return` is rewritten to construct `V2EvalResult(...)`:

| Adapter | Change |
|---|---|
| `v2_eval_llm_judge.py` | `return V2EvalResult(scores=scores, intermediate_outputs=run_output.intermediate_outputs)` — **stop discarding** `run_output.intermediate_outputs` from line 165 (§4). Skip paths return `V2EvalResult(skipped_reason=skip, skipped_detail=detail)`. |
| `v2_eval_code_eval.py` | `V2EvalResult(scores=...)`; trust-skip → `V2EvalResult(skipped_reason=..., skipped_detail=...)`. `intermediate_outputs` stays `None`. |
| `v2_eval_tool_call_check.py`, `v2_eval_exact_match.py`, `v2_eval_contains.py`, `v2_eval_pattern_match.py`, `v2_eval_set_check.py`, `v2_eval_step_count_check.py` | mechanical: wrap existing `(scores, skip, detail)` returns in `V2EvalResult(...)`. |

### 1.3 Consumers — 5 call sites

- **`base_eval.py:245-254`** `BaseV2EvalBridge.run_eval` (signature `-> tuple[EvalScores, Dict[str,str] | None]` unchanged):
  ```python
  result = await self.evaluate(eval_task_input)
  if result.skipped_reason is not None:
      raise ValueError(f"V2 eval was skipped ({result.skipped_reason}): {result.skipped_detail}")
  return result.scores, result.intermediate_outputs
  ```
  (Previously returned `scores, None`. This keeps the abstract `run_eval` contract and now forwards reasoning on the fresh-generation path too.)
- **`eval_runner.py` `_run_v2_job`** — 3 evaluate branches (`from_eval_input` ~463, `task_run_eval` ~489, default `eval_config_eval` ~520). Each:
  ```python
  result = await evaluator.evaluate(eval_task_input)
  # ...build EvalRun with:
  scores=result.scores,
  output=task_output if result.skipped_reason is None else None,
  skipped_reason=result.skipped_reason.value if result.skipped_reason else None,
  skipped_detail=result.skipped_detail,
  intermediate_outputs=result.intermediate_outputs,   # NEW — was absent
  ```
- **`eval_api.py:996` `test_v2_eval`** — `result = await adapter.evaluate(...)`; build `TestV2EvalResponse(scores=result.scores, skipped_reason=…, skipped_detail=…, intermediate_outputs=result.intermediate_outputs)` (§6).

### 1.4 Why a model, not a tuple

Chosen by scosman: self-documenting and lets us add fields (logprobs, usage) later without re-threading all call sites. No storage migration — `EvalRun.intermediate_outputs` already exists (`dict[str,str] | None`).

---

## 2. D14 / D15 — `KilnEvalHelpers` (`eval_helpers.py`)

Pure-stdlib utility; no imports of Kiln models. Both fixes are self-contained method bodies.

### 2.1 `get_tool_calls` (D14)

Replace the body (`eval_helpers.py:19-28`) with OpenAI-format extraction mirroring `v2_eval_tool_call_check.py:41-66`, plus the `id` field for spec parity:

```python
@staticmethod
def get_tool_calls(trace):
    if not trace:
        return []
    calls = []
    for msg in trace:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            func = tc.get("function", {}) if isinstance(tc, dict) else {}
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except (json.JSONDecodeError, TypeError):
                args = {}
            calls.append({
                "name": func.get("name", ""),
                "arguments": args if isinstance(args, dict) else {},
                "id": tc.get("id") if isinstance(tc, dict) else None,
            })
    return calls
```

`name`/`arguments` keys keep `has_tool_call`/`count_tool_calls` working unchanged. Add `import json` (module already imports `re`).

### 2.2 `get_assistant_messages` (D15)

Replace the body (`eval_helpers.py:30-37`); return type `-> list[str]`:

```python
@staticmethod
def get_assistant_messages(trace):
    if not trace:
        return []
    return [
        msg["content"]
        for msg in trace
        if msg.get("role") == "assistant" and isinstance(msg.get("content"), str)
    ]
```

Assistant turns with `content: None` (tool-call-only) are omitted.

### 2.3 Verification gate (hard)

Before approval, run both against a **real** Kiln trace containing real tool calls (capture from a live tool-using task run; do **not** hand-author). Replace the synthetic `role: "tool_call"` fixture in `test_code_eval_samples.py:294` and add a real-format fixture (`role: "assistant"` + nested `tool_calls`) to `test_eval_helpers.py`. Update `test_eval_helpers.py:51` (currently asserts `msgs[0]["content"]` dict access) to assert string content.

---

## 3. D27–D30 — save-time validators (`eval.py`)

All add validation at construction time, surfacing `ValueError` to the create-UI save path **and** the `test_v2_eval` transient-config path. Coordinate with Project 1 (same file, different classes).

| ID | Target (`eval.py`) | Implementation |
|---|---|---|
| **D28** | `ArgMatch` (154-156) | add `@model_validator(mode="after")`: if `match_mode == "regex"`, `re.compile(str(self.value))`; raise `ValueError(f"Invalid regex value '{self.value}': {e}")` on `re.error`. Mirror `PatternMatchProperties.validate_pattern` (114-122). |
| **D27** | `ToolCallCheckProperties.expected_tools` (166) | `min_length=1` is not directly expressible on a bare `list` annotation without `Field`; use `expected_tools: list[ToolCallSpec] = Field(min_length=1)` (Pydantic v2) **or** a `model_validator` raising on empty. Prefer `Field(min_length=1)` with a clear message. |
| **D29** | `reference_key` on `ExactMatchProperties` (96), `ContainsProperties` (129), `SetCheckProperties` (144) | change `reference_key: str | None = None` → `reference_key: str | None = Field(default=None, min_length=1)`. Preserves `None` validity (XOR validators untouched); only `""` is newly rejected. |
| **D30** | `EvalConfig.validate_v2_templates_and_expressions`, `LlmJudgeProperties` branch (706-712) | replace the `"{{" not in tmpl` surface scan with an AST check (below). |

### 3.1 D30 AST check

The judge template's render namespace is exactly `EvalTaskInput.model_dump()` = `{final_message, trace, reference_data, task_input}`.

```python
from jinja2 import meta
from kiln_ai.utils.jinja_engine import _template_env  # SandboxedEnvironment

# (after the existing compile_template_or_raise(props.prompt_template))
referenced = meta.find_undeclared_variables(_template_env.parse(props.prompt_template))
MEANINGFUL = {"final_message", "trace", "task_input"}   # reference_data deliberately excluded
if not (referenced & MEANINGFUL):
    raise ValueError(
        "prompt_template never references the model output. A template that uses "
        "only reference_data (or no variables) produces the same judge prompt for "
        "every run. Reference the output, e.g. {{ final_message }}."
    )
```

`find_undeclared_variables` returns top-level names, so `trace[0].content` surfaces `trace` and passes; `{{ reference_data.x }}`-only and literal templates are rejected. `_template_env.parse()` is exported via the existing `_template_env` import already used by `v2_eval_llm_judge.py`; add `from jinja2 import meta` locally in the validator (it already imports jinja helpers lazily).

---

## 4. D31 backend — capture judge reasoning

Covered structurally by §1. The substantive change is in `v2_eval_llm_judge.py`: line 165 `_, run_output = await adapter.invoke_returning_run_output(rendered_prompt)` already yields `run_output.intermediate_outputs` (the `SIMPLE_CHAIN_OF_THOUGHT` judge emits `{"chain_of_thought": "..."}`). Pass it into `V2EvalResult.intermediate_outputs`. Skip/required-var paths (105-107) carry `None`. No other adapter produces reasoning; `code_eval` stdout capture is explicitly out of scope.

---

## 5. D31 frontend — reasoning modal on run-result page

### 5.1 Thread the prop

`run_result/+page.svelte:354-362` — add to the `<svelte:component>` props:
```svelte
intermediate_outputs={result.intermediate_outputs ?? null}
```
(`result.intermediate_outputs` already exists on the `EvalRun` TS type — the V1 path reads it at line 323.)

### 5.2 `llm_judge_result.svelte`

Add prop + a `Dialog` instance mirroring `thinking_dialog` in `run_result/+page.svelte:418-433`:

```svelte
export let intermediate_outputs: Record<string, string> | null = null
$: reasoning = intermediate_outputs?.reasoning || intermediate_outputs?.chain_of_thought || null
let reasoning_dialog: Dialog | null = null
```
In markup, when `reasoning` is present, render a small **"View reasoning"** button (`text-xs` link style, consistent with the existing `text-gray-400` config block) that calls `reasoning_dialog?.show()`. The `<Dialog bind:this={reasoning_dialog} title="Judge Reasoning" action_buttons={[{label:"Close", isCancel:true}]}>` holds `<div class="font-light text-sm whitespace-pre-wrap">{reasoning}</div>`.

`code_eval_result.svelte` and other renderers: **no change** (no reasoning). No re-enabled Thinking column; the V1 column logic is untouched.

---

## 6. API contract + schema

- `TestV2EvalResponse` (`eval_api.py:212-217`): add `intermediate_outputs: dict[str, str] | None = None`.
- Regenerate the OpenAPI client (`app/web_ui/src/lib/generate_schema.sh`) and commit so `check_schema` passes. No other endpoint/route/request changes.

---

## 7. D35 frontend — `n_excluded` (i) indicator

### 7.1 Compare view (primary) — `run_config_comparison_table.svelte`

`n_excluded` lives in each `ScoreSummary` and is constant across a run config's score keys (`eval_api.py:605`). Read it once per row from the first available score summary:

```ts
function excluded_for_run_config(summary, rc_id, output_scores) {
  const per_score = summary?.results?.["" + rc_id]
  for (const s of output_scores) {
    const ss = per_score?.[string_to_json_key(s.name)]
    if (ss) return { n_excluded: ss.n_excluded ?? 0, n_used: ss.n_used ?? 0 }
  }
  return { n_excluded: 0, n_used: 0 }
}
```

Render next to the Status cell (alongside, not replacing, the existing `percent_complete` incomplete warning). When `n_excluded > 0`:

```svelte
{@const ratio = n_excluded / (n_used + n_excluded)}
<span class={ratio > 0.2 ? "text-error" : "text-warning"}>
  <InfoTooltip
    symbol="info"
    position="top"
    tooltip_text={`${n_excluded} of ${n_used + n_excluded} cases were skipped and are not reflected in this score.`}
  />
</span>
```

`InfoTooltip`'s SVG uses `fill="currentColor"`, so the wrapping `text-warning`/`text-error` span recolors the (i) glyph — **no component change needed**. Threshold: `> 0.2` → red, else yellow.

### 7.2 Judge-comparison view (secondary)

`RunConfigEvalResult.n_excluded` (`eval_api.py:423`) is already exposed. Apply the same `<span class=…><InfoTooltip…/></span>` pattern wherever that surface renders aggregate per-run scores. Locate the consuming component during implementation (`grep` for `RunConfigEvalResult` / `eval_config` comparison table); if it doesn't render a comparable aggregate row, note it and limit D35 to the compare view.

---

## 8. Testing strategy

| Area | Tests |
|---|---|
| §1 `V2EvalResult` | existing V2 adapter tests updated to assert on `result.scores` / `result.skipped_reason` / `result.intermediate_outputs`; `test_v2_dispatch_and_contract.py` covers the shape. Runner test asserts `EvalRun.intermediate_outputs` persists for llm_judge and is `None` for code_eval. |
| §2 D14/D15 | real-format fixture (assistant + nested `tool_calls`); `get_tool_calls` returns `[{name,arguments,id}]`; `get_assistant_messages` returns `list[str]`, omits `content:null` turns. **Manual real-trace gate (§2.3) before approval.** Update `test_eval_helpers.py:51`, `test_code_eval_samples.py:294`. |
| §3 D27–D30 | per-validator accept/reject: empty `expected_tools` rejected; bad regex `ArgMatch` rejected; `reference_key=""` rejected but `None` accepted; D30 — `{{ reference_data.x }}`-only and literal templates rejected, `{{ final_message }}` / `{{ trace[0].content }}` / `{{ task_input }}` accepted. |
| §4–6 D31 | llm_judge `evaluate()` returns reasoning; `_run_v2_job` persists it; `test_v2_eval` returns it; web test that `llm_judge_result.svelte` shows "View reasoning" → modal when reasoning present, hidden when absent. |
| §7 D35 | web test: (i) appears when `n_excluded>0`, absent at `0`; `text-warning` at ≤20%, `text-error` at >20%; coexists with the incomplete-runs warning. |

Run the project's full check suite (lint/format/type/py+web tests/schema/build) before each phase CR.

---

## 9. Sequencing (feeds implementation_plan)

1. **Backend spine + helpers + validators** — `V2EvalResult` migration (§1) + D14/D15 (§2) + D27–D30 (§3) + D31 backend capture (§4). All `libs/core` / API, mutually compatible, one CR.
2. **Frontend + API surface** — `TestV2EvalResponse` field + schema regen (§6), D31 reasoning modal (§5), D35 (i) indicator (§7). One CR.

Two phases keeps each CR reviewable and separates the manual real-trace gate (phase 1) from UI review (phase 2). A single phase is acceptable if preferred; the implementation plan will propose two.

---

## 10. Risks & coordination

- **Project 1 shares `eval.py`** (its `set_check` enum work) — D27–D30 touch different classes/fields; rebase carefully, low conflict risk. The `V2EvalResult` migration touches adapter files Project 1 does not.
- **`evaluate()` signature change is wide** (8 adapters + 5 call sites) but mechanical; the type checker (`ty`) will flag any missed site — lean on it.
- **Manual trace gate** is a process risk, not a code one: do not approve D14/D15 on synthetic fixtures.
