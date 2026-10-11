# Coverage in models.dev and the LiteLLM Catalog

Kiln's `claude-maintain-models` skill discovers models by querying the LiteLLM catalog (`https://api.litellm.ai/model_catalog`) and models.dev (`https://models.dev/api.json`). This page checks how each covers Cloudflare Workers AI as of 2026-09-28.

## Summary

| | models.dev | LiteLLM catalog / cost map |
|---|---|---|
| Provider key | `cloudflare-workers-ai` (separate `cloudflare-ai-gateway` key for proxied third-party models) | `cloudflare` (IDs look like `cloudflare/@cf/...`) |
| Model count (chat) | 27 | 30 |
| Includes the newest models (GLM-5.3, GLM-5.3 Flash, Qwen 3.8 27B, DeepSeek V4 Pro/Flash) | **Yes** | **No** |
| Includes retired models | No (removed 2026-05-31) — but see "deleteMissing" below | **Yes**: 4 retired entries (`llama-2-7b-chat-fp16`, `llama-2-7b-chat-int8`, `mistral-7b-instruct-v0.1`, `@hf/thebloke/codellama-7b-instruct-awq`) |
| How it is maintained | Automated hourly sync from Cloudflare's `/ai/models/search?format=openrouter`, plus hand fixes | One manual bulk import (2026-06-23), no updates since |
| Capability data | Tool call, structured output, reasoning options, input modalities, context/output limits, pricing | `supports_function_calling`, `supports_reasoning`, context, pricing; vision set only on Llama 3.2 11B; `supports_response_schema` null everywhere; `deprecation_date` null everywhere |
| Verdict | **Current and usable as the primary third-party source** | **Stale; useful mainly to confirm LiteLLM's `cloudflare/` prefix and pricing for older models** |

## models.dev

- Provider definition ([`providers/cloudflare-workers-ai/provider.toml`](https://github.com/sst/models.dev/blob/dev/providers/cloudflare-workers-ai/provider.toml)):
  ```toml
  name = "Cloudflare Workers AI"
  env = ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_KEY"]
  npm = "@ai-sdk/openai-compatible"
  doc = "https://developers.cloudflare.com/workers-ai/models/"
  api = "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/ai/v1"
  ```
- Model IDs are the bare Cloudflare IDs (`@cf/zai-org/glm-5.3`), stored as `providers/cloudflare-workers-ai/models/@cf/<author>/<model>.toml`.
- The live site agrees: [models.dev/providers/cloudflare-workers-ai](https://models.dev/providers/cloudflare-workers-ai/) showed "Models: 27" on 2026-09-28, with GLM-5.3, GLM-5.3-Flash, Qwen3.8 27B, DeepSeek V4 Flash 0731, DeepSeek V4 Pro 0813.
- The 27 = all 31 Cloudflare text-generation models minus the four `-lora` bases. Non-text models (embeddings, image, speech) are not included.
- **Automated sync.** [`packages/core/src/sync/providers/cloudflare-workers-ai.ts`](https://github.com/sst/models.dev/blob/dev/packages/core/src/sync/providers/cloudflare-workers-ai.ts) calls `GET https://api.cloudflare.com/client/v4/accounts/{id}/ai/models/search?format=openrouter&per_page=1000` with a Cloudflare token stored as GitHub secrets (`CLOUDFLARE_WORKERS_AI_SYNC_ACCOUNT_ID` / `_API_TOKEN`). The workflow runs hourly (`cron: "17 * * * *"` in [`.github/workflows/sync-models.yml`](https://github.com/sst/models.dev/blob/dev/.github/workflows/sync-models.yml)). Recent commit log for the provider shows `chore(sync): update Cloudflare Workers AI model catalog` on 2026-08-14, 08-17, 08-26, 08-28, 09-09, 09-12, 09-21, 09-22.
- **Lag:** new models appear within about a day of Cloudflare's launch. `deepseek-v4-pro-0813.toml` was added 2026-08-14 (changelog 2026-08-14); `qwen3.8-27b.toml` 2026-08-17 (changelog 2026-08-17); `glm-5.3-flash.toml` 2026-08-26 (changelog 2026-08-26); `glm-5.3.toml` 2026-08-28 (changelog 2026-08-28).
- **Deletion behaviour changed.** Retired models were deleted on 2026-05-31, the day after the 2026-05-30 retirement (commit `7de9710b`: removed `gemma-3-12b-it`, `llama-2-7b-chat-fp16`, `llama-3-8b-instruct(-awq)`, `llama-3.1-8b-instruct-awq`, `mistral-7b-instruct-v0.1`, `kimi-k2.5`). But since 2026-09-21 the sync has `deleteMissing: false` (commit `f02d6806`, "fix(sync): safely refresh Workers AI reasoning from search"), so **future retirements may not be removed from models.dev automatically**. models.dev is therefore a good *addition* signal and a weak *removal* signal.
- **Flapping observed.** `glm-5.3.toml` was deleted and re-added twice on 2026-09-09 (sync commits `016db508`, `35a2ed97`, then fix commit `9faf0c52` "[missing-model] cloudflare-workers-ai: @cf/zai-org/glm-5.3"). *Inference:* the search API response is not always complete, which may be why deletions were turned off.
- Much per-model data is inherited through `base_model` (for example `base_model = "zhipuai/glm-5.3"`), so the raw TOML is sparse. Read the resolved values from `api.json` (`.["cloudflare-workers-ai"].models["@cf/..."]`) rather than the TOML.
- Some models carry hand-written comments explaining Cloudflare's reasoning controls, for example on Kimi K2.6: "Effort: reasoning_effort = none|high; none selects instant mode. Source: Workers AI /ai/models/search?format=openrouter (2026-09-18)."

## LiteLLM

- Provider name `cloudflare`. The LiteLLM catalog returned 30 chat entries on 2026-09-28 (`https://api.litellm.ai/model_catalog?provider=cloudflare&mode=chat&page_size=500`, fetched via Tavily). Same 30 as the `litellm_provider == "cloudflare"` chat entries in [`model_prices_and_context_window.json`](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json) on `main` (plus two `audio_transcription` Whisper entries).
- **One-off import.** LiteLLM commit `2688f81df` (2026-06-23, PR #31051) says: "The Cloudflare Workers AI list in the model cost map was badly stale, holding only 4 ancient entries (llama-2-7b, mistral-7b-v0.1, codellama). This adds the 26 current text-generation models from Cloudflare's live /ai/models/search?task=Text Generation catalog…". Nothing was added after that. Missing on 2026-09-28: `glm-5.3`, `glm-5.3-flash`, `qwen3.8-27b`, `deepseek-v4-pro-0813`, `deepseek-v4-flash-0731`.
- The four "ancient" entries were not removed, and they are all retired on Cloudflare now.
- Capability gaps: `supports_vision` is set only on `llama-3.2-11b-vision-instruct` (not on Kimi K2.6, Gemma 4, Llama 4 Scout); `supports_response_schema` is null for every entry; `deprecation_date` is null for every entry. LiteLLM also sets `max_output_tokens` equal to the context window for every Cloudflare model, which is not real data.
- Later LiteLLM commit `cb8daee55` (2026-09-08) added `rpm` limits (20 rpm for Kimi K2.6/K2.7 Code and GLM-5.2, 300 for others).
- Separately, LiteLLM commit `1be957da1` (2026-06-23) "route native Workers AI provider through OpenAI-compatible endpoint" — relevant to the API subtopic, not researched here.
- **Why this matters for Kiln:** the skill's rule "Every `model_id` must come from an authoritative source (LiteLLM catalog, official docs, …)" will usually fail on LiteLLM for new Cloudflare models. The official Cloudflare list must be the primary source. LiteLLM's missing cost entries also mean Kiln will likely record `cost: null` for new Cloudflare models unless the LiteLLM path returns cost some other way (the Featherless precedent in the skill).

## Coverage gaps in both

- Neither says whether a model needs Workers Paid (`require_workers_paid`) — only Cloudflare's own data has it.
- Neither tracks Cloudflare's `planned_deprecation_date`.
- Neither lists LoRA base models' `lora` requirement.
