---
name: kiln-check-finetune-deprecation
description: Check Kiln's fine-tunable model list for deprecated or unsupported base models. Use when the user wants to audit fine-tuning support, check if fine-tune base models are still valid, or mentions fine-tune model deprecation.
---

# Check Fine-Tune Model Deprecation in Kiln

Audit the fine-tunable models listed in Kiln to find base models that are no longer supported for fine-tuning by their providers. This is separate from general model deprecation — a model can still be available for inference but no longer supported as a fine-tuning base.

---

## Global Rules

- **Sandbox:** All `curl`, `uv run`, and `python3` commands that hit the network MUST use `required_permissions: ["all"]`. The sandbox blocks network access.
- **Env vars:** Source `.env` before running check scripts: `export $(grep -v '^#' .env | xargs)`
- **Vertex AI auth:** The Vertex check requires `gcloud` CLI authentication. Before running, ask the user to run `gcloud auth login` if they haven't recently. If `gcloud auth print-access-token` fails, prompt the user to authenticate.
- **Non-destructive:** This skill only reports findings. It does not automatically remove or deprecate models.

---

## Supported Providers

| Provider | Env Var | Auth |
|----------|---------|------|
| OpenAI | `OPENAI_API_KEY` | Bearer |
| Together AI | `TOGETHER_API_KEY` | Bearer |
| Vertex AI | `VERTEX_PROJECT_ID` + `gcloud` CLI auth | OAuth (gcloud) |
| Fireworks AI | `FIREWORKS_API_KEY` | Bearer |

---

## Background

Kiln has two types of fine-tunable model entries:

1. **Static entries** — Models in `libs/core/kiln_ai/adapters/ml_model_list.py` with `provider_finetune_id` set. Currently used by OpenAI, Together AI, and Vertex AI.
2. **Dynamic entries (Fireworks)** — Fetched at runtime from `api.fireworks.ai/v1/accounts/fireworks/models` filtering by `tunable=True`. This list is managed by Fireworks and may include stale/unsupported models.

The API endpoint that serves the fine-tune dropdown is `GET /api/finetune_providers` in `app/desktop/studio_server/finetune_api.py`.

---

## Phase 1 – Check Static Fine-Tune IDs

Run the check script from the repo root:

```bash
python3 .agents/skills/kiln-check-finetune-deprecation/scripts/check_finetune.py static > /tmp/kiln_finetune_static.json
```

This extracts all `provider_finetune_id` entries from `ml_model_list.py` and checks each provider's API to see if the model is still available for fine-tuning:

- **OpenAI:** Checks `GET https://api.openai.com/v1/models` — fine-tunable models are those with ID matching the `provider_finetune_id`. OpenAI date-stamps fine-tunable model IDs (e.g. `gpt-4o-2024-08-06`), so if the dated version is removed, it's no longer fine-tunable.
- **Together AI:** Checks `GET https://api.together.xyz/v1/models` and filters for models with `"type": "chat"` that match the `provider_finetune_id`. Together uses full HuggingFace-style IDs (e.g. `meta-llama/Meta-Llama-3.1-8B-Instruct-Reference`).
- **Vertex AI:** Checks the Vertex AI tuning documentation / API. Vertex fine-tuning uses specific versioned model IDs (e.g. `gemini-2.0-flash-001`).

**Output:** JSON to stdout with per-provider results, human summary to stderr.

---

## Phase 2 – Check Fireworks Dynamic Models

Fireworks fine-tunable models are fetched dynamically from their API, not stored in `ml_model_list.py`. The concern here is that the Fireworks API's `tunable=True` flag may be stale — listing models that Fireworks no longer actually supports for fine-tuning.

```bash
python3 .agents/skills/kiln-check-finetune-deprecation/scripts/check_finetune.py fireworks > /tmp/kiln_finetune_fireworks.json
```

This script:
1. Fetches all `tunable=True` models from `api.fireworks.ai/v1/accounts/fireworks/models`
2. Cross-references against `FIREWORKS_SUPPORTED_FINETUNE_MODELS` from `app/desktop/studio_server/finetune_api.py` — the same allowlist that filters the runtime fine-tune dropdown
3. Reports models that appear in the API as tunable but are NOT in the allowlist

The canonical allowlist lives in `finetune_api.py` and is shared between the runtime dropdown filter and this audit skill. There is a single place to update when Fireworks changes their supported models.

**Output:** JSON to stdout, human summary to stderr.

---

## Phase 3 – Report Findings

Read the JSON outputs and present findings in a clear table:

```text
Fine-Tune Deprecation Audit Results
====================================

STATIC PROVIDERS (provider_finetune_id in ml_model_list.py):

  ✅ OpenAI: 5/5 found
     gpt-4.1-2025-04-14, gpt-4.1-mini-2025-04-14, gpt-4.1-nano-2025-04-14,
     gpt-4o-2024-08-06, gpt-4o-mini-2024-07-18

  ✅ Vertex AI: 2/2 found
     gemini-2.0-flash-001, gemini-2.0-flash-lite-001

  ❌ Together AI: 2/4 missing
     ✅ Qwen/Qwen2.5-72B-Instruct — found
     ✅ Qwen/Qwen2.5-14B-Instruct — found
     ❌ meta-llama/Meta-Llama-3.1-8B-Instruct-Reference — NOT FOUND
     ❌ meta-llama/Meta-Llama-3.1-70B-Instruct-Reference — NOT FOUND

  ⏭️ SKIPPED (no credentials):
     - vertex (VERTEX_PROJECT_ID not set)

DYNAMIC PROVIDER (Fireworks):

  ⚠️ 167 models marked tunable in API
  ⚠️ 15 models in known-good docs list
  ✅ 11 models in both API and docs
  ❌ 156 models in API but NOT in docs (likely stale)
     - accounts/fireworks/models/qwen2-72b-instruct
     - accounts/fireworks/models/code-llama-7b
     - ...
  ⚠️ 4 models in docs but NOT in API
     - accounts/fireworks/models/gemma-2-9b-it
     - ...
```

Note: The example above is illustrative. Actual model counts and entries will vary.

---

## Phase 4 – Remediation

Based on findings, recommend specific actions:

### For static entries (`provider_finetune_id`):
- If a model's fine-tune ID is no longer valid, either:
  - **Update** the `provider_finetune_id` to a newer version if one exists
  - **Remove** the `provider_finetune_id` field to stop offering fine-tuning for that model on that provider
  - **Set `deprecated=True`** on the provider entry if the model is fully gone

### For Fireworks dynamic entries:
- The stale models come from Fireworks' API, not our code. Options:
  - **Filter in our code** — update `fetch_fireworks_finetune_models()` in `finetune_api.py` to filter against a known-good list
  - **Report to Fireworks** — flag the stale models to Fireworks support
  - **Both** — filter now, report later

**Always ask the user to confirm** before making any code changes.

---

## Phase 5 – Verify

After any changes, run the relevant tests:

```bash
uv run python3 -m pytest app/desktop/studio_server/test_finetune_api.py -q
```

---

## Checklist

- [ ] Env vars sourced from `.env`
- [ ] Vertex auth confirmed (`gcloud auth print-access-token` works, or skip Vertex)
- [ ] Static fine-tune IDs checked against provider APIs (OpenAI, Together, Vertex)
- [ ] Fireworks dynamic models cross-referenced against known-good list
- [ ] Findings reported to user with clear table
- [ ] User confirmed remediation approach
- [ ] Code changes made (if any)
- [ ] Tests pass after changes
- [ ] FIREWORKS_SUPPORTED_FINETUNE_MODELS in finetune_api.py updated if docs have changed
