# Cluster M -- Data-model field fidelity (components/10, 40)

Skeptic review date: 2026-06-23

---

## 10-R23: EvalConfig.description field absent

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** MISSING
- **Corrected severity:** minor
- **Reasoning:** The spec at components/10 section 2.1 explicitly defines `description: str | None = None` on EvalConfig. The code at eval.py:610-633 has no `description` field, and it is not inherited from KilnParentedModel or KilnBaseModel (verified via basemodel.py -- no `description` field on parent classes). The field was never present in the V1 EvalConfig either (verified via `git show bb9a93223^:libs/core/kiln_ai/datamodel/eval.py` lines 259-283). No entry in RUN_NOTES.md addresses this omission, and no commit removes it intentionally.
- **Impact:** Cosmetic / metadata. EvalConfig cannot carry a human-readable description. This does not affect eval execution, scoring, or any runtime behavior. It is a missing UI/metadata convenience field.
- **Evidence:** eval.py:610-633 (no description field). Spec: components/10_data_model.md section 2.1 line 105 `description: str | None = None`. Pre-V2 code (git show bb9a93223^) also lacks description -- it was a spec-only addition that was never implemented.

---

## 10-R66: MultiTurnSyntheticEvalInputData.synthetic_user_info uses dict instead of typed Pydantic model

- **Skeptic verdict:** REFUTED_DEFERRED
- **Corrected verdict:** DEFERRED_OK
- **Corrected severity:** none (not a defect)
- **Reasoning:** The spec at components/10 section 4.3 says: "SyntheticUserInfo is a typed Pydantic model (not a flat dict). Its field list is owned by the parallel multi-turn-synthetic project (C.5). The model carries an explicit version field or equivalent discriminator for forward evolution." The key clause is "Its field list is **owned by the parallel multi-turn-synthetic project (C.5)**." The overview (components/00 section 4) says: "Evals V2 commits to the **contract surface only** -- components/26_type_multi_turn_synthetic.md captures what V2 provides... and what the parallel project owns (field list, scoring, runner design for multi-turn)." The file components/26_type_multi_turn_synthetic.md does not even exist. The parallel project has not been authored. Using `dict[str, JsonValue]` as a placeholder for a typed model whose fields are owned by a project that hasn't shipped yet is the correct forward-compatible implementation. The dict is structurally equivalent to "typed model with unknown fields" -- when the parallel project ships, the dict can be narrowed to a typed model without breaking existing serialized data. The spec itself says the field list is deferred; `dict` is the natural stand-in.
- **Impact:** None. No caller currently constructs or consumes `MultiTurnSyntheticEvalInputData` in any runtime path (multi-turn eval runner is not implemented). The contract is a placeholder for a future project.
- **Evidence:** eval.py:277 `synthetic_user_info: dict[str, JsonValue] = {}`. Spec: components/10_data_model.md section 4.3, line 425 "Its field list is owned by the parallel multi-turn-synthetic project (C.5)." components/00_overview.md section 4 "Parallel-project coordination" (lines 152-154). No components/26 file exists.

---

## 10-R75: EvalRun.scores has default={} not shown in spec

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** PARTIAL
- **Corrected severity:** trivial
- **Reasoning:** The spec at components/10 section 5.1 shows `scores: EvalScores  # Dict[str, float]` with no default. The code at eval.py:451-453 has `scores: EvalScores = Field(default={}, ...)`. However, the spec in section 5.4 explicitly says "Carry no scores (or empty scores)... when skipped_reason is not None, allow empty/None scores." An empty-dict default is functionally required to support skipped runs (which have no scores) and is consistent with the spec's skip semantics. The spec's omission of a default is a spec authoring shorthand (showing the type), not a prohibition on defaults. The `default={}` is a pragmatic implementation choice that aligns with the spec's skip behavior.
- **Impact:** None in practice. Skipped runs need empty scores; the default enables that without requiring callers to explicitly pass `{}`. Non-skipped runs always populate scores via the runner.
- **Evidence:** eval.py:451-453 `scores: EvalScores = Field(default={}, ...)`. Spec: components/10_data_model.md section 5.1 line 462 `scores: EvalScores # Dict[str, float]`, section 5.4 lines 514-515 "Carry no scores (or empty scores)... allow empty/None scores."

---

## 40-R01: EvalTaskInput.final_message is str only, not str | dict[str, Any]

- **Skeptic verdict:** REFUTED_INTENTIONAL
- **Corrected verdict:** NOT A DEFECT (spec is stale)
- **Corrected severity:** none
- **Reasoning:** The spec at components/40 section 2 defines `final_message: str | dict[str, Any]` with the note "String for plain-text tasks; dict for tasks with `output_json_schema`." However, the actual Kiln data model stores ALL task outputs as strings, even for structured JSON tasks. `TaskOutput.output` at task_output.py:332 is typed `str` (with description "JSON formatted for structured output, plaintext for unstructured output"). The `validate_output_format` method (task_output.py:343-352) validates by `json.loads(self.output)` -- i.e., the output is always a string, just sometimes a JSON-serialized string. Both factory methods (`from_task_run` at eval.py:343 and `from_eval_input` at eval.py:368) source `final_message` from `task_run.output.output` / `run_output.output.output`, which is always `str`. There is no code path that could ever produce a dict for `final_message`. The spec's `str | dict[str, Any]` type anticipated a parsed-JSON representation that does not match how Kiln actually stores data. The code correctly reflects the real data model. The spec is aspirational on this point but the implementation is correct for the actual data source.
- **Impact:** None. JSON task outputs are available as serialized strings. Jinja2 templates can still access structured fields via `{{ final_message }}` after parsing, since `model_dump()` provides the string and Jinja2 templates could use custom logic or `extract()` expressions. In practice, templates working with structured outputs parse the JSON string -- this is the actual Kiln pattern.
- **Evidence:** eval.py:315 `final_message: str`. task_output.py:332 `output: str`. task_output.py:343-352 `json.loads(self.output)`. eval.py:343,368 factory methods source from `.output.output` (str).

---

## 40-R02: EvalTaskInput.task_input is str | None, not str | dict[str, Any]

- **Skeptic verdict:** REFUTED_INTENTIONAL
- **Corrected verdict:** NOT A DEFECT (spec is stale)
- **Corrected severity:** none
- **Reasoning:** Same data-model grounding as 40-R01. `TaskRun.input` at task_run.py:37 is typed `str` (with description "JSON formatted for structured input, plaintext for unstructured input"). All code paths that build `EvalTaskInput` set `task_input` from `task_run.input` (str, eval.py:346) or `eval_input.data.user_message.text` (str, eval.py:371). There is no code path that produces a dict. The spec's `str | dict[str, Any]` type was aspirational. Regarding optional vs non-optional: the code has `str | None = None` while the spec says `str | dict[str, Any]` (non-optional). In practice, both factory methods always supply a string value -- no code path ever leaves `task_input` as None. The `None` default is a defensive guard for direct construction outside the factory methods. Since `task_input` is always set via the factories, the optionality has zero runtime impact.
- **Impact:** None. Both the `str`-only type and the `| None` default match the actual Kiln data model and usage patterns. No capability is dropped.
- **Evidence:** eval.py:326 `task_input: str | None = Field(default=None, ...)`. task_run.py:37 `input: str`. eval.py:346,371 factory methods always supply a string. No code path sets `task_input=None` (verified via grep).
