---
status: complete
---

# Phase 8: Model entry, prerelease whitelist, and the live smoke test

## Overview

Phase 3 added the Jev model entry with a removal `TODO`; Phase 6 removed it, and a revert
restored it for manual testing. This phase makes the entry permanent, registers Jev in the
prerelease whitelist, and adds the first tests in the project that call TypeSafe AI for
real.

Everything up to now fakes the HTTP boundary, so the suite only proves Kiln agrees with
itself about the System One wire contract. The two smoke tests are where that contract
meets the API: a structured task run through `JevAdapter` covering every mapped property
shape, and a V2 LLM Judge with a Jev judge.

The plan and the functional spec put this phase in a separate pull request off `main`,
after a client release carries the provider. The user decided to land it on this branch
instead so the provider can be tested. The deviation is recorded in the functional spec's
release gating section: the mechanical gate (a red `debug_detector` check on the removal
`TODO`) is replaced by the pull request staying a work in progress.

## Steps

1. **`libs/core/kiln_ai/adapters/ml_model_list.py`** — delete the three-line
   `# TODO: remove before merge; ...` comment above the Jev `KilnModel`. Keep the
   `# Jev 1.13` header comment (most entries in the file carry a friendly-name header) and
   the entry, `ModelFamily.jev` and `ModelName.jev_1_13` unchanged.

2. **`libs/core/kiln_ai/adapters/pytest_prerelease_whitelist.py`** — add a new list:

   ```python
   PRERELEASE_JEV_MODELS: list[tuple[str, str]] = [
       ("jev_1_13", ModelProviderName.typesafe.value),
   ]
   ```

   Not an entry in `PRERELEASE_CHAT_MODELS`: that list feeds LiteLLM adapter smoke tests,
   and `lite_llm_core_config_for_provider` / `get_litellm_provider_info` raise for
   `typesafe` by design, so an entry there would fail by construction. A comment on the new
   list says so, and the new smoke test parametrizes over it, so the list has a real
   consumer and the prerelease pin sweep sees the Jev slug.

3. **`libs/core/kiln_ai/adapters/jev/test_jev_paid_smoke.py`** (new) — the two live tests,
   in the `jev` package next to the client because they span the adapter and the judge.
   Both are `@pytest.mark.paid` and `@pytest.mark.prerelease`, both skip when
   `TYPESAFE_API_KEY` is unset, and both begin with a preflight that resolves the entry's
   `model_id` through `kiln_model_provider_from` and asserts it against a live
   `GET /v1/models`, so an unconfirmed model id fails by name instead of as a 422.

   ```python
   async def _assert_model_id_is_live(model_name: str, provider: str, api_key: str) -> str
   ```

4. **`specs/projects/jev_provider/functional_spec.md`** — rewrite steps 2 and 3 of the
   "Model entry and release gating" list to describe what actually happened, keeping the
   reason the entry must not reach `main` before a release.

5. **`specs/projects/jev_provider/implementation_plan.md`** — tick Phase 8, with a
   parenthetical noting the `GET /v1/models` model-id confirmation is still the user's to
   run.

## Tests

- `test_jev_structured_task_run_live` — a five-property output schema covering every mapped
  shape (string enum, bounded integer, integer enum, boolean, number 0 to 1) run through
  `adapter_for_task`. Asserts the adapter resolved is `JevAdapter`; the output validates
  against the task's output schema and each value has the right Python type and range; the
  one unambiguous classification is right (a mangled state would give a coin flip);
  `jev_probabilities` is keyed by schema property with keys drawn from the schema's own
  values and each distribution summing to 1; `jev_confidence` is a float in 0 to 1 for
  choice and score properties and `None` for the two noul properties; the decoded value for
  each choice property appears in its own distribution; the trace has three messages and
  usage reports tokens.
- `test_jev_v2_llm_judge_live` — a V2 LLM Judge whose judge model is Jev, over an eval with
  one score of each discrete rating type. Asserts no skip; the score keys are exactly the
  three properties; `pass_fail` is in {0, 1}, `pass_fail_critical` in {-1, 0, 1},
  `five_star` a whole number in 1 to 5; the two unambiguous scores are passes; and
  `jev_probabilities` / `jev_confidence` are keyed by score with labels drawn from the eval
  score schema.
