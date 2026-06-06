---
status: complete
approved: true
alignment_refs: [A1.2, A1.3, A1.4]
opens: []
summary: Flat dict shape, multi-config consumption, reference-key naming guidelines, per-case criteria via reference data.
---

# Reference Data

## 1. Purpose and scope

This file owns the reference-data semantics and key contract for V2 evals. Specifically:

- The flat `EvalInput.reference: dict[str, JsonValue] | None` shape and what it means (A1.2).
- How multiple EvalConfigs on the same Eval consume the same reference dict (A1.3).
- Reference-key naming guidelines -- the canonical keys, conventions for new ones, and collision avoidance (consequence of A1.3).
- Per-case criteria expressed as reference data, not as a separate field (A1.4).

The `EvalInput` entity schema itself (Pydantic model, field placement, `data` discriminator) is owned by `components/10_data_model.md`. This file references the `reference` field defined there and specifies everything downstream of it.

---

## 2. Shape: `EvalInput.reference` (A1.2)

```python
class EvalInput(KilnParentedModel):
    # ... other fields (tags, data) per components/10 ...
    reference: dict[str, JsonValue] | None = None
```

### 2.1. Type definition

- **Root type:** `dict[str, JsonValue] | None`.
- **`JsonValue`:** Pydantic v2's built-in `JsonValue` type. Alias: `None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]`.
- **Root constraint:** When non-None, the root must be a dict. Top-level non-dict values (bare string, bare array, bare bool) are rejected because they would break key-based config consumption. This is enforced by the type annotation itself (Pydantic validates the root as `dict[str, JsonValue]`).

### 2.2. Design rationale

A flat dict was chosen over typed/structured alternatives (A1.2 rationale):

| Alternative considered | Why rejected |
|---|---|
| Typed `ReferenceProperties` Pydantic model | Would get brittle as the EvalConfigType catalog grows. Every new type that needs a new reference field would require a schema migration on the shared model. Third-party plugins (Batch E, E.36) could not add reference keys without a Kiln PR. |
| Per-config namespaced sub-dicts (`reference: dict[str, dict[str, JsonValue]]` keyed by config ID) | Tightly couples datasets to specific configs. Reorganizing configs (rename, replace, add a new config that scores the same dimension) forces reference-data migration. Breaks dataset sharing across Evals. |
| Per-variant typed reference (different reference schema per `EvalInputData` variant) | `reference` is turn-agnostic (A1.1): the same reference answer is equally valid for single-turn and multi-turn inputs. Per-variant typing would force duplication or a shared supertype that converges back to a dict. |

### 2.3. Trade-offs accepted

1. **No EvalInput-creation-time validation of reference shape.** A user can populate any keys with any JSON-roundtrippable values. Validation happens at config-bind time (see section 3).
2. **No IDE autocomplete on reference data.** The dict is untyped at the EvalInput level. Recoverability: each EvalConfigType declares the keys it consumes (see section 3), so tooling can introspect declared keys from the config side. The builder UX uses this to render reference-data forms (see section 5).
3. **No schema enforcement across EvalInputs in a dataset.** Two EvalInputs under the same Eval may have different reference keys populated. The runner handles missing keys via the skip mechanism (C.runner.1), not via dataset-level schema enforcement.

### 2.4. JSON roundtrip guarantee

Every value in `reference` must survive `json.dumps` / `json.loads` roundtrip without loss. This is enforced by the `JsonValue` type constraint. Consequences:

- Python `datetime`, `bytes`, `set`, custom objects are not storable. Users must serialize to string or list before storing.
- `float('nan')`, `float('inf')` are technically valid JSON in Python's `json` module but are not interoperable. Best practice: avoid; no enforcement in V2.0.
- Order of keys in nested dicts is preserved (Python 3.7+, JSON insertion order).

---

## 3. Multi-config consumption (A1.3)

### 3.1. Principle

One `EvalInput.reference` dict serves all EvalConfigs under the same Eval. Each EvalConfig declares which keys it consumes. Validation happens at config-bind time (when the runner pairs an EvalConfig with an EvalInput to produce an EvalRun), not at EvalInput creation time.

### 3.2. Declaration mechanism

EvalConfigTypes declare their reference-key requirements through their properties shape. The mechanism differs by type family:

**LLM judge types** declare reference-key consumption implicitly through the Jinja2 `prompt_template` and explicitly through `required_var`:

```python
LlmJudgeProperties(
    prompt_template="""\
{{ reference_data.reference_answer }}
...compare the model's output against the reference above...
{{ final_message }}
""",
    required_var=["reference_data.reference_answer"],
    ...
)
```

- `required_var` expressions are pre-checked via `extract()` before template rendering. If any evaluates to `None` or `Undefined`, the case is skipped with `skipped_reason: extraction_failed` + `skipped_detail: "reference_data.reference_answer"` (per C.runner.1, `components/40` section 3.1).
- Template variables not listed in `required_var` degrade gracefully: Jinja2's `{% if reference_data.ground_truth_context %}` pattern (used in RAG templates, see `components/29` section 3.4) renders the optional block only when the key is present.

**Simple-check types** (`exact_match`, `contains`, `set_check`) declare reference-key consumption via a typed `reference_key: str` field on their properties:

```python
ExactMatchProperties(
    value_expression="final_message.classification",
    reference_key="expected_classification",
)
```

- At runtime, the adapter reads `eval_input.reference[reference_key]`. If the key is absent or `reference` is None, the case is skipped (C.runner.1).
- `reference_key` is mutually exclusive with `expected_value` (literal comparison, no reference data needed). Enforced by a Pydantic `model_validator` on each simple-check properties class (see `components/40` section 3.2).

**Typed trace inspectors** (`tool_call_check`, `step_count_check`) do not consume reference data in V2.0. They walk the trace internally. Future extensions (e.g., per-case expected tool-call sequences) would use reference keys following the conventions in section 4.

### 3.3. Skip semantics for missing reference data

When an EvalConfig requires a reference key that is absent from a particular EvalInput's `reference` dict (or when `reference` is None entirely):

1. The runner **skips** that (input, config) combination.
2. A structured `skipped_reason` + `skipped_detail` is recorded on the EvalRun (e.g., `skipped_reason: extraction_failed` + `skipped_detail: "reference_data.reference_answer"` for LLM judge, `skipped_reason: missing_reference_key` + `skipped_detail: "expected_classification"` for simple-check types).
3. The skip contributes to `n_excluded` in metric provenance (per `components/85`).
4. The skip is **not** a hard failure -- other EvalConfigs that do not require the missing key still run against that EvalInput.

This is the C.runner.1 contract: best-effort partial eval, not hard-fail, not score-partial.

### 3.4. Reference-key collision handling

When two EvalConfigs on the same Eval declare that they consume the same reference key, this is allowed (the dict is shared). However, if the two configs expect different semantics for the same key name (e.g., one expects `reference_answer` to be a string, the other expects it to be a list), the result is a type error at runtime in one of the two configs.

Mitigation:

- Naming guidelines (section 4) reduce accidental collisions.
- At EvalConfig creation time (builder UX or API), a warning is surfaced if the new config declares a reference key already declared by another config on the same Eval with a different expected type. This is a non-blocking warning, not a hard rejection (the user may intentionally share keys across configs).
- The OPENS.md item "Reference-key collision warning" tracks the implementation of this warning.

---

## 4. Reference-key naming guidelines

Reference keys are plain strings (dict keys in `EvalInput.reference`). These naming conventions ensure consistency across the V2 ecosystem: first-party EvalConfigTypes, RAG templates (`components/29`), third-party plugins, and user-authored configs.

### 4.1. Canonical keys (first-party)

These keys are defined by first-party EvalConfigTypes and RAG templates. They are not reserved at the framework level (any config can use any key name), but these names carry established semantics and should not be repurposed.

| Key | Type | Semantics | Defined by |
|---|---|---|---|
| `reference_answer` | `str` | Gold-standard answer for correctness comparison. The factually correct, complete answer a human expert would give. | RAG templates (Answer Correctness), general `llm_judge` usage |
| `retrieved_context` | `list[str]` | Text chunks returned by a RAG retrieval system. Each element is one chunk. Order reflects retrieval rank where applicable. | RAG templates (Faithfulness, Context Relevance, Context Precision, Hallucination) |
| `ground_truth_context` | `list[str]` | Ideal source passages that should have been retrieved. Authoritative, curated set for evaluating retrieval quality against actual results. | RAG templates (Context Precision, optional) |
| `expected_classification` | `str` | Expected enum/label value for classifier tasks. | `exact_match` via `reference_key` |
| `expected_set` | `list[str]` | Expected set of values for set-containment checks. | `set_check` via `reference_key` |

**Consistency note:** The three RAG keys (`reference_answer`, `retrieved_context`, `ground_truth_context`) are used verbatim in `components/29_rag_judge_templates.md` sections 2.1-2.3 and throughout the six RAG template prompts via `{{ reference_data.retrieved_context }}`, `{{ reference_data.reference_answer }}`, `{{ reference_data.ground_truth_context }}`. The names here and there are identical; any rename must be coordinated.

### 4.2. `expected_*` convention

For reference data that represents a known-correct value to compare against:

- Use the prefix `expected_` followed by a descriptive noun: `expected_classification`, `expected_sentiment`, `expected_language`, `expected_tool_name`, `expected_summary`.
- This convention comes from kintsugi's data model (`expected_mode`, `expected_knowledge_files`, `expected_api_docs`) and generalizes naturally.
- The prefix makes the key self-documenting: it is clearly a ground-truth value, not an input or metadata value.

### 4.3. Domain-qualified names for ambiguous concepts

When a reference key name could be ambiguous across EvalConfigTypes, qualify it with the domain or eval type:

| Ambiguous | Better | Why |
|---|---|---|
| `criteria` | `llm_judge_criteria` | Multiple eval types could define "criteria." Qualifying with the consuming type avoids collision. |
| `context` | `retrieved_context` or `ground_truth_context` | "Context" alone is meaningless -- is it retrieved? Expected? System prompt context? |
| `answer` | `reference_answer` or `expected_answer` | "Answer" alone does not convey whether it is ground truth or model output. |
| `output` | `expected_output` | "Output" collides with the model's actual output. |

### 4.4. Conventions for new keys

When designing a new EvalConfigType or template that consumes reference data:

1. **Check the canonical list first.** If an existing canonical key fits the semantics, use it. Do not invent a synonym (`correct_answer` vs. `reference_answer`).
2. **Use `snake_case`.** All canonical keys use `snake_case`. Do not use `camelCase`, `PascalCase`, or `kebab-case`.
3. **Use `expected_*` for ground-truth values** that will be compared against model output.
4. **Use descriptive nouns, not verbs.** `retrieved_context` (noun), not `retrieve_context` (verb).
5. **Avoid single-word keys.** `answer`, `context`, `output`, `score` are too generic. Always qualify.
6. **Document the key's type and semantics** in the EvalConfigType's design doc, following the pattern in `components/29` section 2.

### 4.5. Third-party plugin keys

Third-party EvalConfigType plugins (per `components/80`) that consume reference data should:

1. Prefix keys with a package-scoped namespace if the key is plugin-specific: `myplugin_expected_entities`, `myplugin_rubric_items`.
2. Use canonical keys (`reference_answer`, `retrieved_context`) when the semantics match exactly -- do not reinvent.
3. Document consumed keys in the plugin's metadata (the extensibility contract in `components/80` specifies how plugins declare their reference-key requirements).

---

## 5. Per-case criteria via reference data (A1.4)

### 5.1. Decision

There is no separate `criteria` field on `EvalInput`. Per-case variation in evaluation checks is expressed through reference data keys that EvalConfigs opt to consume. Global checks ("the 12 things this eval cares about") live on EvalConfig properties (e.g., in the `prompt_template` for `llm_judge`, in the `pattern` for `pattern_match`).

### 5.2. Rationale

Kintsugi's per-case criteria pattern (where each test case carries its own `deterministic_criteria` and `semantic_criteria` arrays) decomposes cleanly into the A1.2/A1.3 mechanism without a new field:

- **Per-case selection of typed checks:** Model each check as its own EvalConfig with a typed `reference_key`, or expose a `reference["check_names"]: list[str]` for a single config to dispatch from a registry.
- **Per-case content for judge criteria:** Store as `reference["llm_judge_criteria"]: list[str]` (or a richer structure), consumed by an `llm_judge` EvalConfig whose prompt template iterates over the criteria list.

Adding a first-class `criteria` field on `EvalInput` would create a parallel structure to reference data that serves the same purpose (carrying per-case ground-truth-like data) but with a different access pattern, different validation story, and different builder UX. The flat dict already handles this.

### 5.3. Per-case criteria with `llm_judge`

The primary consumer of per-case criteria is the enhanced `llm_judge` type (`components/21`). The pattern:

```python
# On EvalInput.reference:
{
    "llm_judge_criteria": [
        "Response correctly identifies the root cause",
        "Response suggests at least one actionable fix",
        "Response does not hallucinate error codes"
    ]
}
```

```python
# On EvalConfig.properties (LlmJudgeProperties):
LlmJudgeProperties(
    prompt_template="""\
Evaluate the following response against each criterion.
For each criterion, provide a pass/fail verdict with reasoning.

Criteria:
{% for criterion in reference_data.llm_judge_criteria %}
{{ loop.index }}. {{ criterion }}
{% endfor %}

Response to evaluate:
{{ final_message }}

Provide a JSON verdict for each criterion...
""",
    required_var=["reference_data.llm_judge_criteria"],
    ...
)
```

This pattern gives per-input criteria with per-criterion verdicts, using the existing Jinja2 template infrastructure (`components/40`) and the existing reference-data dict. No new framework abstractions are needed.

### 5.4. Global vs. per-case criteria interaction

A1.4 explicitly rules out "this eval has 5 global checks PLUS case 47 has 3 extra checks" as a first-class pattern. If you need that, the answer is to spin off case 47 into its own eval (consistent with the "many small evals" philosophy from A0.2).

Possible workarounds within the existing mechanism (no framework support -- user-authored):

- An `llm_judge` template could hardcode global criteria in the template text and conditionally append per-case criteria from `reference_data.extra_criteria` if present. This works but is the user's responsibility to author.
- Two EvalConfigs on the same Eval: one with global criteria in the template, one consuming per-case criteria from reference data. Both run against every EvalInput; the per-case config skips inputs that lack the reference key.

### 5.5. Per-case criteria for deterministic checks

Deterministic EvalConfigTypes do not have a "criteria list" concept -- they check one specific thing (exact match, pattern match, set containment). Per-case variation for deterministic checks is expressed through the `reference_key` mechanism:

- Different EvalInputs can have different values for `expected_classification`, and the `exact_match` config compares against whatever value is present.
- An EvalInput that does not have the relevant reference key is skipped (C.runner.1).

This is not "per-case criteria" in the kintsugi sense (a list of checks per case). It is per-case ground-truth values for a single global check. The distinction matters: kintsugi's per-case criteria are load-bearing for its tiered composite scoring model (`blocking` vs. `quality` tiers). In V2, the equivalent is achieved by having multiple EvalConfigs, each checking one dimension, with composite scoring deferred to post-V2 (`composite` type per A2.4).

---

## 6. Reference data in `EvalTaskInput` assembly

When the eval runner prepares a case for scoring, it assembles an `EvalTaskInput` (defined in `components/40` section 2) that includes the reference data:

```python
class EvalTaskInput(BaseModel):
    final_message: str | dict[str, Any]
    trace: list[ChatCompletionMessageParam] | None = None
    reference_data: dict[str, JsonValue] | None = None  # <-- from EvalInput.reference
    task_input: str | dict[str, Any]
```

The mapping is direct: `EvalTaskInput.reference_data = eval_input.reference`. The field is renamed from `reference` to `reference_data` to avoid collision with Pydantic's internal `reference` handling and to be self-documenting in template expressions (`{{ reference_data.reference_answer }}` reads better than `{{ reference.reference_answer }}`).

Templates access reference data as `reference_data.<key>`:

- `{{ reference_data.reference_answer }}` -- string access
- `{% for chunk in reference_data.retrieved_context %}` -- list iteration
- `{{ reference_data.expected_classification }}` -- used by simple-check types internally (not in templates, but same dict)

This is consistent with `components/40` section 2 (reserved top-level names: `final_message`, `trace`, `reference_data`, `task_input`) and `components/29` (all six RAG templates use `reference_data.<key>` syntax).

---

## 7. Corrected-output promotion

Corrected-output promotion (promoting a human-corrected output to reference data) is **out of scope for V2.0**. The Feedback Pipeline project was punted on 2026-06-03 (see reference/ALIGNMENT.md Batch F, A0.5 updated). The V1 `TaskRun.repaired_output` field exists but is not wired to evals (per `reports/kiln_reference_data_today.md` section 6).

The V2 reference-data shape (flat dict) is compatible with future corrected-output promotion: a promotion workflow would write the corrected output to `reference["reference_answer"]` (or another appropriate key) on the relevant EvalInput. No schema changes are needed to support this in the future. The `reference` dict is intentionally open-ended to accommodate workflows like this without pre-committing the schema.

---

## 8. V1 comparison

V1's reference-data mechanism is documented in `reports/kiln_reference_data_today.md`. Key differences:

| Aspect | V1 | V2 |
|---|---|---|
| Shape | `str | None` (single string on `EvalRun.reference_answer`, denormalized from `TaskRun.output.output`) | `dict[str, JsonValue] | None` (structured dict on `EvalInput.reference`) |
| Scope | Per-EvalRun (denormalized copy) | Per-EvalInput (source of truth; no denormalization onto EvalRun) |
| Multi-field | No -- single string. Classifier multi-field ground truth requires JSON-in-string workaround. | Yes -- arbitrary keys. `expected_classification`, `expected_sentiment`, etc. are separate keys. |
| Multi-config | All configs see the same string | All configs see the same dict, but each declares which keys it consumes |
| Per-case criteria | Not supported | Via reference keys (e.g., `llm_judge_criteria: list[str]`) |
| Validation | Eval-level `EvalDataType.reference_answer` toggle; validator on EvalRun | Per-config at bind time; `required_var` / `reference_key` mechanisms |

V1 reference-data paths continue to work unchanged for V1 EvalConfigs (per A0.1). V2 EvalConfigs use the new `EvalInput.reference` dict exclusively.

---

## Opens

(None. All three alignment refs are fully covered; no implementation-blocking questions remain for this file's scope. Reference-key collision warning and naming-guideline enforcement are tracked in OPENS.md as runner/tooling concerns, not reference-data shape concerns.)
