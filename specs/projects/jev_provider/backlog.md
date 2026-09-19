# Backlog: Jev Provider (TypeSafe AI System One)

Items found while implementing, outside the phase that found them. Phase 7 reviews these
with the user and closes or dismisses each one.

## Open

- **This branch makes `adapter_for_task` resolve the model provider twice per run.** Not a
  latent cleanup: it is a behaviour regression this branch introduces to a shared hot path,
  and it hits **every custom-model run, not only Jev**. `adapter_for_task` resolves the
  provider eagerly to read `.adapter`, then discards it, so `BaseAdapter.model_provider()`
  resolves it a second time on first use. Consequences: `get_all_user_models()` re-parses the
  user model registry twice per run, and the `logger.warning("Unexpected model/provider
  pair...")` in `kiln_model_provider_from` now fires twice per run where it fired once before,
  which reads as a real duplicate to anyone debugging from logs. The fix is to thread the
  already-resolved `KilnModelProvider` into the adapter to prime `BaseAdapter._model_provider`.
  Deferred from Phase 3 review because that threading touches `BaseAdapter`, which every
  adapter depends on — not a change worth making mid-phase for log noise, but it should get a
  deliberate look. **Disclose in the PR description** so nobody debugging from logs chases a
  phantom duplicate.

- **The `g_eval` / `supports_logprobs` guard only fires for models with a built-in entry.**
  The V2 LLM Judge's guard in `v2_eval_llm_judge.py` raises only when
  `built_in_models_from_provider(...)` returns non-`None`, so a `g_eval=True` judge on a
  model with no built-in entry slips past it and fails late with
  `RuntimeError("No logprobs found for output - can not calculate g-eval")`. This matters
  for Jev specifically between Phase 6, which removes the model entry, and Phase 8, which
  re-adds it: in that window a user-registry Jev model is the only way to use the
  provider, and it is exactly the case the guard misses. Related and also pre-existing:
  legacy `EvalConfigType.g_eval` has no `supports_logprobs` guard at all, so a legacy
  g_eval config naming Jev fails the same late way. Both are the guard shape shared with
  every custom model, so this is a deliberate deferral, not an oversight.

## Closed

- **Confirm `GET https://api.typesafe.ai/v1/models` rejects a bad key.** This is the
  precondition `architecture.md` sets for `connect_typesafe`. It could not be verified
  during Phase 1 because sandbox egress to `api.typesafe.ai` is proxy-blocked, so the
  phase took the GET branch on indirect evidence from the official SDK only. If the
  endpoint turns out to be public — as Featherless's `/v1/models` is, which is why
  `connect_featherless` uses a minimal POST — then `connect_typesafe` will store any
  arbitrary string as a valid key and report "Connected to TypeSafe AI", and the user
  will discover the bad key only on their first run. In that case the plan was to switch
  to the spec's minimal `POST /v1/systemone` fallback.

  **Resolved:** the user confirmed against the live endpoint that `GET /v1/models`
  rejects an invalid API key, so `connect_typesafe` keeps the GET check and the
  `POST /v1/systemone` fallback is not needed.

- **The TypeSafe AI connect dialog links to the marketing root, not an API key page.**
  Step 1 says "Go to https://typesafe.ai", where every sibling provider deep-links to the
  page that actually creates a key (Featherless `https://featherless.ai/account/api-keys`,
  Cerebras `https://cloud.cerebras.ai/platform`, SiliconFlow
  `https://cloud.siliconflow.cn/account/ak`, Together
  `https://api.together.ai/settings/api-keys`). The user lands on a homepage and has to
  hunt, which is the friction the three-step recipe exists to remove. No console URL was
  substituted at the time because none was verified: `research/jev_api/summary.md` records only
  `api.typesafe.ai` endpoints and notes `docs.typesafe.ai` was unreachable during
  research. The same root URL was also used in the backend warning in `provider_tools.py`.

  **Resolved:** the user supplied the console keys URL `https://console.typesafe.ai/keys`,
  now used in both the connect dialog step and the `provider_warnings` message.
