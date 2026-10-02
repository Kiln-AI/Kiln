---
status: complete
---

# Phase 1: Backend and Required Web Plumbing

## Overview

Add Cloudflare as a `ModelProviderName` that runs through the existing LiteLLM adapter on the generic `openai/` route, with a per-account base URL and an optional `cf-aig-gateway-id` header. Add the connect and disconnect endpoints with the two-step connect check (models search, then an optional gateway check). Add the web plumbing the new enum value forces (schema, name map, image map, logo). The connect card UI is phase 2.

## Steps

1. `libs/core/kiln_ai/datamodel/datamodel_enums.py`: add `cloudflare = "cloudflare"` after `featherless_ai`.
2. `libs/core/kiln_ai/utils/config.py`: add `cloudflare_api_key` (env `CLOUDFLARE_API_KEY`, sensitive), `cloudflare_account_id` (env `CLOUDFLARE_ACCOUNT_ID`) and `cloudflare_ai_gateway_id` (env `CLOUDFLARE_AI_GATEWAY_ID`) next to the Fireworks entries.
3. `libs/core/kiln_ai/utils/litellm.py`: `case ModelProviderName.cloudflare: is_custom = True`.
4. `libs/core/kiln_ai/adapters/provider_tools.py`:
   - `provider_name_from_id` returns `"Cloudflare"`.
   - `provider_warnings[cloudflare]` requires `cloudflare_api_key` and `cloudflare_account_id` only.
   - Module-level `CLOUDFLARE_API_BASE`, `CLOUDFLARE_GATEWAY_HEADER`, `cloudflare_base_url(account_id: str) -> str` (URL-encodes the account ID with `quote(..., safe='')`), `cloudflare_headers(gateway_id: str | None) -> Dict[str, str] | None`, and `_cloudflare_core_config() -> LiteLlmCoreConfig` (raises the provider warning message when the account ID is missing).
   - `lite_llm_core_config_for_provider`: `case ModelProviderName.cloudflare: return _cloudflare_core_config()`.
5. `app/desktop/studio_server/provider_api.py`:
   - Field-label constants, `CLOUDFLARE_CONNECTION_CHECK_MODEL = "@cf/kiln/connection-check"`, error codes 5007 and 2001, 30 s timeout.
   - Helpers: `_cloudflare_field` (strip, empty → `None`), `_cloudflare_error_codes(response) -> set[int]` (empty on non-JSON), and small error-response builders.
   - `connect_cloudflare(key_data: dict)`: required-field check; `GET .../ai/models/search?search=kiln-connection-check` (404 → Invalid Account ID; 400/401/403 → token message; other non-200 → generic); if a gateway ID is given, `POST .../ai/v1/chat/completions` with the gateway header and the fake model (2001 → gateway message; 5007 or 200 → OK; else generic); save all three fields only after every check passes (gateway `None` when absent); wrap in `try/except` → generic error.
   - Dispatch in `connect_api_key` with the full dict; disconnect clears all three fields.
6. Web plumbing:
   - Regenerate `app/web_ui/src/lib/api_schema.d.ts` with `generate_schema.sh`.
   - `stores.ts` `provider_name_map`: `cloudflare: "Cloudflare"`.
   - `provider_image.ts`: `cloudflare: "/images/cloudflare.svg"`.
   - `static/images/cloudflare.svg`: from the spec asset, with the XML declaration, comment, `<title>`, `width` and `height` removed, `fill="currentColor"`, and the `viewBox` cropped to the path's bounding box measured with Playwright `getBBox()`.

## Tests

- `test_config.py::test_cloudflare_properties`: the three properties exist with the right env vars and sensitivity.
- `test_provider_tools.py`:
  - `test_provider_name_from_id_parametrized`: Cloudflare case.
  - `test_cloudflare_provider_warning_requires_key_and_account_not_gateway`.
  - `test_provider_enabled_cloudflare`: true with key and account, false when either is missing.
  - `test_cloudflare_base_url`, `test_cloudflare_base_url_encodes_path_characters`, `test_cloudflare_headers` (None, "", "gw").
  - `test_lite_llm_core_config_for_provider_cloudflare`: full config with and without a gateway.
  - `test_lite_llm_core_config_for_provider_cloudflare_missing_account`: `ValueError` for `None` and `""`.
- `test_litellm.py`: Cloudflare in the provider mapping parametrize; `test_cloudflare_model_id_keeps_cf_prefix` gives `openai/@cf/zai-org/glm-5.3`.
- `test_litellm_adapter.py::test_litellm_model_id_standard_providers`: `(cloudflare, "openai")`.
- `test_adapter_registry.py::test_cloudflare_adapter_creation`: base URL, headers with and without a gateway, API key.
- `model_adapters/test_cloudflare_litellm.py` (respx, `litellm.disable_aiohttp_transport = True`):
  - Request through a gateway carries `cf-aig-gateway-id`, `Authorization: Bearer <key>`, and the unprefixed `@cf/...` model.
  - Request without a gateway has no gateway header.
  - 429 / 3021 → `litellm.RateLimitError` after unwrapping, retryable, not batch-fatal, "Rate limit exceeded" message; with and without a gateway.
  - 401 / 10000 → `AuthenticationError`, batch-fatal.
- `test_provider_api.py`:
  - Dispatch passes the full dict to `connect_cloudflare`.
  - Missing, whitespace-only or non-string token or account → 400, no calls, nothing saved.
  - Search 404 / 400 / 401 / 403 / 500 → the right message and status, no gateway call, nothing saved.
  - No gateway (absent, empty, whitespace) → saves stripped token and account, gateway `None` (clears a previous one), no chat call, exact search request.
  - Account ID is URL-encoded in the search URL.
  - Gateway with 400 / 5007 or 200 → saves all three; exact chat request.
  - Gateway 400 / 2001 → gateway message, nothing saved.
  - Gateway non-JSON 502, or an unexpected error code → generic message, nothing saved.
  - Request exception → 400 with the error text.
  - Disconnect clears all three fields.
  - `cloudflare` in the invalid-payload parametrize and `mock_config_all_providers`.
