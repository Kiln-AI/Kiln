---
status: draft
---

# Implementation Plan: Jev Provider (TypeSafe AI System One)

Phases 1 to 5 can merge as one PR (nothing references the provider until Phase 6 lands). Phase 6 is a separate PR, merged only after a client release containing Phases 1 to 5 is live, per the release-gating rule in `architecture.md`.

## Phases

- [ ] Phase 1: Provider plumbing. `ModelProviderName.typesafe`, `typesafe_api_key` config, `provider_tools` (friendly name, warnings, LiteLLM cases that raise), `utils/litellm.py` case, `connect_typesafe` + connect/disconnect dispatch in `provider_api.py`, and the standard provider tests. No UI yet.
- [ ] Phase 2: Jev client and schema mapping (`adapters/jev/`), pure and fully unit tested per the two component docs.
- [ ] Phase 3: `JevAdapter`, `RunOutput.answer_probabilities`, routing in `adapter_for_task`, `eval_runner` retryable classification. Tests use a patched `built_in_models` fixture for the Jev model entry and a fake client. Includes an end-to-end test through `BaseAdapter.invoke`.
- [ ] Phase 4: Eval integration. `scores_from_answer_probabilities` fast path in `build_g_eval_score`, tests for legacy `GEval` and V2 `LlmJudgeEval` with a Jev judge (g_eval on and off).
- [ ] Phase 5: Web UI and docs. Provider card, status wiring, `provider_name_map`, provider image (placeholder glyph with a `TODO` for the official mark), regenerated `api_schema.d.ts`, one connect-providers test, `.agents/scripts/provider_utils.py`, the three synced skill-doc copies. Run the `kiln-ui` skill before touching `.svelte` files. Full `checks.sh`.
- [ ] Phase 6 (separate PR, after release): `ml_model_list.py` entry for `ModelFamily.jev` / `ModelName.jev_1_13` on `typesafe`, confirmed against `GET /v1/models`; prerelease whitelist and a `--runpaid` smoke test (one structured task, one V2 judge) skipped without `TYPESAFE_API_KEY`.
