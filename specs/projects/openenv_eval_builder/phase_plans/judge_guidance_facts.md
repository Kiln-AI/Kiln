---
status: complete
---

# Judge guidance holds environment facts only

## Overview

The grounded reference's Expected outcome, Allowed and Must not happen sections restated and
interpreted the eval's specification. The judge already has the specification, and a second policy
written by the grounding agent can disagree with it. The reference keeps only what the environment
shows: the starting point, the facts with their evidence, and one short paragraph of expected
outcome facts.

## Steps

1. `libs/core/kiln_ai/eval_grounding/models.py`: `GroundedReference` keeps `starting_point: str`
   (what the environment holds before the conversation, including setup the agent added) and
   `facts`, and turns `expected_outcome` into one `str` (the correct answer and any end-state
   change, as facts; may name plausible wrong answers as facts). Drop `allowed` and
   `must_not_happen`. `result_json_schema` follows for both answer styles. `from_model_output`
   needs no change beyond the shape (it only touches facts).
2. `judge_guidance.py`: three headings, Starting point, Facts, Expected outcome. An empty string
   or list renders "None.".
3. `prompt.py`: skeleton matches the new fields. Replace the must_not_happen paragraph with
   expected-outcome guidance (results, not steps; check in the rehearsal what actually changed).
   Add rules: don't restate or interpret the specification, the judge has it; write the data the
   scenario calls for as the scenario describes it, without softening, masking or sanitizing it.
4. `app/desktop/studio_server/utils/eval_builder_utils.py`: the grounded judge instructions say to
   grade against the specification, using the guidance as the facts of the environment; no
   "Must not happen".
5. `eval_builder_models.py` field description and the `create_eval_config` judge hint drop the old
   section names.
6. Specs: functional_spec.md Reference and Judge, architecture.md models / rendering / judge,
   ui_design.md section list and hint. Docs draft (separate repo, not committed): the one sentence
   naming "what must not happen".

## Tests

- `test_models.py`, `test_agent.py`, `test_batch.py`, dev `test_ground_cases.py`,
  `test_eval_builder_grounding.py`: fixtures use the new shape; a result with a list-typed
  `expected_outcome` or an extra `must_not_happen` key is rejected by the schema shape.
- `test_judge_guidance.py`: three headings in order; empty starting point, facts and expected
  outcome each render "None.".
- `test_prompt.py`: the new rules are present and the old must_not_happen rule is gone.
- `test_eval_builder_api.py`: the grounded template mentions the specification and not
  "Must not happen".
