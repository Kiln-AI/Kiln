---
name: kiln-check-deprecation
description: Check Kiln's model list for deprecated or sunset models across all providers. Use when the user wants to find deprecated models, check model availability, audit the model list for stale entries, or mentions model deprecation/sunset/end-of-life.
---

# Check Model Deprecation in Kiln

Audit `libs/core/kiln_ai/adapters/ml_model_list.py` to find models that have been deprecated, removed, or are approaching end-of-life across all providers. **All checks are free** — they use model-listing endpoints, not inference.

---

## Global Rules

- **Sandbox:** All `curl`, `uv run`, and `python3` commands that hit the network MUST use `required_permissions: ["all"]`. The sandbox blocks network access.
- **Env vars:** Source `.env` before running check scripts: `export $(grep -v '^#' .env | xargs)`
- **Vertex AI auth:** The Vertex check requires `gcloud` CLI authentication. Before running, ask the user to run `gcloud auth login` if they haven't recently. If `gcloud auth print-access-token` fails, prompt the user to authenticate.
- **Non-destructive:** This skill only sets `deprecated=True` on individual provider entries. It never removes models or providers from the list.
- **Skip already-deprecated:** Only check providers where `deprecated=False` (the default). Don't re-check entries already marked deprecated.

---

## Phase 1 – Extract Current Model-Provider Pairs

Run the extraction script from the repo root:

```bash
python3 .cursor/skills/kiln-check-deprecation/scripts/extract_models.py > /tmp/kiln_extracted.json
```

This fetches the published model list from `https://remote-config.getkiln.ai/kiln_config_v2.json` and extracts:
- The provider name
- The model_id
- The parent model's enum name

It skips entries already marked `deprecated=True`.

**Output:** JSON to stdout (pipe to file), human summary to stderr.

The JSON contains:
- `deprecated_count`: number of already-deprecated entries
- `providers`: dict of provider_name → sorted unique list of model_ids
- `entries`: list of `{enum, provider, model_id}` for each non-deprecated entry

---

## Phase 2 – Check Each Provider

### Option A: Check all providers at once

```bash
export $(grep -v '^#' .env | xargs)
python3 .cursor/skills/kiln-check-deprecation/scripts/check_provider.py all > /tmp/kiln_check_results.json
```

### Option B: Check a single provider

```bash
export $(grep -v '^#' .env | xargs)
python3 .cursor/skills/kiln-check-deprecation/scripts/check_provider.py openrouter > /tmp/kiln_check_openrouter.json
```

The script handles all provider API quirks automatically:
- **Together AI** returns a flat JSON array (not `{data: [...]}`)
- **Gemini API** needs both v1 and v1beta endpoints (preview/Gemma models only on v1beta)
- **Gemini** model names are prefixed with `models/` — stripped automatically
- **Anthropic** uses `x-api-key` header, not `Authorization: Bearer`
- **OpenRouter** is public (no auth) and includes `expiration_date` fields
- **Fireworks AI** `/v1/models` only lists serverless models; the script instead checks each model individually via the model detail API (`GET /v1/{model_id}`), which covers all tiers (serverless, on-demand, fine-tune). A model is only flagged as missing if it returns HTTP 404 from the detail API.
- **OpenRouter** `:exacto` is a virtual routing suffix (quality-first provider sorting) that never appears in model listings. The script strips it before checking. `:free` and `:thinking` are real model entries that appear in the listing when available — if they're missing, it's a genuine removal.
- **Vertex AI** uses the v1beta1 publisher models endpoint with `x-goog-user-project` header. Requires `gcloud` CLI auth. Kiln entries may use `meta/` prefix for LiteLLM routing — stripped automatically. Versioned aliases like `gemini-2.0-flash` → `gemini-2.0-flash-001` are handled.

**Output:** JSON to stdout with per-provider results, human summary to stderr.

Each provider result contains:
- `missing`: model_ids not found in the provider's listing
- `expiring`: model_ids with upcoming expiration dates (OpenRouter only)
- `entries_to_deprecate`: full enum/provider/model_id entries for each missing model
- `skipped` / `error`: if credentials missing or API call failed

### Supported providers

| Provider | Env Var | Auth |
|----------|---------|------|
| OpenRouter | (none — public API) | None |
| OpenAI | `OPENAI_API_KEY` | Bearer |
| Anthropic | `ANTHROPIC_API_KEY` | x-api-key |
| Gemini API | `GEMINI_API_KEY` | Query param |
| Fireworks AI | `FIREWORKS_API_KEY` | Bearer |
| Together AI | `TOGETHER_API_KEY` | Bearer |
| SiliconFlow CN | `SILICONFLOW_CN_API_KEY` | Bearer |
| Cerebras | `CEREBRAS_API_KEY` | Bearer |
| Groq | `GROQ_API_KEY` | Bearer |
| Vertex AI | `VERTEX_PROJECT_ID` + `gcloud` CLI auth | OAuth (gcloud) |

### Providers NOT covered by the script (check manually if needed)

#### Amazon Bedrock

Requires `aws` CLI configured. If not installed, skip.

```bash
aws bedrock list-foundation-models --output json | \
  jq '[.modelSummaries[] | {modelId, status: .modelLifecycle.status, endOfLife: .modelLifecycle.endOfLifeTime}]'
```

Flag any model where `status == "LEGACY"` or `endOfLifeTime` is approaching.

### LiteLLM Model DB (supplementary signal)

Cross-reference against LiteLLM's public model database for `deprecation_date` fields. This mostly covers Azure/OpenAI date-stamped models but is a useful secondary signal.

```bash
curl -s https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json | \
  jq 'to_entries[] | select(.value.deprecation_date != null) | {model: .key, deprecation_date: .value.deprecation_date}'
```

### Providers to skip

These don't have meaningful deprecation to check:
- `ollama` — local models, user-managed
- `kiln_fine_tune` — internal
- `kiln_custom_registry` — internal
- `openai_compatible` — user-configured
- `docker_model_runner` — local
- `azure_openai` — typically mirrors OpenAI, covered by OpenAI check
- `huggingface` — serverless inference, model availability varies

---

## Phase 3 – Report Findings

Read the JSON output from check_provider.py and present findings in a clear table to the user:

```text
Deprecation Audit Results
=========================

❌ REMOVED (model not found in provider's model list):
  - ModelName.gemini_1_5_pro → gemini_api (model_id: gemini-1.5-pro)
  - ModelName.gemini_1_5_pro → openrouter (model_id: google/gemini-pro-1.5)

⚠️ EXPIRING SOON (within 90 days):
  - ModelName.claude_3_7_sonnet → openrouter (model_id: anthropic/claude-3.7-sonnet, expires: 2026-05-05)

⚠️ LEGACY (Bedrock lifecycle status):
  - ModelName.mistral_large → amazon_bedrock (model_id: mistral.mistral-large-2407-v1:0, status: LEGACY)

✅ ALL CLEAR:
  - openai: 20/20 models found
  - anthropic: 8/11 models found (3 deprecated above)

⏭️ SKIPPED (no credentials):
  - groq
  - amazon_bedrock
```

Group by provider within each category. Use the `entries_to_deprecate` field from the JSON to get the ModelName enum for each entry.

---

## Phase 4 – Mark Deprecated

For each confirmed-removed model, set `deprecated=True` on the affected `KilnModelProvider` entry.

To find the line to edit, grep for the `model_id` in `ml_model_list.py`:

```bash
grep -n 'model_id="<model_id>"' libs/core/kiln_ai/adapters/ml_model_list.py
```

Then add `deprecated=True,` after the `model_id=` line in the matching `KilnModelProvider` block.

**Rules:**
- Only mark a provider deprecated if its model_id is confirmed missing from that provider's model list
- If ALL providers for a `KilnModel` are deprecated, note this to the user — they may want to consider removing the model entirely
- For "expiring soon" models, inform the user but don't mark deprecated yet — let them decide
- For Bedrock `LEGACY` status, mark deprecated (the model still works but is on its way out)

**Ask the user to confirm** before making changes. Present the list of changes and wait for approval.

---

## Phase 5 – Verify

After marking providers deprecated, run a quick sanity check:

```bash
grep -c "deprecated=True" libs/core/kiln_ai/adapters/ml_model_list.py
```

Ensure the count matches what you expect (previous count + newly marked).

---

## Checklist

- [ ] Extraction script run, JSON saved to /tmp/kiln_extracted.json
- [ ] Provider checks run (all or individually)
- [ ] Vertex auth confirmed (`gcloud auth print-access-token` works, or skip Vertex)
- [ ] Bedrock checked manually (skip if aws CLI unavailable)
- [ ] LiteLLM DB checked for supplementary deprecation_date signals
- [ ] Findings reported to user with clear table
- [ ] User confirmed changes before marking deprecated
- [ ] `deprecated=True` set on confirmed entries
- [ ] Deprecation count verified
