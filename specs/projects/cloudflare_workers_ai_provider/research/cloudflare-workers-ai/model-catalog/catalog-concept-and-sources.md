# Workers AI Catalog: What It Is and Where to Read It

Researched 2026-09-28. All Cloudflare sources below were read at these revisions:
`cloudflare/cloudflare-docs` `production` @ `c1530017` (2026-09-28), `cloudflare/api-schemas` `main` @ `e934edf0` (2026-09-28).

Note on access: in this research environment `api.cloudflare.com`, `developers.cloudflare.com`, `models.dev`, and `api.litellm.ai` were blocked by the egress proxy, and no Cloudflare credentials were available. Everything here comes from the GitHub source of those sites (docs repo, OpenAPI repo, SDK repo, models.dev repo), plus a server-side fetch (Tavily) of the public JSON endpoint and of the LiteLLM catalog. I could not make an authenticated call to the models search API myself.

---

## 1. Two catalogs, not one

Cloudflare's docs site now merges two separate model collections into one "Models" page. The docs' own resolver code says so directly ([`src/util/models/model-resolver.ts`](https://github.com/cloudflare/cloudflare-docs/blob/production/src/util/models/model-resolver.ts)):

> Resolves the two model collections into a single unified `ModelView`:
> - `workers-ai-models` (legacy) — Cloudflare-hosted. `task` is an object; numeric specs live in the `properties[]` array.
> - `catalog-models` (catalog) — third-party / proxied. `task` is a string; specs are top-level fields.
> ... Hosting is a function of the data source (catalog ⇒ proxied, legacy ⇒ hosted).

| Collection | IDs look like | Count (2026-09-28) | What it is | Source of data |
|---|---|---|---|---|
| `workers-ai-models` ("hosted") | `@cf/openai/gpt-oss-120b` | 65 (31 Text Generation) | Models Cloudflare runs on its own GPUs. This is "Workers AI" proper. | Public unauthenticated JSON `https://ai-cloudflare-com.pages.dev/api/models` ([`bin/fetch-ai-models.js`](https://github.com/cloudflare/cloudflare-docs/blob/production/bin/fetch-ai-models.js)) |
| `catalog-models` ("proxied") | `openai/gpt-5.5`, `anthropic/claude-opus-4.7`, `google/gemini-3.5-flash` | 164 (67 Text Generation) | Third-party models (OpenAI, Anthropic, Google, xAI, Alibaba, …) that Cloudflare proxies and bills via AI Gateway unified billing. | Authenticated, undocumented `GET /client/v4/accounts/{id}/ai/catalog/models` ([`bin/fetch-catalog-models.ts`](https://github.com/cloudflare/cloudflare-docs/blob/production/bin/fetch-catalog-models.ts)) |

**For Kiln's Workers AI provider, only the first collection (`@cf/...` hosted models) matters.** The proxied third-party catalog is the AI Gateway "unified billing" catalog and belongs to the AI Gateway subtopic. models.dev also splits them this way: `cloudflare-workers-ai` (27 models, all `@cf/...`) vs `cloudflare-ai-gateway` (55 models, `openai/...`, `anthropic/...`, etc.) — see [models.dev repo `providers/`](https://github.com/sst/models.dev/tree/dev/providers).

---

## 2. Is the list global/static or per-account?

**Short answer: one global, Cloudflare-curated list of `@cf/...` models, with per-account differences in *what you can successfully call*, not in *what model IDs exist*.** Kiln can treat it like OpenRouter/Together: a static list maintained in `ml_model_list.py`.

Evidence for "one global list":

- The docs site builds its catalog from a single **unauthenticated** endpoint with no account context: `const API_URL = "https://ai-cloudflare-com.pages.dev/api/models";` ([fetch-ai-models.js](https://github.com/cloudflare/cloudflare-docs/blob/production/bin/fetch-ai-models.js)). I fetched it on 2026-09-28 (via Tavily): it returned 65 `@cf/...` models, the exact same set as the 65 JSON files in the docs repo.
- Model pages, changelogs and pricing are written as if every account sees the same catalog ("For the full list of available models, refer to the Workers AI model catalog" — [2026-05-08 deprecation changelog](https://developers.cloudflare.com/changelog/post/2026-05-08-planned-model-deprecations/)).
- models.dev syncs the catalog hourly from a single account's `/ai/models/search` and publishes it as the provider's model list for everyone ([sync code](https://github.com/sst/models.dev/blob/dev/packages/core/src/sync/providers/cloudflare-workers-ai.ts)).

Per-account variation that does exist (none of it adds or removes model IDs from the public list):

| Variation | What happens | Source |
|---|---|---|
| **Plan gating (Workers Free vs Paid)** | Some models require the Workers Paid plan. The model JSON carries `{"property_id": "require_workers_paid", "value": "true"}`. On Free, calls return HTTP `403`, internal error `5035`. As of 2026-09-28: `kimi-k2.6`, `kimi-k2.7-code`, `glm-5.2`, `glm-5.3`, `glm-5.3-flash`, `deepseek-v4-pro-0813`, `deepseek-v4-flash-0731`. | [2026-07-28 changelog](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/); [errors.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/platform/errors.mdx): "`Model requires Workers Paid plan` \| `5035` \| `403`" |
| **License click-through** | Llama 3.2 11B Vision needs a one-time `{"prompt": "agree"}` call per account before first use; otherwise `403` / `5016` "User has not agreed to Llama3.2 model terms". | [llama-vision-tutorial.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/guides/tutorials/llama-vision-tutorial.mdx); errors.mdx |
| **LoRA fine-tunes** | Account-specific adapters are *not* new model IDs. You upload an adapter against a `-lora` base model, then pass `"lora": "<finetune id or name>"` in the request to the base model. Listed via `GET /accounts/{id}/ai/finetunes` (account) and `/ai/finetunes/public` (Cloudflare's public `cf-public-*` adapters). Limit: "You can test up to 100 LoRA adapters per account". | [loras.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/features/fine-tunes/loras.mdx), [public-loras.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/features/fine-tunes/public-loras.mdx) |
| **Private / custom models** | Cloudflare offers "private custom models" by request ("complete the Custom Requirements Form"). The catalog API has a `private` flag, which the docs sync skips ("`publicModels = models.filter((m) => !m.private)`"). *Inference:* some accounts may see extra private entries in account-scoped listings. I could not confirm whether `/ai/models/search` ever returns them. | [custom_requirements.mdx partial](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/partials/workers-ai/custom_requirements.mdx); fetch-catalog-models.ts |
| **Experimental / beta** | `/ai/models/search` has a `hide_experimental` filter; 9 hosted models carry `beta: true` (in text generation, only the three old `-lora` bases). | OpenAPI (below); model JSON |
| **Capacity** | The `-fast`, paid-only, and large models return `429`/`3040` "Out of capacity" under load. That is an availability issue, not a catalog difference. | errors.mdx; 2026-07-28 changelog |

**Implication for Kiln:** a static list works. Kiln should (a) not require a per-user model discovery call, (b) consider warning or documenting that several of the best models need Workers Paid (error 5035), and (c) skip `-lora` base models, `llama-guard`, and the license-gated Llama 3.2 Vision unless it is willing to explain the `agree` step.

---

## 3. Machine-readable sources

### 3a. `GET /accounts/{account_id}/ai/models/search` (official, authenticated)

From the OpenAPI spec ([cloudflare/api-schemas `openapi.json`](https://github.com/cloudflare/api-schemas), operationId `workers-ai-search-model`, "Searches Workers AI models by name or description."):

- **Auth required.** `security: api_token` or `api_email + api_key`. Token groups: `"Workers AI Write", "Workers AI Read"`. Permission `com.cloudflare.api.account.ai`. Available on all plans (free/pro/business/enterprise).
- **Query params (verbatim descriptions):**
  - `per_page` (default 100), `page` (default 1)
  - `task` — "Filter by Task Name." example `"Text Generation"`
  - `author` — "Filter by Author."
  - `source` — "Filter by Source Id." (historically `1` = `@cf`, `2` = `@hf`; see lifecycle doc)
  - `hide_experimental` — "Filter to hide experimental models." default false
  - `search` — "Search."
  - `include_deprecated` — "**If true, include models for up to three months after their deprecation date. Defaults to false.**"
  - `format` — enum `["openrouter"]` — "If set, return models in the requested marketplace format instead of the default response."
- **Response:** "Default shape is the standard envelope; when `format` is supplied the marketplace-specific shape is returned instead." Default envelope = `{success, result: [object], errors, messages}`; `format=openrouter` = `{data: [object]}` ("See https://openrouter.ai/docs/guides/get-started/for-providers"). **Item schema is untyped (`object`) in the OpenAPI spec and in the Python SDK** (`SyncV4PagePaginationArray[object]`, [cloudflare-python `models.py`](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/ai/models/models.py)).
- `x-forge-hidden: true` — the endpoint is flagged hidden in some tooling, although the SDK exposes it as `client.ai.models.list(...)`.

**Default-format item fields** (inferred — the public pages.dev JSON and the docs JSON have this shape, and LiteLLM's commit says its entries came from "Cloudflare's live /ai/models/search?task=Text Generation catalog" with the same fields):

```json
{
  "id": "f9f2250b-1048-4a52-9910-d0bf976616a1",
  "source": 1,
  "name": "@cf/openai/gpt-oss-120b",
  "description": "...",
  "task": {"id": "c329a1f9-...", "name": "Text Generation", "description": "..."},
  "created_at": "2025-08-05 10:27:29.131",
  "tags": [],
  "properties": [
    {"property_id": "context_window", "value": "128000"},
    {"property_id": "price", "value": [{"unit": "per M input tokens", "price": 0.35, "currency": "USD"}, {"unit": "per M output tokens", "price": 0.75, "currency": "USD"}]},
    {"property_id": "function_calling", "value": "true"},
    {"property_id": "reasoning", "value": "true"},
    {"property_id": "reasoning_effort", "value": {"supported_efforts": ["low","medium","high"], "default_effort": "medium", "mandatory": true, "default_enabled": true}},
    {"property_id": "async_queue", "value": "true"}
  ]
}
```
(from [`gpt-oss-120b.json`](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/workers-ai-models/gpt-oss-120b.json); the docs copy also embeds `schema.input`/`schema.output` JSON Schemas and a `deprecated` boolean — whether search returns `schema` inline is unverified; there is a separate `GET /ai/models/schema?model=` endpoint that "Retrieves the input and output JSON schema definition for a Workers AI model.")

**All `property_id` values seen across the 65 hosted models** (count in parentheses): `price` (53), `context_window` (34), `terms` (27), `async_queue` (19), `function_calling` (18), `reasoning` (16), `reasoning_effort` (12), `info` (11), `partner` (10), `beta` (9), `lora` (9), `vision` (8), `require_workers_paid` (7), `realtime` (6), `max_input_tokens` (3), `output_dimensions` (3), `languages` (1). Plus, when a retirement is scheduled, **`planned_deprecation_date`** (e.g. `"2026-05-30"`; none present on 2026-09-28).

What is **not** in the metadata: no JSON-mode / structured-output flag, no max-output-tokens field for hosted models, no OpenAI-compatible-endpoint flag. Booleans are strings (`"true"`), and absence means false/unknown.

**`format=openrouter` shape** (unverified by a live call). models.dev's sync consumes it and its parser/test fixture show rows like `{"id": "workers-ai/@cf/...", "name", "created", "hugging_face_id", "context_length", "architecture": {"input_modalities", "output_modalities"}, "pricing": {"prompt": "0.000001", "completion": "0.000002", "overrides": [...]}, "top_provider": {"context_length", "max_completion_tokens"}, "supported_parameters": [...], "reasoning": {...}}` and alternatively `input_modalities`, `max_output_length`, `supported_features`, `supported_sampling_parameters` ([sync code](https://github.com/sst/models.dev/blob/dev/packages/core/src/sync/providers/cloudflare-workers-ai.ts), [test](https://github.com/sst/models.dev/blob/dev/packages/core/test/cloudflare-workers-ai.test.ts)). models.dev's own model comments cite it: "Source: Workers AI /ai/models/search?format=openrouter (2026-09-18)". This format is attractive for Kiln because it carries input modalities (vision), max output tokens, and supported parameters (tools, structured outputs, reasoning) in a standard shape — but I could not see a real response, so treat field names as needing confirmation.

### 3b. `https://ai-cloudflare-com.pages.dev/api/models` (public, unauthenticated, undocumented)

- Returns `{"models": [ ...same item shape as above, including `schema` ... ]}`. ~880 KB. Fetched successfully on 2026-09-28 (65 models, all `@cf/`).
- It is what Cloudflare's docs build uses. The docs script notes it "fans out per-model schema fetches on cache miss and can return a transient 502", so it retries.
- **Caveat:** it is a Cloudflare Pages deployment backing Cloudflare's own sites, not a documented API. It could move or change without notice. It needs no credentials, which makes it the easiest source for an agent/skill.

### 3c. `cloudflare/cloudflare-docs` repo, `src/content/workers-ai-models/*.json` (public, via GitHub)

- One JSON file per hosted model, named after the last ID segment (e.g. `glm-5.3.json`). Same shape as 3b.
- Raw URL pattern: `https://raw.githubusercontent.com/cloudflare/cloudflare-docs/production/src/content/workers-ai-models/<name>.json`. A directory listing needs the GitHub API or a sparse clone.
- **Freshness:** synced from 3b and also hand-edited in PRs (e.g. "[Workers AI] Fix DeepSeek V4 Flash context window (#33055)", "[Workers AI] Update model reasoning efforts (#33541)"). New models land the same day as the changelog (e.g. GLM-5.3: commit `3441bfe4c` on 2026-08-28, changelog dated 2026-08-28).
- **Deprecation handling:** since May 2026 the sync skips models whose `planned_deprecation_date` is in the past and deletes their files; files with a future date are kept even if the API drops them ([commit `225279a14`](https://github.com/cloudflare/cloudflare-docs/commit/225279a1461d1a39c752889304c65380688e1991): "Adds planned_deprecation_date to 18 model JSONs so model pages render a 'Planned deprecation' pill before the date and disappear after."). So a model with a `planned_deprecation_date` property in this directory = scheduled for retirement; a model missing from this directory = retired.
- The `deprecated` field is present but `false` on all 65 files (older files had `null`); it is not the signal Cloudflare uses.

### 3d. `GET /accounts/{account_id}/ai/catalog/models` (authenticated, undocumented)

- The "Unified Catalog" used by the dashboard (docs script comment: "Go to Workers AI > Models in the dashboard … Find the request to /ai/catalog/models"). Not in the public OpenAPI spec.
- Fields: `model_id`, `provider_id`, `name`, `task` (string), `tags`, `context_length`, `max_output_tokens`, `supports_async`, `zdr`, `request_formats` (e.g. `["chat-completions","responses"]`, `["anthropic-messages"]`), `metadata` (free-form, includes `planned_deprecation_date`, `function_calling`, `beta`, `lora`…), `private`, `pricing`, `schema`, `examples`, `banner`.
- The docs repo copy (`src/content/catalog-models/`) contains only third-party proxied models (164, none `@cf/`). *Inference:* hosted `@cf/` models may also appear in the live API (the resolver says "a catalog row shadows a legacy row when `model_id === name`"), but none do in the committed data.
- Not recommended for Kiln: undocumented, and its useful content is the AI Gateway catalog.

### 3e. Other sources checked

- **OpenAI-compatible `GET /ai/v1/models`:** not in the OpenAPI spec and not mentioned in the OpenAI-compatibility docs (which list only `/v1/chat/completions`, `/v1/embeddings`, `/v1/responses`). I found no evidence it exists. (API subtopic owns this.)
- **Changelog RSS:** the docs site has per-product RSS routes (`src/pages/changelog/rss/[product].xml.ts`), so a Workers AI feed should be at `https://developers.cloudflare.com/changelog/rss/workers-ai.xml` (URL inferred from the route file, not fetched).
- **Third-party mirrors** such as `ai.flared.au` ("Cloudflare Workers AI — live model reference", seen in search results) exist; not evaluated, not official.
