# Cluster J — Save-time validation gaps

## 22-R46: expected_tools must be non-empty list at save time

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** MISSING
- **Corrected severity:** minor
- **Reasoning:** The spec at component 22 section 6 explicitly states: `tool_call_check | expected_tools: non-empty list.` The code at `eval.py:166` declares `expected_tools: list[ToolCallSpec]` with no `min_length=1` field annotation or model_validator enforcing non-emptiness. An empty list can be saved. At runtime: `match_mode="all"` and `match_mode="ordered"` would vacuously pass (the for loop never runs and `expected_idx == 0 == len([])` is True); `match_mode="any"` would always fail (found_any stays False); `match_mode="never"` vacuously passes. This is a real footgun — a user who accidentally submits an empty expected_tools gets a check that always passes or always fails depending on mode, with no save-time warning.
- **Evidence:**
  - Spec: `components/22_type_deterministic_basics.md:516` — `tool_call_check | expected_tools: non-empty list.`
  - Code absence: `libs/core/kiln_ai/datamodel/eval.py:164-168` — no min_length or validator.
  - Runtime impact: `libs/core/kiln_ai/adapters/eval/v2_eval_tool_call_check.py:96-108` — empty list + "all"/"ordered" = vacuous pass.
  - No intentional divergence found in RUN_NOTES.md or git history.

---

## 22-R47: ArgMatch regex values validated via re.compile at save time

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** MISSING
- **Corrected severity:** minor
- **Reasoning:** The spec at component 22 section 6 explicitly states: `If any ArgMatch.match_mode="regex": re.compile(str(value)).` The `ArgMatch` model at `eval.py:154-156` has no model_validator or field_validator that calls `re.compile`. Contrast with `PatternMatchProperties` (`eval.py:114-122`) which does have a `validate_pattern` model_validator that compiles the regex at save time — proving the pattern was intended to be followed. At runtime, `v2_eval_tool_call_check.py:161-164` wraps `re.search` in a try/except that returns False on `re.error`, so an invalid regex silently never matches rather than crashing. This means a user who makes a typo in a regex value gets a check that silently always fails for that argument, with no save-time feedback.
- **Evidence:**
  - Spec: `components/22_type_deterministic_basics.md:516` — `If any ArgMatch.match_mode="regex": re.compile(str(value)).`
  - Code absence: `libs/core/kiln_ai/datamodel/eval.py:154-156` — no validator.
  - Comparison: `eval.py:114-122` — `PatternMatchProperties.validate_pattern` does compile at save time.
  - Runtime behavior: `v2_eval_tool_call_check.py:161-164` — catches `re.error`, returns False.
  - No intentional divergence found in RUN_NOTES.md or git history.

---

## 22-R62: reference_key save-time validation: non-empty string (min_length=1)

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** MISSING
- **Corrected severity:** minor
- **Reasoning:** The spec at component 22 section 1 (line 41) explicitly states: `Save-time validation: non-empty string (Pydantic min_length=1).` All three reference_key fields (`eval.py:96,129,144`) are declared as `reference_key: str | None = None` with no `min_length` constraint. The XOR validators check `is None` equality, so `reference_key=""` passes validation (empty string is not None). At runtime, `check_reference_key` at `v2_eval_helpers.py:62` checks `if reference_key not in eval_input.reference_data` — a key named "" is vanishingly unlikely to exist in real data, so the case would always be skipped with `missing_reference_key`. This is a mild footgun: a user who accidentally submits an empty string gets a config that always skips (never actually evaluates), with no save-time warning.
- **Evidence:**
  - Spec: `components/22_type_deterministic_basics.md:41` — `Save-time validation: non-empty string (Pydantic min_length=1).`
  - Code absence: `libs/core/kiln_ai/datamodel/eval.py:96,129,144` — `reference_key: str | None = None` with no min_length.
  - XOR pass: `eval.py:100-101` — `(self.expected_value is None) == (self.reference_key is None)` — `""` is not None, passes.
  - Runtime impact: `v2_eval_helpers.py:62-66` — `""` key not in dict → always skips.
  - No intentional divergence found in RUN_NOTES.md or git history.

---

## 21-R41 / 40-R31: Useless-template rejection should use AST-based variable analysis

- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** PARTIAL
- **Corrected severity:** minor
- **Reasoning:** The spec at `components/40_template_and_extraction.md:213-219` explicitly requires: "Save-time validation parses the template AST to find variable references; rejects the save unless at least one reference is: A reserved top-level var that's NOT reference_data (final_message, trace, or task_input), OR a sub-path of one of those." The code at `eval.py:706-712` uses a surface-level string check: `if "{{" not in tmpl_source and "{%" not in tmpl_source`. This is weaker than the spec requires. However, it IS a partial implementation — it does catch the zero-variable case (pure literal templates). It misses the reference_data-only case.

  **Concrete bypass case:** `{{ reference_data.expected_output }}` — contains `{{` so passes the surface check, but only references `reference_data` (never touches `final_message`, `trace`, or `task_input`). Such a template would produce the same judge prompt regardless of the model's actual output, making the eval meaningless. The AST-based check would detect that the only top-level variable referenced is `reference_data` and reject it.

  Severity remains minor because: (1) this is an edge case — typical llm_judge templates reference `final_message` because that's the model output being judged; (2) a template referencing only `reference_data` would still "work" (produce a score), it would just score independent of model output — a logic error rather than a crash; (3) the current check does catch the degenerate no-Jinja case.

- **Evidence:**
  - Spec: `components/40_template_and_extraction.md:213-219` — full AST-based requirement quoted above.
  - Code: `libs/core/kiln_ai/datamodel/eval.py:706-712` — `if "{{" not in tmpl_source and "{%" not in tmpl_source`.
  - Bypass: Template `{{ reference_data.expected_output }}` passes surface check but violates spec intent.
  - No intentional divergence found in RUN_NOTES.md or git history.
