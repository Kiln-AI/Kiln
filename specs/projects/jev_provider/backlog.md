# Backlog: Jev Provider (TypeSafe AI System One)

Items found while implementing, outside the phase that found them. Phase 7 reviews these
with the user and closes or dismisses each one.

## Open

None. Phase 7 reviewed every item with the user.

## Closed

- **`adapter_for_task` resolves the model provider twice per run.** `adapter_for_task`
  resolves the provider to read `.adapter`, then discards it, so
  `BaseAdapter.model_provider()` resolves it again on first use. Two effects: one extra
  provider lookup per run, and a duplicated `logger.warning("Unexpected model/provider
  pair...")` from `kiln_model_provider_from`.

  **Dismissed in Phase 7.** Neither effect earns a change. The lookup is in memory, not on
  disk: `get_all_user_models()` reads the `Config.shared()` singleton and builds a
  `UserModelEntry` per row, and the built-in path scans a list of a few hundred models, so
  a second call is unmeasurable beside the network call that follows it. The duplicated
  warning is narrower than this entry first claimed: it is not every custom-model run, but
  only a run whose model and provider pair matches no built-in model and is not
  `kiln_custom_registry`, because a user-registry model returns earlier from
  `find_user_model`. The only fix that removes the second resolution is to thread the
  resolved `KilnModelProvider` into the adapter, which means changing `BaseAdapter`, the
  base class of every adapter in the repo. That is too much surface for a duplicated
  advisory line on an edge-case path.

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
  every custom model, so this is accepted behaviour rather than a Jev defect.

  **Dismissed in Phase 7.** The model dropdown's `requires_logprobs` filter keeps a Jev
  judge out of G-Eval on the default UI path, so the exposure is the API path, a
  pre-existing eval config, or a user who overrides `supports_logprobs`. Making the guard
  fire without a built-in entry changes behaviour for every custom model, which belongs in
  its own project rather than in a provider pull request.


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
