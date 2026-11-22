---
status: complete
---

# Functional Spec: OpenCode Provider

## Overview

Add OpenCode as a standard Kiln model provider. OpenCode Console is a pay-as-you-go AI gateway. One API key gives access to models from many labs (Anthropic, OpenAI, Google, xAI, DeepSeek, Moonshot, Zhipu, MiniMax, Alibaba, Mistral, Meta), billed at the labs' prices from prepaid credits.

Users connect with an OpenCode Console API key. Kiln then offers OpenCode as another provider on the Kiln models that OpenCode serves, through the same connect screen and model picker that every provider uses. There's no new UX.

Sources:

- [Console models](https://opencode.ai/docs/console/models): the model catalog, endpoints, pricing, free models, deprecations and privacy.
- [Harnesses: base URLs](https://opencode.ai/docs/console/harnesses#base-urls): base URLs per plan, API paths, API keys and the session header.
- Live checks made while writing this spec (Nov 22, 2026): `GET https://opencode.ai/inference/v1/models` returned 200, and a chat-completions call to `claude-haiku-5-5` succeeded and reported its cost in `usage.cost`.

## Scope

### In scope

- One new provider, shown to users as **OpenCode**.
- A connect flow with one field, the API key, validated on connect.
- Running OpenCode's paid chat models through its OpenAI-compatible Chat Completions endpoint, using Kiln's existing OpenAI-compatible LiteLLM path, the same way Kiln calls other OpenAI-compatible hosts.
- Recording the cost OpenCode reports for each call.
- OpenCode provider entries on the existing Kiln models that OpenCode serves (paid chat models only). See [Model Catalog](#model-catalog).
- Updates to the model-maintenance and deprecation-check skills so the OpenCode entries stay current.

### Out of scope

- **The Go subscription plan.** It uses a separate base URL (`https://opencode.ai/inference/go`) and requires the session header. The provider ID and name are plain "OpenCode", so Go can be added later as a connect-time option without renaming anything.
- **Free models.** These include `big-pickle`, the `*-free` models and `jev-1.13-free`. OpenCode returns HTTP 403 for them to any client other than OpenCode itself, even with a valid key.
- **OpenCode's other APIs.** These are Responses, Anthropic Messages and Gemini. OpenCode translates every paid text model to Chat Completions, so Kiln uses Chat Completions only.
- **Embedding models** for RAG. That's a possible follow-up project.
- **System One models** (Jev, GPT 6 Luna Decision, Gemini Decision 1). Kiln already serves Jev through the TypeSafe provider.
- **Image, video and realtime models.**
- **New `KilnModel` entries** for OpenCode models that Kiln doesn't have yet. Those go through the normal model-sweep process later.
- **The `x-opencode-session` header.** Session affinity for multi-turn runs is a cross-provider problem, handled separately for all providers.
- **Kiln-side awareness of the user's balance, budgets, auto-recharge or workspace settings.** Users manage these in OpenCode Console.

## Provider Identity

| Item | Value |
|---|---|
| Internal provider ID | `opencode` (a new `ModelProviderName` member) |
| Display name | "OpenCode" |
| `models_dev_id` | `opencode` (exists on models.dev; `opencode-go` is the separate Go plan entry) |
| Model IDs | OpenCode's own model IDs, sent unchanged, e.g. `claude-sonnet-5-5`, `gpt-5.4-mini`, `kimi-k3` |

## Credentials and Configuration

| Field | Required | Stored as | Env var | Notes |
|---|---|---|---|---|
| API key | Yes | Kiln config, secret | `OPENCODE_API_KEY` | Format `oc_sk_...`. The env var name matches models.dev and OpenCode's docs. |

Users can use either a personal API key (Account → Personal API keys → Add API key) or a service-account key that a workspace owner or admin creates. Usage is billed to the workspace the key belongs to. That workspace needs credits.

The connect screen's help text explains how to create a key and that the workspace needs credits. See [Connect Screen Copy](#connect-screen-copy).

## Connect Flow

1. On the connect-provider screen, the user opens OpenCode and pastes an API key.
2. Kiln validates the key before saving it.
   - An invalid or revoked key must fail the connect with "Invalid OpenCode API key", and the message must say a pay-as-you-go Console key is needed. Kiln must never save a key that it knows fails.
   - A valid key on a workspace with no credits still connects. Calls then fail at run time with a clear message (see [Errors](#errors)). Credits are a billing state that changes over time, so they shouldn't block connecting.
   - A network failure (OpenCode unreachable, timeout) fails the connect with a message saying Kiln couldn't reach OpenCode. It doesn't claim the key is invalid.
   - The architecture step picks the validation call. The first choice is a free authenticated call, such as `GET /inference/v1/models` if that endpoint rejects bad keys. If no free call distinguishes good keys from bad ones, the fallback is a 1-token chat completion on the cheapest paid model, which costs a fraction of a cent.
3. On success, Kiln saves the key and shows OpenCode as connected, like other providers.
4. Disconnect clears the key.

## Calling Models

- **Endpoint:** `https://opencode.ai/inference/openai/v1/chat/completions`. The base URL for the OpenAI-compatible client is `https://opencode.ai/inference/openai/v1`.
- **Auth:** `Authorization: Bearer <key>`.
- **Path:** Kiln's existing OpenAI-compatible LiteLLM flow, with a fixed base URL and the stored key. It's wired the way other OpenAI-compatible hosts are, with no OpenCode-specific adapter.
- **Translation:** for models whose native API isn't Chat Completions (Claude, GPT, Gemini, Grok, Muse, some Qwen), OpenCode translates the request. Kiln treats this as a black box. Each model's capability flags come from the per-model paid tests run through this path, not from the model's flags on its native provider (see [Model Catalog](#model-catalog)).

## Cost

OpenCode reports the cost of each call in USD, in the response's `usage.cost` field. The billed amount is also in `usage.opencode.list_cost`, and the billing source in `usage.opencode.billing_source`.

- For OpenCode calls, Kiln records `usage.cost` as the run's cost, in place of LiteLLM's computed `response_cost`. OpenCode's prices include discounts and per-context-length tiers that LiteLLM's price list doesn't know about.
- If a response has no `usage.cost`, Kiln records no cost. It doesn't fall back to LiteLLM's estimate, because a wrong number is worse than none.
- Streaming responses: the architecture step confirms that the final usage chunk carries `usage.cost`, and how to read it there.

## Errors

OpenCode's own error messages are clear, and LiteLLM keeps them intact (see the probe in [architecture.md](./architecture.md#error-probe)). Kiln adds no OpenCode-specific error handling. It relies on its existing handling, plus one generic rule for HTTP 402 that applies to every provider.

| Case | OpenCode returns | Kiln behavior |
|---|---|---|
| Invalid, revoked or expired key | 401 (confirmed by the user with a bad key) | The existing authentication error: "Check your API key." It's batch-fatal. |
| Out of pay-as-you-go credits | 402 `Insufficient account funds` (per OpenCode's billing docs) | New generic 402 rule: "The model provider declined the request because the account is out of credits. Add credits with the provider and try again." It's batch-fatal and not retried. |
| Rate limit | 429 | The existing `RateLimitError`: retryable and not batch-fatal. |
| Model disabled for the workspace, retired, or unknown | 403, 410 or 400 | The existing generic error. Kiln lists only default-enabled, current models, so these occur only with custom model IDs or after an admin change. |
| Free model (custom model ID only) | 429 `FreeUsageLimitError` | Treated as a rate limit by the existing handling. Kiln never lists free models. |

**Provider text is kept.** For every row above, OpenCode's own message must reach Kiln unchanged in the exception Kiln keeps:
- Non-streaming runs: `KilnRunError.original`.
- Streaming runs: the exception that's raised, which isn't wrapped in a `KilnRunError`.

The status code must be kept too. Kiln doesn't show this text to the user in this project; showing it in the run page and elsewhere is a separate project. This project only guarantees that the text is there, and tests that it is.

The pay-as-you-go versus OpenCode Go distinction is made on the connect screen (the warning and the key steps), in the connect error for a rejected key, and in the missing-key warning. A generic provider rule can't name OpenCode Go, so the 402 message doesn't.

## Model Catalog

Option A: add an `opencode` provider entry to every existing `KilnModel` that OpenCode serves as a paid chat model.

**Inclusion rule.** A model is included only if all of these hold:

- OpenCode lists it with `type: chat`.
- It has a non-zero price. Free models are excluded.
- **It's enabled by default in a new OpenCode workspace.** Models an admin has to turn on aren't listed. Users who turn them on can add them as Kiln custom models, which keeps the default list working for everyone.
- It isn't on OpenCode's deprecated-models table.
- Kiln already has a `KilnModel` for it. A match uses the model's identity, which is OpenCode's `canonical_id` (e.g. `anthropic/claude-sonnet-5-5`), not just its display name.

**Flags.** Each provider entry sets its own structured-output mode, tool calling, reasoning, thinking levels, vision and supported file types. Start from the same model's entry on its native provider, then let the paid tests through OpenCode's Chat Completions path decide. Translation may support less than the native API does (for example PDF input), and the entry must reflect what works through OpenCode.

**Which models are enabled by default:** this comes from `GET /inference/v1/models` with a key from a workspace whose model settings are untouched. That endpoint lists only the models the workspace allows, and calling any other model returns 403.

## Model List Maintenance

Add an OpenCode section to `.agents/skills/claude-maintain-models/SKILL.md` and to the deprecation-check skill:

- **Sources:** `GET /inference/v1/models` from a default-settings workspace, for the models enabled by default. Cross-check with models.dev under key `opencode`, and with OpenCode's deprecated-models table on the docs page.
- **Inclusion rule:** as in [Model Catalog](#model-catalog), including the default-enabled check. The skill text must say how to spot free, decision, image, embedding, video and realtime models in the source (the `type` field, a zero price, the `-free` suffix).
- **Deprecations:** flag any Kiln OpenCode entry whose model appears on OpenCode's deprecated-models table, and remove or deprecate it before the listed date.
- **Lagging check:** add OpenCode to the skill's check for providers that lag behind, so it adds OpenCode entries to recently added Kiln models once OpenCode starts serving them.

## Release Sequencing

Follow the model-maintenance skill's rule for new providers:

- **PR 1, provider support:** the `ModelProviderName` member, the config field, the LiteLLM wiring, cost recording, the generic 402 rule, connect and disconnect, the `built_in_providers` item, and the web UI connect entry and icon. It can merge whenever it's ready.
- **PR 2, model catalog and skill docs:** the `ml_model_list.py` provider entries and the skill updates. It merges only after a client release that includes PR 1.

## Connect Screen Copy

Approved strings. There's no separate UI design step for this project.

- **Card description:** "Pay-as-you-go access to models from Anthropic, OpenAI, Google and more, billed to your OpenCode credits."
- **Warning, shown above the key field:** "Uses OpenCode's pay-as-you-go credits. OpenCode Go subscriptions aren't supported."
- **Key steps:**
  1. "Sign in to OpenCode Console at https://opencode.ai/console and add pay-as-you-go credits to your workspace."
  2. "Open Account, then Personal API keys, and click Add API key."
  3. "Copy the key and paste it below."

## Testing

- **Unit tests:** the config field, connect validation (valid key, invalid key, network failure), the LiteLLM wiring (base URL, key, model ID passthrough), cost recording (with and without `usage.cost`, streaming and non-streaming), and the 402 rule.
- **Per-model paid tests:** these run automatically for each OpenCode entry in `ml_model_list.py`, as for other providers. They set the final flags.
- **Live tests:** use `OPENCODE_API_KEY`. In this cloud environment, the key is saved as a network secret for `opencode.ai`, so tests set the env var to a placeholder and the proxy injects the real key.

### Dev network allowlist

| Host | Why |
|---|---|
| `opencode.ai` | Inference, the models list, connect validation and the docs. It's allowed through the saved network secret. |
| `models.dev` | Cross-check source for the maintenance skill. It's already allowed. |
