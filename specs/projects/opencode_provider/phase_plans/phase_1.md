---
status: complete
---

# Phase 1: Core OpenCode provider support in `libs/core`

## Overview

Make OpenCode a working provider in the `kiln_ai` library: the enum member, the config key, the LiteLLM mapping onto Kiln's OpenAI-compatible path with a fixed base URL, the missing-key warning, the `built_in_providers` item, and cost read from `usage.cost` only. Wire tests run the real `LiteLlmAdapter` and LiteLLM request/exception mapping against recorded OpenCode bodies through respx, pinning the request shape, the cost source, and that OpenCode's error text and status code reach the exception Kiln keeps.

Connect/disconnect, the API schema and the web UI are phase 2.

## Steps

1. `libs/core/kiln_ai/datamodel/datamodel_enums.py`: add `opencode = "opencode"` to `ModelProviderName` after `typesafe`.

2. `libs/core/kiln_ai/utils/config.py`: add next to `typesafe_api_key`:
   ```python
   "opencode_api_key": ConfigProperty(str, env_var="OPENCODE_API_KEY", sensitive=True),
   ```

3. `libs/core/kiln_ai/utils/litellm.py`: in `get_litellm_provider_info`, add `case ModelProviderName.opencode: is_custom = True` so the model ID becomes `openai/<model_id>`.

4. `libs/core/kiln_ai/adapters/provider_tools.py`:
   - `OPENCODE_API_BASE = "https://opencode.ai/inference/openai/v1"`.
   - `provider_warnings[ModelProviderName.opencode]` with `required_config_keys=["opencode_api_key"]` and the message "Attempted to use OpenCode without an API key set. \nGet a pay-as-you-go API key from https://opencode.ai/console (OpenCode Go subscriptions aren't supported)."
   - `LiteLlmCoreConfig.cost_from_response_usage: bool = False`.
   - `lite_llm_core_config_for_provider` case:
     ```python
     case ModelProviderName.opencode:
         return LiteLlmCoreConfig(
             base_url=OPENCODE_API_BASE,
             additional_body_options={"api_key": Config.shared().opencode_api_key},
             cost_from_response_usage=True,
         )
     ```
     This adds a `Config.shared()` read in `kiln_ai/`, matching every other case (H24, reported in the summary).

5. `libs/core/kiln_ai/adapters/model_adapters/litellm_config.py`: add `cost_from_response_usage: bool = False` to `LiteLlmConfig`. `adapter_registry.py::litellm_core_provider_config` copies it from the core config.

6. `libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py::usage_from_response`:
   - When `self.config.cost_from_response_usage`, the cost is `usage.cost` only (ignoring `_hidden_params["response_cost"]`), accepted only if it's a finite, non-negative `int` or `float` (not `bool`), stored as `float`. Anything else is no cost.
   - Otherwise the existing precedence is unchanged.

7. `libs/core/kiln_ai/adapters/ml_provider_list.py`: `KilnProviderInfo` for `opencode` after TypeSafe with `friendly_name="OpenCode"`, `models_dev_id="opencode"`, the three notes from the architecture doc (`Routing:`, `Data retention:`, `Gotchas:`), `tags=[]`.

8. `app/desktop/studio_server/provider_api.py`: only if `ty check` flags the exhaustive `match` statements in `connect_api_key` / `disconnect_api_key` as non-exhaustive once the enum member exists. In that case the connect and disconnect cases are phase 2 work; no stub is added here and the failure is reported.

## Tests

New `libs/core/kiln_ai/adapters/model_adapters/test_opencode_litellm.py` (respx, `litellm.disable_aiohttp_transport = True`, real `adapter_for_task`):

- `test_opencode_request_wiring`: posts to `https://opencode.ai/inference/openai/v1/chat/completions` with `Authorization: Bearer <key>` and the model ID unchanged in the body.
- `test_opencode_cost_from_usage_cost` (parametrized non-streaming / streaming): `run.usage.cost` equals the body's `usage.cost`.
- `test_opencode_cost_ignores_litellm_response_cost`: a `gpt-*` model ID that LiteLLM prices itself still records `usage.cost`.
- `test_opencode_missing_usage_cost_records_no_cost` (non-streaming / streaming): no `usage.cost` gives `run.usage.cost is None`.
- `test_opencode_int_zero_cost_recorded_as_float`: `usage.cost == 0` gives `0.0`.
- `test_opencode_error_text_kept` (parametrized over the 402, 403, 410, 400 and free-model 429 bodies, × non-streaming / streaming): the kept exception (`KilnRunError.original` / the raised stream exception) has OpenCode's `error.message` in `str()` and the right `status_code`.
- `test_opencode_auth_error_is_batch_fatal`: 401 stays a `litellm.AuthenticationError` and batch-fatal.
- `test_opencode_rate_limit_is_retryable`: a plain 429 stays a retryable, non-batch-fatal `litellm.RateLimitError`.

Extended existing tests:

- `test_litellm_adapter.py`: `opencode` → `openai` prefix in `test_litellm_model_id_standard_providers`; unit tests for `usage_from_response` with `cost_from_response_usage=True` (ignores `response_cost`, accepts `int`/`float`, rejects negative, NaN, inf, `bool`, strings, missing).
- `test_provider_tools.py`: friendly name "OpenCode"; `lite_llm_core_config_for_provider(opencode)` returns the base URL, key and `cost_from_response_usage=True`; missing-key warning text.
- `utils/test_litellm.py`: `opencode` maps to `openai`, custom.
- `test_adapter_registry.py`: OpenCode adapter has the base URL, key and `cost_from_response_usage=True`.
- `utils/test_config.py`: `opencode_api_key` env var and sensitivity.
- `test_ml_provider_list.py`: `opencode` in the `models_dev_ids` expected dict.
