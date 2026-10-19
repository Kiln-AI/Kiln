---
status: complete
---

# Phase 4: Eval integration

## Overview

Make a Jev judge work in Kiln's two LLM judges, and make the eval runner retry Jev's
transient failures the way it retries LiteLLM's.

Almost nothing needs to change: both judges build their score schema with
`BaseEval.build_score_schema(allow_float_scores=False)` and select their adapter through
`adapter_for_task`, which Phase 3 taught to route on `KilnModelProvider.adapter`. So the
work here is one line of classification in `eval_runner` plus the tests that hold the two
load-bearing claims the spec makes:

1. Every shape `build_score_schema(allow_float_scores=False)` can emit maps onto a Jev
   question — five_star to `score`, pass_fail and pass_fail_critical to `choice`. If a
   future rating type or description change broke that, a Jev judge would fail at run
   time on a schema Kiln itself generated.
2. A Jev judge scores through both judges end to end, with only the HTTP client faked.

`g_eval=True` stays out of scope: `v2_eval_llm_judge.py` guards on `supports_logprobs`
before it reaches `adapter_for_task`, and the Jev entry sets `supports_logprobs=False`.
A test pins that ordering, since the guard is what keeps Jev out of a scoring mode it
cannot support.

## Steps

1. `libs/core/kiln_ai/adapters/eval/eval_runner.py` — import `JevApiError` from
   `kiln_ai.adapters.jev` and classify it in `_is_retryable_error`, after the LiteLLM
   check and before the output-schema `ValueError` check:

   ```python
   # Jev errors carry their own transience (429, 5xx, timeouts, connection failures);
   # the adapter never retries, so the runner's retries are the only ones.
   if isinstance(e, JevApiError):
       return e.retryable
   ```

2. New `libs/core/kiln_ai/adapters/eval/test_jev_judge.py`. Shared helpers:

   - `ScriptedJevClient(JevClient)`: takes `{property_key: desired output value}`, reads
     the questions off the request it is given, and builds a wire answer of the matching
     type (`ChoiceAnswer` / `ScoreAnswer` / `NoulAnswer`) that decodes back to the desired
     value. It records the requests it received. Nothing about the mapping is
     precomputed, so the real `JSONSchema2Jev` and `JevResult2JsonSchema` run in both
     directions.
   - `jev_judge_client` fixture: patches
     `kiln_ai.adapters.model_adapters.jev_adapter._client_from_config` to return the
     scripted client, and `kiln_model_provider_from` in both
     `kiln_ai.adapters.adapter_registry` and
     `kiln_ai.adapters.model_adapters.base_adapter` to a TypeSafe
     `KilnModelProvider(adapter=ModelAdapterId.jev, model_id="jev-1.13.0")`. Real routing
     therefore runs; only the network and the model-list lookup are replaced, so the
     tests survive Phase 6 removing the model entry.
   - Real `Project` / `Task` / `Eval` / `EvalConfig` objects under `tmp_path`, with
     output scores covering all three rating types.

3. `test_eval_runner.py`: add `JevApiError` cases to the existing
   `test_is_retryable_error_returns_true` / `..._returns_false` parametrizations, and one
   test for the shape the runner actually sees — a `JevApiError` wrapped in
   `KilnRunError` by the base adapter.

## Tests

`test_jev_judge.py`:

- `test_eval_score_schema_maps_to_jev_questions`: the real
  `build_score_schema(allow_float_scores=False)` output for five_star, pass_fail and
  pass_fail_critical scores converts, and the kinds are `score`, `string_choice`,
  `string_choice`; the score question's criteria are `["1".."5"]` with `minimum == 1`,
  and the choice criteria are bare labels (`{"pass": None, "fail": None}` and the
  three-label version).
- `test_eval_schema_question_instructions_carry_the_rubric`: each question's
  `instructions` is the property description, so the scoring instruction and the scale
  sentence reach Jev without eval-specific handling.
- `test_legacy_llm_as_judge_scores_with_jev`: `GEval(config_type=llm_as_judge).run_eval`
  returns the expected scores, and Jev's probabilities and confidence come back in the
  intermediate outputs.
- `test_legacy_judge_request_state_carries_the_run_description`: the scripted client's
  recorded request has the judge's input in `state["input"]` and the judge system
  instruction in `state["task_instructions"]`.
- `test_v2_llm_judge_scores_with_jev`: `LlmJudgeEval.evaluate` (g_eval off) returns the
  same scores and a populated `usage`.
- `test_v2_g_eval_rejected_before_adapter_selection`: with `g_eval=True` and a provider
  entry reporting `supports_logprobs=False`, `evaluate` raises before `adapter_for_task`
  is called.
- `test_judge_api_error_is_retryable`: a retryable `JevApiError` raised by the judge's
  client surfaces from `run_eval` and `_is_retryable_error` classifies the wrapped error
  as retryable.

`test_eval_runner.py`:

- retryable-true parametrization gains a `JevApiError(retryable=True)`.
- retryable-false parametrization gains a `JevApiError(retryable=False)`.
- `test_is_retryable_error_unwraps_jev_api_error`: `KilnRunError` wrapping a retryable
  `JevApiError` classifies as retryable.
