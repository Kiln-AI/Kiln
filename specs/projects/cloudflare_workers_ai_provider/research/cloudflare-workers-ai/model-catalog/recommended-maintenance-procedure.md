# Recommended Procedure: Keeping Kiln's Cloudflare Workers AI Entries Current

This is a proposal for what to add to `.agents/skills/claude-maintain-models/SKILL.md` (and the deprecation tooling) once the Cloudflare provider exists. It is based on the findings in the other files in this directory. Snippets were tested with `jq` against the docs-repo copy of the data (same shape as the live endpoint), not against the live endpoint, which was blocked for `curl` in this environment.

## Principles

1. **Cloudflare's own list is the source of truth for slugs and capabilities.** LiteLLM has not been updated for Cloudflare since 2026-06-23 and still lists retired models. It fails the skill's "verify every slug" rule for new models.
2. **models.dev is a good second source for additions** (hourly automated sync, same-day coverage, provider key `cloudflare-workers-ai`). It is weak for removals, because its sync stopped deleting missing models on 2026-09-21.
3. **Treat Cloudflare as a "direct-check" provider**, like Fireworks/Together/SiliconFlow/Featherless in the skill's Lagging Providers section.
4. The list is **global**, so no per-user discovery is needed. Per-account differences (Workers Paid plan, Llama 3.2 Vision license, LoRAs) affect whether a call succeeds, not which IDs exist.

## Step-by-step

### A. Fetch the current list (no credentials needed)

```bash
curl -s https://ai-cloudflare-com.pages.dev/api/models -o /tmp/cf_models.json

# Text-generation models, newest first, with Kiln-relevant flags
jq -r '.models[] | select(.task.name=="Text Generation")
  | (reduce .properties[] as $p ({}; .[$p.property_id]=$p.value)) as $p
  | [.name, .created_at[0:10], ($p.context_window//"-"),
     (if $p.function_calling=="true" then "tools" else "" end),
     (if $p.vision=="true" then "vision" else "" end),
     (if $p.reasoning=="true" then "reasoning" else "" end),
     (if $p.require_workers_paid=="true" then "paid" else "" end),
     (if $p.lora=="true" then "lora" else "" end),
     ($p.planned_deprecation_date//"")] | @tsv' /tmp/cf_models.json | sort -t$'\t' -k2 -r

# Full record for one model (drop the large schema)
jq '.models[] | select(.name=="@cf/zai-org/glm-5.3") | del(.schema)' /tmp/cf_models.json
```

The response is ~900 KB: save it and filter with `jq`, never WebFetch it. It can return a transient 502 (Cloudflare's own docs script retries up to 4 times).

**Fallbacks, in order:**

1. The official authenticated API, if a token is set (`CLOUDFLARE_API_TOKEN` with Workers AI Read, plus `CLOUDFLARE_ACCOUNT_ID`):
   ```bash
   curl -s "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/ai/models/search?task=Text%20Generation&per_page=1000" \
     -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '.result[].name'
   ```
   Add `&include_deprecated=true` to see models retired in the last three months. `&format=openrouter` returns an OpenRouter-style shape that includes input modalities and supported parameters (field names unverified; check once).
2. models.dev: `curl -s https://models.dev/api.json | jq '.["cloudflare-workers-ai"].models | keys[]'`.
3. The docs repo files: `src/content/workers-ai-models/*.json` in `cloudflare/cloudflare-docs` (same shape; synced from the endpoint above and hand-corrected).

### B. Discovery (skill Phase 1)

- Cross-reference the `@cf/` names from step A against the Cloudflare provider entries in `ml_model_list.py`. Report models that are new, and models Kiln has that Cloudflare no longer lists.
- For each candidate, find the existing Kiln `ModelName` (most notable Cloudflare models are already in Kiln under other providers; see `text-generation-models.md`). Adding Cloudflare is usually a new `KilnModelProvider` on an existing model, not a new model.
- **Skip by default:** `-lora` bases (need a `lora` request parameter; beta; small contexts), `llama-guard-*` (classifier), coding models (`kimi-k2.7-code`, `qwen2.5-coder-*`) per the skill's existing rule, and non-chat tasks.
- Also scan the Workers AI changelog for launches in the last two weeks, in case the endpoint lags: `https://developers.cloudflare.com/changelog/product/workers-ai/`.

### C. Setting flags on a new entry (skill Phase 3)

| Cloudflare property | Kiln setting |
|---|---|
| `name` (e.g. `@cf/qwen/qwen3.8-27b`) | `model_id`, exactly as given (whether Kiln adds a `cloudflare/` prefix is decided by the API subtopic's adapter choice) |
| `function_calling: "true"` | tools supported; candidate for `StructuredOutputMode.json_schema` or `function_calling` — **confirm with paid tests**, since the catalog has no JSON-mode flag and the docs' JSON-mode model list is stale |
| `vision: "true"` | `supports_vision`, `multimodal_capable`, image MIME types; start broad, narrow on 400s (existing skill rule) |
| `reasoning: "true"` + `reasoning_effort.supported_efforts` | `available_thinking_levels` from `supported_efforts`; `mandatory: true` means reasoning cannot be turned off. Re-read on every run: Cloudflare edited these on 2026-09-24 |
| `context_window` | informational; note small windows (Llama 3.3 70B fp8-fast is only 24,000) |
| `require_workers_paid: "true"` | Kiln has no field for this today. Note it in the PR and consider a UI hint (spec decision); Free-plan users get `403` / error `5035` |
| `planned_deprecation_date` present | do not add the model |

Keep the skill's rule: default `reasoning_capable=False` unless the model always emits reasoning.

### D. Deprecation checks (`kiln-check-deprecation`)

- Add Cloudflare to `PROVIDER_CONFIG` in `.agents/scripts/provider_utils.py` with a fetcher for the public endpoint (no key), returning `{m["name"] for m in data["models"]}`. Optionally fall back to the authenticated search API.
- Also report models whose `planned_deprecation_date` is set, so Kiln can remove them **before** the date. Notice periods have been 13–22 days.
- Why it matters: at retirement Cloudflare may **alias** an old ID to a newer, more expensive model (Kimi K2.5 → K2.6 on 2026-05-30). A stale Kiln entry can keep "working" while running a different model.

### E. Cost reporting

LiteLLM's price map lacks every Cloudflare model added after 2026-06-23 (GLM-5.3, GLM-5.3 Flash, Qwen 3.8 27B, DeepSeek V4 Pro/Flash). Expect `cost: null` for those unless the adapter path gets cost elsewhere. Cloudflare's `price` property has per-million-token prices if Kiln ever wants its own fallback.

## Suggested text for the skill's Lagging Providers section

> **Cloudflare Workers AI** — LiteLLM's `cloudflare/` entries are a one-time import from June 2026 and are stale (missing newer models, still listing retired ones). models.dev (`cloudflare-workers-ai`) syncs hourly and is current, but no longer removes retired models. The authoritative list is Cloudflare's public, unauthenticated JSON: `curl -s https://ai-cloudflare-com.pages.dev/api/models` (save to a file; ~900 KB; filter `.models[] | select(.task.name=="Text Generation")`). Model IDs are the `name` field (`@cf/<author>/<model>`). Capabilities are in `properties[]` (`function_calling`, `vision`, `reasoning`, `reasoning_effort`, `context_window`, `require_workers_paid`, `planned_deprecation_date`). With a token, `GET /accounts/{id}/ai/models/search?task=Text%20Generation` returns the same data officially.
