# Model Catalog and Discovery (Cloudflare Workers AI)

## Bottom Line

Workers AI has **one global, Cloudflare-curated list** of hosted models with IDs like `@cf/<author>/<model>`. It is not a list of "models your account can access". Accounts do differ, but only in whether a call succeeds, not in which IDs exist:
- Some big models need the Workers Paid plan (error `5035`).
- Llama 3.2 Vision needs a one-time license "agree" call.
- LoRA fine-tunes are a request parameter on a base model, not new IDs.

So Kiln can maintain its Cloudflare entries statically, the same way it does for OpenRouter and Together.

**Machine-readable lists exist.** There's an official `GET /accounts/{id}/ai/models/search` that needs a token. It supports a task filter, `include_deprecated`, and an OpenRouter-format option. There's also a public JSON at `https://ai-cloudflare-com.pages.dev/api/models` that needs no login and is what Cloudflare's own docs build uses.

**models.dev covers it well.** Its provider key is `cloudflare-workers-ai`. It syncs hourly and is current to within a day.

**LiteLLM is stale.** Its provider key is `cloudflare`. The entries came from a one-time import on 2026-06-23, the five newest models are missing, and four retired models are still listed.

Cloudflare retires models in batches with 2–3 weeks' notice. Once, it quietly pointed a retired ID at a more expensive model. Kiln's maintenance skill should check Cloudflare's own list directly.

## Key Findings

- **Two catalogs; only one matters here.** "Hosted" `@cf/...` models are Workers AI: 65 in total, 31 of them text generation. The "proxied" third-party models (`openai/...`, `anthropic/...`, 164 in total) come from a separate, undocumented `/ai/catalog/models` API. They belong to AI Gateway unified billing. [model-resolver.ts](https://github.com/cloudflare/cloudflare-docs/blob/production/src/util/models/model-resolver.ts)
- **The search API needs a token** with Workers AI Read or Write. Its parameters are `task`, `author`, `source`, `search`, `hide_experimental`, `include_deprecated`, `format=openrouter`, plus paging. `include_deprecated` is described as "include models for up to three months after their deprecation date". The OpenAPI spec leaves the item schema untyped. [cloudflare/api-schemas](https://github.com/cloudflare/api-schemas)
- **The public JSON needs no login but is undocumented.** It returns `{models:[...]}`, and each model has `name`, `task.name`, `created_at` and `properties[]`.
  - Properties that matter for Kiln: `context_window`, `function_calling`, `vision`, `reasoning`, `reasoning_effort` (supported levels, default, whether mandatory), `price`, `require_workers_paid`, `lora`, `beta`.
  - When a retirement is scheduled, a `planned_deprecation_date` property appears.
  - There is **no JSON-mode flag and no max-output field**.
  - [fetch-ai-models.js](https://github.com/cloudflare/cloudflare-docs/blob/production/bin/fetch-ai-models.js)
- **The same data is in GitHub**, one file per model, at `cloudflare/cloudflare-docs/src/content/workers-ai-models/*.json`. It's synced from the endpoint and sometimes corrected by hand. New models show up the day they launch.
- **Notable text models on 2026-09-28:** GLM-5.3 and GLM-5.3 Flash, GLM-5.2, GLM-4.7-Flash, DeepSeek V4 Pro (`-0813`) and Flash (`-0731`), Kimi K2.6, Kimi K2.7 Code, Qwen 3.8 27B, Qwen3 30B A3B fp8, gpt-oss-120b and 20b, Gemma 4 26B A4B, Nemotron 3 Super, Llama 4 Scout, Llama 3.3 70B fp8-fast (24K context), Mistral Small 3.1, QwQ 32B.
  - 18 models support function calling.
  - 7 text models support vision.
  - 7 models need Workers Paid.
  - See [text-generation-models.md](./text-generation-models.md).
- **IDs:** the last four `@hf/` models were retired on 2026-05-30, so every current ID starts with `@cf/`. IDs include quantization suffixes (like `-fp8`) and date suffixes (like `-0813`), so they can't be guessed.
- **JSON mode:** it's documented, but the docs' list of supported models is stale; 4 of its 6 models are retired. The docs also say it isn't guaranteed and doesn't work with streaming. Each model needs a paid test. [json-mode.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/features/json-mode.mdx)
- **models.dev:**
  - It has 27 models, which is every text-generation model except the four LoRA base models.
  - It sets `env = ["CLOUDFLARE_ACCOUNT_ID","CLOUDFLARE_API_KEY"]` and `npm = "@ai-sdk/openai-compatible"`.
  - It syncs hourly from `/ai/models/search?format=openrouter`.
  - Since 2026-09-21 its sync no longer deletes models that disappear from Cloudflare's list, so it's a weak signal for retirements.
  - [sync code](https://github.com/sst/models.dev/blob/dev/packages/core/src/sync/providers/cloudflare-workers-ai.ts)
- **LiteLLM:**
  - It has 30 `cloudflare/@cf/...` chat entries from a single import on 2026-06-23.
  - Missing: GLM-5.3, GLM-5.3 Flash, Qwen 3.8 27B, DeepSeek V4 Pro and DeepSeek V4 Flash.
  - It still lists 4 retired models.
  - Vision is flagged only on Llama 3.2 11B, and `deprecation_date` is null on every entry.
  - Kiln will likely record no cost for the newer models.
  - [LiteLLM commit 2688f81df](https://github.com/BerriAI/litellm/commit/2688f81df)
- **Retirements:**

  | Announced | Retired | Models |
  |---|---|---|
  | 2024-06-11 | 2024-06-30 | 1 |
  | 2025-09-18 | 2025-10-01 | 19 |
  | 2026-05-08 | 2026-05-30 | 18 |

  Each batch is announced in the changelog, and the affected models get a `planned_deprecation_date` property. A retired ID usually returns error `5007` ("No such model"). One ID was instead aliased: Kimi K2.5 now runs K2.6, which costs more. [2026-05-08 changelog](https://developers.cloudflare.com/changelog/post/2026-05-08-planned-model-deprecations/)
- **Recommended procedure:**
  - Treat Cloudflare's public JSON, or the search API when a token is set, as the source of truth for model IDs and capability flags.
  - Use models.dev as a cross-check, and don't rely on LiteLLM for Cloudflare.
  - Add Cloudflare to the skill's "Lagging Providers" section, and to `provider_utils.py` so deprecation checks cover it.
  - Alert when a model gains `planned_deprecation_date`.
  - Draft skill text and tested jq snippets are in [recommended-maintenance-procedure.md](./recommended-maintenance-procedure.md).

## Details

- [catalog-concept-and-sources.md](./catalog-concept-and-sources.md) covers the two catalogs, the evidence that the list is global, and every machine-readable source with its fields. Read it to choose a data source or write a fetcher.
- [text-generation-models.md](./text-generation-models.md) covers the ID format, a table of all 31 text-generation models with capabilities and prices, JSON mode, vision and reasoning, the conflicts between sources, and how the models map to existing Kiln `ModelName`s. Read it when writing the first entries.
- [third-party-catalogs.md](./third-party-catalogs.md) covers how complete and current models.dev and LiteLLM are, and how each one's sync or import works.
- [lifecycle-and-deprecation.md](./lifecycle-and-deprecation.md) covers retirement history, what retirement looks like in the data and the API, the aliasing risk, plan-gating changes, and where to watch for changes.
- [recommended-maintenance-procedure.md](./recommended-maintenance-procedure.md) covers the step-by-step procedure, how Cloudflare's properties map to Kiln flags, the deprecation tooling changes, and the proposed skill text.

## Open Questions / Gaps

- **No direct or authenticated API calls.** The egress proxy blocked `api.cloudflare.com`, `developers.cloudflare.com`, `models.dev` and `api.litellm.ai`, and there were no Cloudflare credentials. The public JSON and the LiteLLM catalog were read through Tavily; everything else came from GitHub. These points are inferred from specs and code, not seen in a live response:
  - the exact item shape from `/ai/models/search`
  - the field names in its `format=openrouter` mode
  - whether accounts ever see private models in it
- What a retired ID returns wasn't verified. Error `5007` comes from the errors page.
- Three conflicts between sources are unresolved:
  - Mistral Small 3.1: the changelog says it has vision, but the model data has no vision flag.
  - DeepSeek V4 Flash context window: Cloudflare says 1,048,576, models.dev says 1,310,720.
  - `@cf/meta/llama-3.1-8b-instruct-fast`: the May 2026 changelog says it stays active, but it isn't in any list.
- Not checked: whether every model works on the OpenAI-compatible `/v1/chat/completions` endpoint. The Qwen 3.8 launch post mentions only `/ai/run`.
- The changelog RSS URL wasn't fetched. The path `/changelog/rss/workers-ai.xml` is inferred from a route file in the docs repo.

## Sources

- [cloudflare-docs `workers-ai-models/`](https://github.com/cloudflare/cloudflare-docs/tree/production/src/content/workers-ai-models): the per-model catalog data (commit c1530017, 2026-09-28).
- [`bin/fetch-ai-models.js`](https://github.com/cloudflare/cloudflare-docs/blob/production/bin/fetch-ai-models.js) and [`bin/fetch-catalog-models.ts`](https://github.com/cloudflare/cloudflare-docs/blob/production/bin/fetch-catalog-models.ts): how the docs get their model data and filter out deprecations.
- [`model-resolver.ts`](https://github.com/cloudflare/cloudflare-docs/blob/production/src/util/models/model-resolver.ts): the split between hosted and proxied models.
- `https://ai-cloudflare-com.pages.dev/api/models`: the public catalog JSON, read through Tavily on 2026-09-28 (65 models).
- [cloudflare/api-schemas `openapi.json`](https://github.com/cloudflare/api-schemas): the search, schema and fine-tune API definitions (commit e934edf0, 2026-09-28).
- [cloudflare-python `models.py`](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/ai/models/models.py): the SDK's list parameters.
- [Workers AI changelog](https://developers.cloudflare.com/changelog/product/workers-ai/): the posts dated 2026-05-08, 07-28, 08-14, 08-17 and 08-28, read from the docs repo.
- [`release-notes/workers-ai.yaml`](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/release-notes/workers-ai.yaml): the October 2025 deprecation batch.
- [errors.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/platform/errors.mdx): error codes 5007, 5016, 5035 and 3040.
- [json-mode.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/features/json-mode.mdx), [loras.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/features/fine-tunes/loras.mdx) and [public-loras.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/features/fine-tunes/public-loras.mdx).
- [models.dev provider folder](https://github.com/sst/models.dev/tree/dev/providers/cloudflare-workers-ai), its [sync code](https://github.com/sst/models.dev/blob/dev/packages/core/src/sync/providers/cloudflare-workers-ai.ts) and the [live provider page](https://models.dev/providers/cloudflare-workers-ai/) (commit 552ba9d9, 2026-09-28).
- [LiteLLM price map](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json) and the LiteLLM catalog API with `provider=cloudflare` (main branch, 2026-09-28).
- [OpenRouter provider listing spec](https://openrouter.ai/docs/guides/get-started/for-providers): the format that `format=openrouter` follows.
