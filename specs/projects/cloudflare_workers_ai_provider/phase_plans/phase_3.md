---
status: complete
---

# Phase 3: Cloudflare Model Entries and Maintenance Tooling

## Overview

Phases 1 and 2 added the Cloudflare provider plumbing and connect card (PR 1). This phase is PR 2: it gives the 10 curated Cloudflare Workers AI models a `KilnModelProvider` entry each, with per-model flags confirmed by the paid per-model tests, adds a Cloudflare model to the prerelease whitelist, and teaches the model-maintenance tooling (shared provider script, deprecation-check script and the three skill docs) about Cloudflare. It must merge only after a client release that includes PR 1.

## Steps

1. `libs/core/kiln_ai/adapters/ml_model_list.py`: append a `KilnModelProvider(name=ModelProviderName.cloudflare, model_id="@cf/...")` to the `providers` list of each model:

   | Kiln `ModelName` | `model_id` |
   |---|---|
   | `deepseek_4_pro` | `@cf/deepseek-ai/deepseek-v4-pro-0813` |
   | `deepseek_4_flash` | `@cf/deepseek-ai/deepseek-v4-flash-0731` |
   | `glm_5_3` | `@cf/zai-org/glm-5.3` |
   | `glm_5_3_flash` | `@cf/zai-org/glm-5.3-flash` |
   | `glm_5_2` | `@cf/zai-org/glm-5.2` |
   | `glm_4_7_flash` | `@cf/zai-org/glm-4.7-flash` |
   | `kimi_k2_6` | `@cf/moonshotai/kimi-k2.6` |
   | `qwen_3p8_27b` | `@cf/qwen/qwen3.8-27b` |
   | `gemma_4_27b` (Gemma 4 26B A4B) | `@cf/google/gemma-4-26b-a4b-it` |
   | `nemotron_3_super` | `@cf/nvidia/nemotron-3-120b-a12b` |

   Starting flags, then adjusted by the paid tests:
   - `structured_output_mode=StructuredOutputMode.json_schema` (these models take the OpenAI `response_format` envelope natively); fall back per model to `json_instruction_and_object` / `json_instructions` if a test shows the schema is ignored or rejected.
   - `supports_function_calling` left at its default (`True`, every model has Cloudflare's `function_calling` flag); set to `False` where the tool tests fail.
   - `reasoning_capable=False` (the skill's default for adaptive reasoning); reasoning is still parsed from `reasoning_content`.
   - Vision models per Cloudflare's `vision` flag (GLM 5.3 Flash, Kimi K2.6, Qwen 3.8 27B, Gemma 4 26B): `supports_vision=True`, `multimodal_capable=True`, `multimodal_mime_types=[JPG, PNG]`. No doc extraction, so no extraction sweep is added.
   - No `available_thinking_levels` (same as the Fireworks and Together entries for these models); no `max_tokens` or other provider options; no `suggested_for_*` flags.
2. `libs/core/kiln_ai/adapters/pytest_prerelease_whitelist.py`: add `("glm_4_7_flash", ModelProviderName.cloudflare.value)` to `PRERELEASE_CHAT_MODELS`.
3. `.agents/scripts/provider_utils.py`:
   - `PROVIDER_CONFIG["cloudflare"] = {"type": "cloudflare", "env": "CLOUDFLARE_API_KEY", "account_env": "CLOUDFLARE_ACCOUNT_ID"}`.
   - `CLOUDFLARE_PUBLIC_MODELS_URL = "https://ai-cloudflare-com.pages.dev/api/models"`.
   - `fetch_cloudflare(api_key: str | None, account_id: str | None) -> tuple[set[str], dict[str, str]]`: when both are set, page through `GET /accounts/{account}/ai/models/search?task=Text%20Generation&include_deprecated=true`; otherwise read the public JSON and keep `task.name == "Text Generation"`. Returns `(available_ids, planned_deprecation_dates)`. A model whose `planned_deprecation_date` is today or earlier is left out of `available_ids` (it is retired, and may be aliased), but kept in the dates dict.
4. `.agents/skills/kiln-check-deprecation/scripts/check_provider.py`:
   - Import `fetch_cloudflare`. Cloudflare doesn't skip when `CLOUDFLARE_API_KEY` is missing (public fallback); a `cloudflare` branch reads both env vars and returns planned deprecation dates as `expiring`.
   - Add Cloudflare quirks to the module docstring.
5. `.agents/skills/kiln-check-deprecation/SKILL.md`: Cloudflare row in the supported-providers table, a Cloudflare quirks bullet, and a rule that a Cloudflare entry with any `planned_deprecation_date` is marked deprecated before that date (not left for the user as "expiring soon"), because Cloudflare may alias the retired ID to another model.
6. `.agents/skills/claude-maintain-models/SKILL.md`:
   - `cloudflare` row in the `model_id` format table.
   - Cloudflare in Phase 1B's lagging-provider list, and a Cloudflare entry in the Lagging Providers reference (public JSON, authenticated search API, models.dev cross-check, never LiteLLM's catalog, docs repo fallback).
   - A Cloudflare section in Provider Quirks: inclusion rule and how to tell OpenAI-format from older models (`schema.input` has `max_completion_tokens`, older models have `prompt`/`raw` and a 256 default `max_tokens`), skip list, flag mapping from Cloudflare properties, Workers Paid note, JSON mode has no streaming, no cost data in LiteLLM, and the **No Model Substitution** rule (remove entries before `planned_deprecation_date`).
7. `.agents/skills/kiln-prerelease-check/SKILL.md`: add `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` to the env var list.

## Tests

- Existing parametrized unit tests over `built_in_models` (`test_ml_model_list.py`, adapter tests) cover the new entries' validity.
- `test_ml_model_list.py::test_prerelease_chat_models_exist`: every `PRERELEASE_CHAT_MODELS` pair names a real, non-deprecated built-in model and provider (catches whitelist typos, including the new Cloudflare pair).
- `test_ml_model_list.py::test_cloudflare_model_ids_use_workers_ai_ids`: every Cloudflare entry's `model_id` starts with `@cf/` (the openai route sends the ID verbatim, so a stray prefix would 400).
- Live per-model paid tests (`--runpaid --ollama -k cloudflare`), run model by model with low parallelism, set the final flags. Not part of CI.
- Manual run of `check_provider.py cloudflare` against a fresh extract, with and without credentials.
