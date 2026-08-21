---
status: complete
approved: true
alignment_refs: [A2.1, A2.4, A2.10, A2.11, B.12, C.11b, C.11c, K.4, H.32a]
opens: []
summary: V2.0 catalog (lean surface), per-type adapter contract, plugin-extensibility seam, helper-extraction seam.
---

# EvalConfig Types Overview

**Author:** sub-agent dispatched 2026-06-03 for Stage 4 gap-fill
**Status:** complete

## TL;DR

- V2.0 ships exactly **8 EvalConfigTypes** in the `V2EvalType` enum: `llm_judge`, `exact_match`, `pattern_match`, `set_check`, `contains`, `tool_call_check`, `step_count_check`, `code_eval`. The catalog is deliberately lean; post-V2 types extend the same union.
- All V2 types enter through a **two-level adapter dispatch**: outer on `EvalConfig.config_type` (legacy enum vs `"v2"`), inner on `properties.type` (the V2 discriminator). Legacy `g_eval`/`llm_as_judge` paths are untouched.
- V2 adapters subclass the existing `BaseEval` (no `BaseEvalV2` fork). LLM-specific field access is decoupled via a helper module; non-LLM adapters inherit `BaseEval` cleanly.
- Pure scoring logic (score parsing, G-Eval logprob pipeline, token map) is extracted from GEval into `scoring_utils.py` for reuse by V2 `llm_judge`. GEval's V1-coupled seams are never shared or refactored.
- The catalog is closed for V2.0 (no runtime plugin discovery). `code_eval` is the per-project escape hatch. Architectural seams for future plugins are documented; full plugin model lives in `components/80_extensibility_contract.md`.

---

## 1. V2.0 EvalConfigType catalog (A2.4, B.12, K.4)

V2.0 ships with 8 types in the `V2EvalType` enum and `V2EvalConfigProperties` discriminated union. Each type has a dedicated properties class (Pydantic `BaseModel` with a `type: Literal[...]` discriminator field) and a corresponding adapter (subclass of `BaseEval`).

| # | `V2EvalType` value | Purpose (one-line) | Properties class | Detail file |
|---|---|---|---|---|
| 1 | `llm_judge` | Subjective quality, factual accuracy, criteria pass/fail; `g_eval` toggle for token-logprob scoring | `LlmJudgeProperties` | `components/21_type_llm_judge.md` |
| 2 | `exact_match` | String/enum equality vs `reference[key]` | `ExactMatchProperties` | `components/22_type_deterministic_basics.md` |
| 3 | `pattern_match` | Regex on output / trace / field-path | `PatternMatchProperties` | `components/22_type_deterministic_basics.md` |
| 4 | `set_check` | Set containment (subset/superset/intersection) vs reference | `SetCheckProperties` | `components/22_type_deterministic_basics.md` |
| 5 | `contains` | Substring presence/absence | `ContainsProperties` | `components/22_type_deterministic_basics.md` |
| 6 | `tool_call_check` | Tool trajectory: existence, ordering, forbidden, per-arg matching | `ToolCallCheckProperties` | `components/22_type_deterministic_basics.md` |
| 7 | `step_count_check` | Agent efficiency: count of tool calls / model responses / turns vs bounds | `StepCountCheckProperties` | `components/22_type_deterministic_basics.md` |
| 8 | `code_eval` | User-authored Python scorer; gated by trust UX + crash isolation | `CodeEvalProperties` | `components/27_type_code_eval.md` |

**Type groupings by infrastructure:**

- **LLM-backed (1):** `llm_judge`. Requires model fields (`model_name`, `model_provider`) on its own properties. Uses Jinja2 `prompt_template` + `JinjaInputTransform` (D.2/D.3/D.4). Consumes `scoring_utils.py` helpers for score parsing and G-Eval logprobs (H.32a).
- **Deterministic (2-7):** `exact_match`, `pattern_match`, `set_check`, `contains`, `tool_call_check`, `step_count_check`. No LLM call. Use `extract()` / `value_expression` for data extraction (D.2/D.3). Grouped in `components/22` because they share the extraction infrastructure.
- **Code (8):** `code_eval`. Runs user Python via `multiprocessing` (B.13). Separate trust and sandboxing story.

**SpecType mapping (K.4):** For V2.0, all 17 existing SpecTypes in the builder/Copilot flow map to `llm_judge`. Mapping other SpecTypes to deterministic or code types (e.g. `appropriate_tool_use` to `tool_call_check`) is deferred to the post-V2 "new eval types in UI" follow-up.

**Post-V2 types (not in V2.0 enum):** `composite`, `threshold`, `json_schema`, `event_ordering`, `embedding_similarity`, `dag_metric`. Each can be added as a new `V2EvalType` enum value + properties class + adapter, extending the discriminated union. `event_ordering` can be expressed via `code_eval` in the interim (B.14).

---

## 2. Two-level adapter dispatch (A2.11, C.11b)

V2 uses two-level adapter dispatch. This is the central mechanism that routes an `EvalConfig` to its scoring adapter.

### 2.1 Dispatch flow

```
EvalConfig
  |
  +-- config_type == "g_eval" or "llm_as_judge"
  |     |
  |     +-- LEGACY PATH: return GEval (unchanged, per D.5)
  |
  +-- config_type == "v2"
        |
        +-- V2 PATH: read properties.type (inner discriminator)
              |
              +-- dispatch via V2 sub-registry keyed on V2EvalType value
              |     "llm_judge"      -> LlmJudgeAdapter
              |     "exact_match"    -> ExactMatchAdapter
              |     "pattern_match"  -> PatternMatchAdapter
              |     "set_check"      -> SetCheckAdapter
              |     "contains"       -> ContainsAdapter
              |     "tool_call_check"-> ToolCallCheckAdapter
              |     "step_count_check"-> StepCountCheckAdapter
              |     "code_eval"      -> CodeEvalAdapter
              |
              +-- unknown type -> raise (exhaustive enum match)
```

### 2.2 Registry signature (A2.11)

The registry entry point changes from taking the enum value to taking the full `EvalConfig`:

```python
# kiln_ai/adapters/eval/registry.py

def eval_adapter_from_type(eval_config: EvalConfig) -> type[BaseEval]:
    if eval_config.config_type == EvalConfigType.v2:
        return _v2_adapter_from_properties_type(eval_config.properties)
    # Legacy dispatch — unchanged
    match eval_config.config_type:
        case EvalConfigType.g_eval:
            return GEval
        case EvalConfigType.llm_as_judge:
            return GEval
        case _:
            raise_exhaustive_enum_error(eval_config.config_type)


# V2 sub-registry — one map, exhaustive over V2EvalType
_V2_ADAPTER_MAP: dict[V2EvalType, type[BaseEval]] = {
    V2EvalType.llm_judge: LlmJudgeAdapter,
    V2EvalType.exact_match: ExactMatchAdapter,
    V2EvalType.pattern_match: PatternMatchAdapter,
    V2EvalType.set_check: SetCheckAdapter,
    V2EvalType.contains: ContainsAdapter,
    V2EvalType.tool_call_check: ToolCallCheckAdapter,
    V2EvalType.step_count_check: StepCountCheckAdapter,
    V2EvalType.code_eval: CodeEvalAdapter,
}

def _v2_adapter_from_properties_type(
    properties: V2EvalConfigProperties,
) -> type[BaseEval]:
    adapter_cls = _V2_ADAPTER_MAP.get(V2EvalType(properties.type))
    if adapter_cls is None:
        raise ValueError(f"Unknown V2EvalType: {properties.type}")
    return adapter_cls
```

**Internal API; one call site** (`eval_runner.py:204`) to update. The runner already has the full `EvalConfig` in scope at the dispatch site.

### 2.3 Two discriminator mechanisms (recap from A2.1)

These do different jobs and must not be confused:

- **Outer (`config_type` on `EvalConfig`):** A plain field + `model_validator` that routes parsing between the legacy `dict[str, Any]` path and the V2 typed discriminated union. NOT a Pydantic discriminator. Values: `g_eval`, `llm_as_judge`, `v2`.
- **Inner (`type` on each V2 properties variant):** The standard Pydantic v2 `Annotated[Union[...], Discriminator("type")]` pattern. Values: the `V2EvalType` enum members.

### 2.4 Frontend parallel (G.3)

The frontend mirrors this dispatch with two parallel registries keyed on `properties.type`:

- **Create-form-by-type** — the per-type authoring component plugged into the shared create container (G.1).
- **Result-renderer-by-type** — the per-type view component.

Both are exhaustive over `V2EvalType` (compile-time TS exhaustiveness + runtime assert). A new type added without a UI module fails loudly. Implementation detail in `components/70_builder_and_onboarding.md`.

---

## 3. Adapter base class contract (C.11c, A2.10)

### 3.1 Single `BaseEval` — no fork

V2 adapters subclass the existing `BaseEval`. There is no `BaseEvalV2` class. This avoids coupling V1/V2 lifetimes (every base-class change replicated twice) and the V1/V2 semantic coupling that A2.10's helper extraction explicitly avoids.

```
BaseEval (generic, no LLM coupling)
  |
  +-- GEval (legacy; calls legacy_model_fields helper for model access)
  |
  +-- LlmJudgeAdapter (V2; reads model fields from LlmJudgeProperties)
  +-- ExactMatchAdapter (V2; no model fields)
  +-- PatternMatchAdapter (V2; no model fields)
  +-- SetCheckAdapter (V2; no model fields)
  +-- ContainsAdapter (V2; no model fields)
  +-- ToolCallCheckAdapter (V2; no model fields)
  +-- StepCountCheckAdapter (V2; no model fields)
  +-- CodeEvalAdapter (V2; no model fields; sandbox dispatch)
```

### 3.2 Model-field access decoupling (A2.10)

`BaseEval.model_and_provider()` (currently at `base_eval.py:40-54`) is extracted into a separate helper module (e.g. `kiln_ai/adapters/eval/legacy_model_fields.py`):

- **Legacy `GEval`:** Calls the helper to read root-level `EvalConfig.model_name` / `EvalConfig.model_provider`.
- **V2 `llm_judge`:** Reads `self.eval_config.properties.model_name` / `.model_provider` directly from `LlmJudgeProperties`. Does NOT use the helper.
- **V2 non-LLM types:** Inherit `BaseEval` cleanly; never touch model fields.

This keeps `BaseEval` minimal. Verified: `BaseEval.__init__` at `base_eval.py:21-38` already does NOT read `model_name`/`model_provider` — only the `model_and_provider()` method does, so extraction is clean.

### 3.3 Per-adapter contract summary

Every V2 adapter:

1. Subclasses `BaseEval`.
2. Receives either `TaskRun` or `EvalInput` via the runner (the runner guarantees V2 adapters receive `EvalInput` per B2.1 translation; the base `run_eval` signature widens to `TaskRun | EvalInput` as a formality).
3. Uses `BaseEval.build_score_schema()` for score-schema generation (already class-level, no V1 coupling).
4. Returns scores conforming to the parent `Eval.output_scores` shape (validated at EvalRun save time by the existing `EvalRun.validate_scores` mechanism, per C.9).

Type-specific adapter responsibilities:

| Adapter | Data access | Score production |
|---|---|---|
| `LlmJudgeAdapter` | Jinja2 `prompt_template` + `JinjaInputTransform`; `required_var` pre-check via `extract()` | Calls LLM; parses via `scoring_utils.build_llm_as_judge_score()` or `scoring_utils.build_g_eval_score()` depending on `g_eval` flag |
| Deterministic adapters (6) | `extract()` via `value_expression` on properties; `tool_call_check` and `step_count_check` read trace directly | Pure comparison logic; no external calls |
| `CodeEvalAdapter` | Passes raw sources via helper lib (Phase 5) | Executes user code in `multiprocessing` child (B.13); parses returned result |

---

## 4. Scoring-helper extraction seam (H.32a)

### 4.1 What gets extracted

GEval's three V1-decoupled, pure scoring seams are extracted into `kiln_ai/adapters/eval/scoring_utils.py`:

| Seam | Functions extracted | Source lines | V1 coupling |
|---|---|---|---|
| Score token mapping | `score_from_token_string()`, `TOKEN_TO_SCORE_MAP` | `g_eval.py:24-34, 515-534` | None (pure utility) |
| Structured-output score parsing | `build_llm_as_judge_score(run_output) -> EvalScores` | `g_eval.py:331-347` | None (pure function of `RunOutput`) |
| G-Eval logprob pipeline | `build_g_eval_score(run_output) -> EvalScores`, `g_eval_single_metric()`, `rating_token_to_score()`, `raw_output_from_logprobs()`, `metric_offsets()`, `token_search_range()` | `g_eval.py:349-563` | None (pure function of `RunOutput` + logprobs) |

**Also stays on `BaseEval` (not extracted):** `build_score_schema()` at `base_eval.py:104-184` — already class-level, no V1 coupling, naturally inherited by all adapters.

### 4.2 What is NOT extracted (never shared, never refactored)

| Seam | Why not shared |
|---|---|
| `GEvalTask` construction (`g_eval.py:44-81`) | V1-specific: reads V1 `EvalConfig.properties` as a raw dict. V2 uses Jinja2 templates + `JinjaInputTransform` (D.2). |
| Three `generate_*_run_description` f-strings (`g_eval.py:121-247`) | Replaced entirely by user-authored Jinja2 `prompt_template` in V2 (D.1). V2 never hardcodes prompt shapes. |
| `model_and_provider()` on `BaseEval` | Being extracted to its own helper per A2.10 (section 3.2 above). Not part of scoring_utils. |

### 4.3 Consumption pattern

```python
# V2 LlmJudgeAdapter (built fresh, Phase 1)
from kiln_ai.adapters.eval.scoring_utils import (
    build_llm_as_judge_score,
    build_g_eval_score,
)

class LlmJudgeAdapter(BaseEval):
    async def run_eval(self, item, ...):
        # ... own task/prompt construction via D.2/D.3/D.4 ...
        run_output = await self._invoke_llm(...)
        if self.eval_config.properties.g_eval:
            return build_g_eval_score(run_output)
        else:
            return build_llm_as_judge_score(run_output)
```

```python
# Legacy GEval (unchanged beyond import path)
from kiln_ai.adapters.eval.scoring_utils import (
    build_llm_as_judge_score,
    build_g_eval_score,
    score_from_token_string,
    TOKEN_TO_SCORE_MAP,
)
# GEval.run_eval body: zero behavior change. Calls same functions, now imported.
```

### 4.4 Prerequisites (hard gate)

GEval's `reference_answer` path has **zero test coverage** (verified 2026-06-03: `generate_ref_ans_run_description` and the `reference_answer` branch of `run_eval` have no tests across `test_g_eval.py`, `test_eval_runner.py`, `test_g_eval_data.py`). Two characterization tests (~50 LOC) pinning current behavior must land as a standalone commit before helpers are extracted:

1. `test_generate_ref_ans_run_description` — unit test for the f-string template.
2. `test_run_eval_reference_answer_data_type` — end-to-end test for `GEval.run_eval` when `evaluation_data_type == EvalDataType.reference_answer`.

### 4.5 Phasing

1. **Phase 0 (parallel with schema work):** Add characterization tests. Extract `scoring_utils.py`. GEval imports from it; zero behavior change.
2. **Phase 0:** Extract `model_and_provider()` per A2.10 (section 3.2).
3. **Phase 1:** Build `LlmJudgeAdapter` fresh on `scoring_utils` + `BaseEval.build_score_schema()` + D.2/D.3/D.4 infra.

---

## 5. Extensibility seam (A2.4, B.12, E.36 pointer)

### 5.1 V2.0 stance: closed catalog + `code_eval` escape hatch

The `V2EvalType` enum and `V2EvalConfigProperties` union are **closed for V2.0** — adding a new built-in type requires a PR to Kiln. There is no runtime plugin discovery, no setuptools entry-point registration, no plugin marketplace.

**Why closed:**

- Kiln's primary distribution is the PyInstaller bundle, which cannot `pip install` at runtime (A0.4). An open registry would only work for pip-installed Kiln, creating a two-tier ecosystem.
- Builder UX (G.1/G.3) needs the full type catalog at build time for exhaustive enum binding. Runtime-discovered types cannot be surfaced cleanly.
- Quality and security consistency for V2.0 launch.

**`code_eval` covers the long tail:** Anything a third-party plugin could do (custom signal extraction, project-specific logic, novel scoring) can be done inside `code_eval` as user-authored Python. The limitation is that `code_eval` is per-project — no built-in mechanism to share a scorer across projects. If users want to share, they share the code.

### 5.2 Architectural seams that would open for future plugins

The V2.0 architecture does not foreclose a future plugin model. The seams:

1. **Enum extension:** `V2EvalType` is a `str, Enum`. A future plugin system would extend it with namespace-aware values (e.g. `"mypackage/my_scorer"`).
2. **Properties union extension:** `V2EvalConfigProperties` is an `Annotated[Union[...], Discriminator("type")]`. New properties classes slot in by widening the union.
3. **Adapter map extension:** `_V2_ADAPTER_MAP` (section 2.2) is a plain dict. Entry-point discovery would add entries to it at startup.
4. **Builder UI discovery:** G.3's renderer registry would need a "plugin-provided" fallback renderer for types not known at compile time.

**Full plugin model design lives in `components/80_extensibility_contract.md`** — that file documents the seams, the conditions under which they would open, and why `code_eval` covers V2.0's long-tail use cases. This file defines the seams; `components/80` defines the keys.

### 5.3 How a new built-in type plugs in (V2.x process)

Adding a new built-in type (e.g. `json_schema` post-V2) requires:

1. Add value to `V2EvalType` enum.
2. Create `JsonSchemaProperties(BaseModel)` with `type: Literal["json_schema"]`.
3. Add the properties class to the `V2EvalConfigProperties` union.
4. Create `JsonSchemaAdapter(BaseEval)` implementing `run_eval`.
5. Register in `_V2_ADAPTER_MAP`.
6. Add frontend module exporting `{ label, icon, createForm, resultRenderer, requiresTrust }` per G.3.
7. Ensure exhaustive enum coverage in both backend and frontend registries.

This is the same pattern used by every V2.0 type. The architecture is uniform; no special "extensibility API" is needed for built-in additions.

---

## 6. Alignment reference coverage

| Ref | Decision | Coverage in this file |
|---|---|---|
| A2.1 | EvalConfig V2 shape (coexistence) | Section 2 (two-level dispatch relies on the `config_type`/`properties.type` discriminator structure defined by A2.1) |
| A2.4 | V2.0 lean catalog | Section 1 (full catalog table; post-V2 deferrals listed) |
| A2.10 | `model_and_provider` helper extraction | Section 3.2 (decoupling pattern; who calls what) |
| A2.11 | Adapter registry signature change | Section 2.2 (registry code; signature `EvalConfigType` to `EvalConfig`) |
| B.12 | Hybrid: config-first, `code_eval` as additional type | Section 1 (code_eval in catalog); Section 5.1 (`code_eval` as escape hatch) |
| C.11b | V2 adapter registry: two-level dispatch | Section 2 (dispatch flow + registry implementation) |
| C.11c | V2 adapter base class: generic `BaseEval` | Section 3.1 (no `BaseEvalV2` fork; inheritance tree) |
| K.4 | SpecType to V2EvalType mapping | Section 1 (all 17 SpecTypes to `llm_judge` for V2.0) |
| H.32a | Legacy/V2 code reuse: scoring helper extraction | Section 4 (what moves, what stays, prereqs, phasing) |

---

## Opens

None. All alignment_refs are fully covered; no blocking questions remain for this file. Per-type implementation detail lives in sibling design files (`21`, `22`, `27`). Plugin model detail lives in `components/80`.
