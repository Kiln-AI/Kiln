# Backlog: Jev Provider (TypeSafe AI System One)

Items found while implementing, outside the phase that found them. Phase 9 reviews these
with the user and closes or dismisses each one.

## Open

- **Confirm `GET https://api.typesafe.ai/v1/models` rejects a bad key.** This is the
  precondition `architecture.md` sets for `connect_typesafe`. It could not be verified
  during Phase 1 because sandbox egress to `api.typesafe.ai` is proxy-blocked, so the
  phase took the GET branch on indirect evidence from the official SDK only. If the
  endpoint turns out to be public — as Featherless's `/v1/models` is, which is why
  `connect_featherless` uses a minimal POST — then `connect_typesafe` will store any
  arbitrary string as a valid key and report "Connected to TypeSafe AI", and the user
  will discover the bad key only on their first run. In that case, switch to the spec's
  minimal `POST /v1/systemone` fallback. Needs a human with a live key; must not reach
  merge unresolved.

- **`adapter_for_task` resolves the model provider twice per run.** It resolves the provider
  eagerly to read `.adapter`, then discards it, so `BaseAdapter.model_provider()` resolves it
  a second time on first use. Consequences: `get_all_user_models()` re-parses the user model
  registry twice per run, and the `logger.warning("Unexpected model/provider pair...")` in
  `kiln_model_provider_from` now fires twice for every custom-model run, which reads as a real
  duplicate to anyone debugging from logs. The fix is to thread the already-resolved
  `KilnModelProvider` into the adapter to prime `BaseAdapter._model_provider`. Deferred from
  Phase 3 review because it touches `BaseAdapter`, which every adapter depends on — not a
  change worth making mid-phase for log noise, but it should get a deliberate look.

- **The `g_eval` / `supports_logprobs` guard only fires for models with a built-in entry.**
  The V2 LLM Judge's guard in `v2_eval_llm_judge.py` raises only when
  `built_in_models_from_provider(...)` returns non-`None`, so a `g_eval=True` judge on a
  model with no built-in entry slips past it and fails late with
  `RuntimeError("No logprobs found for output - can not calculate g-eval")`. This matters
  for Jev specifically between Phase 6, which removes the model entry, and Phase 7, which
  re-adds it: in that window a user-registry Jev model is the only way to use the
  provider, and it is exactly the case the guard misses. Related and also pre-existing:
  legacy `EvalConfigType.g_eval` has no `supports_logprobs` guard at all, so a legacy
  g_eval config naming Jev fails the same late way. Both are the guard shape shared with
  every custom model, so this is a deliberate deferral, not an oversight.
