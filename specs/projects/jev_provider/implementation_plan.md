---
status: complete
---

# Implementation Plan: Jev Provider (TypeSafe AI System One)

Phases 1 to 6 are one PR. Phase 7 is a separate PR merged only after a client release carries the provider (see the functional spec's release gating). Phase 8 is optional and opt-in: stop and ask before starting it.

## Phases

- [x] Phase 1: Provider plumbing. `ModelProviderName.typesafe`, `typesafe_api_key` config, `provider_tools` (friendly name, `provider_warnings`, LiteLLM cases that raise), `utils/litellm.py` case, `connect_typesafe` (verify first whether `GET /v1/models` rejects a bad key; else the minimal-POST check) plus connect/disconnect dispatch in `provider_api.py`, and the standard provider tests.
- [ ] Phase 2: The reusable `jev_jsonschema` module (wire models, `JSONSchema2Jev`, `JevResult2JsonSchema`, options, errors) and `JevClient` on top of it, per the two component docs. No `kiln_ai` imports inside the module.
- [ ] Phase 3: Routing and adapter. `ModelAdapterId` enum and `KilnModelProvider.adapter` field, `default_adapter_for_provider` wired into user and custom model construction, `adapter_for_task` dispatch, `JevAdapter` with `build_jev_state`, and the Jev model entry with its removal `TODO`. Tests including end-to-end through `BaseAdapter.invoke`.
- [ ] Phase 4: Eval integration. `eval_runner` retryable classification for `JevApiError`; tests running the legacy LLM-as-Judge and the V2 LLM Judge (g_eval off) with a Jev judge through a fake client; the eval-schema contract test (five_star, pass_fail, pass_fail_critical map to score, choice, choice).
- [ ] Phase 5: Web UI and docs. Provider card, status wiring, `provider_name_map`, provider image (official mark from `specs/projects/jev_provider/assets/typesafe_jev_logo.svg`), regenerated `api_schema.d.ts`, one connect-providers test, `.agents/scripts/provider_utils.py`, the three synced skill-doc copies. Run the `kiln-ui` skill before touching `.svelte` files. Full `checks.sh`.
- [ ] Phase 6: Pre-merge. Remove the Jev model entry and its `TODO` (the `ModelFamily`/`ModelName` members go with it), confirm no `TODO` remains, full `checks.sh`, open the PR.
- [ ] Phase 7 (separate PR, after release): Re-add the `ml_model_list.py` entry, confirmed against `GET /v1/models`; prerelease whitelist; a `--runpaid` smoke test (one structured task, one V2 judge) skipped without `TYPESAFE_API_KEY`.
- [ ] Phase 8 (optional, opt-in, ask first): Probability-weighted scoring. `supports_probability_scores` flag and `ModelDetails` exposure, the three availability sites, "Probability-weighted" label and copy, `RunOutput.answer_probabilities`, `scores_from_answer_probabilities` fast path in `build_g_eval_score`, tests for both judges in that mode.
- [ ] **Phase 9: Backlog.** Review open backlog items with the user, then close or dismiss each through the standard phase flow.
