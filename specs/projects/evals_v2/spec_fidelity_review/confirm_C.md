# Cluster C — Eval.evaluation_data_type default

## 10-R12: CONTRADICTED/major — Eval.evaluation_data_type defaults to EvalDataType.final_answer instead of None

### Skeptic Verdict: REFUTED_INTENTIONAL

### Corrected Verdict: NOT A DEFECT (spec stale; code correct)

### Corrected Severity: none

### Reasoning

The `final_answer` default is an **intentional divergence** from the original spec text in `components/10_data_model.md`, made for V1 backwards-compatibility reasons. This was explicitly recognized, verified against code, and documented during the deep-cr-cleanup Phase 6 (commit `7c1e44294`).

**Why the default matters for V1:**
- V1 Eval files on disk may omit `evaluation_data_type` (older format). Pydantic loads them using the default.
- The `validate_output_fields` validator (eval.py:491-516) reads `parent_eval.evaluation_data_type` for V1 EvalRuns. A `None` default would make V1 Evals ambiguous and could break this validator.
- `final_answer` is the correct V1 semantic (evaluate the model's final answer unless explicitly configured otherwise).

**Why it is inert for V2:**
- V2 runner path (`_run_v2_job`, eval_runner.py:372+) never reads `evaluation_data_type`.
- `validate_output_fields` (eval.py:494-495) returns early for `config_type == EvalConfigType.v2`.
- `validate_reference_answer` (eval.py:592-593) returns early for V2 config_type.
- The `GEval` adapter (g_eval.py:297-312) reads this field, but only runs for V1 configs.
- V2 Evals that need `None` semantics set it explicitly at construction time (e.g., test at test_eval_api.py:3650).

**The spec was updated:** `components/15_v1_v2_coexistence.md` section 4.1 was explicitly updated in Phase 6 to show `= EvalDataType.final_answer` with a rationale paragraph. The stale text is in `components/10_data_model.md` section 1, which was not updated simultaneously.

### Evidence

- **Code:** `libs/core/kiln_ai/datamodel/eval.py:793-795` — `default=EvalDataType.final_answer`
- **Intentional decision:** commit `7c1e44294` (Phase 6) — "change evaluation_data_type default from None to EvalDataType.final_answer, matching eval.py:793. Document the V1 back-compat rationale (omitted field loads as true V1 behavior)."
- **Updated spec:** `specs/projects/evals_v2/components/15_v1_v2_coexistence.md:215` — shows `= EvalDataType.final_answer` with back-compat rationale
- **RUN_NOTES.md line 22:** Phase 6 outcome states "5.1 final_answer default documented; both verified vs code"
- **V2 inertness:** eval_runner.py:372-439 (V2 job path never reads the field); eval.py:494-495 (V2 bypass in validate_output_fields); eval.py:592-593 (V2 bypass in validate_reference_answer)
- **Stale spec text:** `specs/projects/evals_v2/components/10_data_model.md` section 1 still shows `= None` — this doc was not updated in Phase 6 (only components/15 was). The 10_data_model.md text is stale and should be updated for consistency.

### Recommendation

Update `components/10_data_model.md` section 1 schema to show `evaluation_data_type: EvalDataType | None = EvalDataType.final_answer` to match components/15 and eliminate the spec-internal contradiction.
