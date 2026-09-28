---
status: draft
---

# Architecture: Cloudflare Provider

Built on the [functional spec](./functional_spec.md), the [approved strings](./ui_design.md) and the [live test findings](./live_test_findings.md). This is a small project, so everything fits in this one doc; there are no component docs.

## Summary

Cloudflare is a new `ModelProviderName` that runs through Kiln's existing LiteLLM adapter using the generic `openai/` route (the SiliconFlow pattern). The only new behavior is:

1. A base URL built from the account ID.
2. An optional `cf-aig-gateway-id` header.
3. A two-step connect check.

Everything else, including rate-limit handling, reuses existing code unchanged. The live tests show LiteLLM already maps Cloudflare's errors the way Kiln needs.

```mermaid
flowchart LR
  UI[connect_providers.svelte] -->|POST connect_api_key| API[provider_api.connect_cloudflare]
  API -->|1. GET models/search| CF[(api.cloudflare.com)]
  API -->|2. if gateway: POST chat, fake model| CF
  API -->|save| CFG[Config: key, account, gateway]
  RUN[LiteLlmAdapter] --> CORE[lite_llm_core_config_for_provider]
  CORE -->|reads| CFG
  RUN -->|openai/@cf/... + api_base + headers| CF
```

## Decisions From Live Testing

| Open question (functional spec) | Answer | Design consequence |
|---|---|---|
| Does the response report which model ran? | **No.** A successful call to the aliased `@cf/moonshotai/kimi-k2.5` returns `"model": "@cf/moonshotai/kimi-k2.5"`, even though K2.6 runs. No header carries it either. | **The optional runtime no-substitution check is not built.** The process safeguard in the maintenance skills is the only protection. |
| Cheapest way to validate a gateway ID | A chat completion for a model ID that doesn't exist, with the gateway header. It returns 400 / 2001 if the gateway is missing, and 400 / 5007 ("No such model") if the gateway is fine. No model runs, so it's free. | Step 2 of the connect check. |
| Token permissions for a gateway | None beyond Workers AI. Confirmed by the account owner: the test token has no AI Gateway permission and works with the `default` gateway. | No permission text in the UI (already removed). |
| Is the gateway header optional? | Yes. | The header is sent only when a gateway ID is set. |
| Truncation with no `max_tokens` | None on all 10 included models: complete 700-number outputs of 1,500–5,800 tokens, `finish_reason: stop`. | **Kiln sends no `max_tokens` for this provider.** No provider-specific code. |
| Qwen 3.8 on `/v1` | Works. It's slow (about 23 tokens/s), and long non-streaming outputs hit Cloudflare's timeout (408 / 3046 after 121 s). | Kept, per the product decision. See [Timeouts](#timeouts). |
| Rate-limit error shape | HTTP 429, code 3021, both direct and through a gateway. LiteLLM raises `litellm.RateLimitError`: `is_retryable_error=True`, `is_batch_fatal_error=False`. | No code change. Unit tests pin it (see [Testing](#testing-strategy)). |

## Data Model and Config

### Enum

`libs/core/kiln_ai/datamodel/datamodel_enums.py`, `ModelProviderName`: add `cloudflare = "cloudflare"`. Place it after `featherless_ai`. Order matters only for readability.

### Config properties

`libs/core/kiln_ai/utils/config.py`, next to the Fireworks entries:

```python
"cloudflare_api_key": ConfigProperty(
    str,
    env_var="CLOUDFLARE_API_KEY",
    sensitive=True,
),
"cloudflare_account_id": ConfigProperty(
    str,
    env_var="CLOUDFLARE_ACCOUNT_ID",
),
"cloudflare_ai_gateway_id": ConfigProperty(
    str,
    env_var="CLOUDFLARE_AI_GATEWAY_ID",
),
```

- The config key is `cloudflare_api_key`, not `..._token`. That keeps it consistent with every other provider's `*_api_key` key and with the env var LiteLLM and models.dev use. Only the UI label says "API Token".
- The account ID and gateway ID aren't secrets, the same as `fireworks_account_id`.
- An empty gateway ID is stored as `None`, never as `""`.

## Component Changes

### 1. Provider identity and warnings (`libs/core/kiln_ai/adapters/provider_tools.py`)

- `provider_name_from_id`: `case ModelProviderName.cloudflare: return "Cloudflare"`.
- `provider_warnings`:

  ```python
  ModelProviderName.cloudflare: ModelProviderWarning(
      required_config_keys=["cloudflare_api_key", "cloudflare_account_id"],
      message="Attempted to use Cloudflare without an API token and account ID set. \nCreate a token and find your account ID at https://dash.cloudflare.com/?to=/:account/ai/workers-ai",
  ),
  ```

  The gateway ID is **not** listed in `required_config_keys`. It's optional, and this list decides whether the provider counts as connected (`provider_enabled`, `get_available_models`, `get_available_providers`).

### 2. LiteLLM wiring

`libs/core/kiln_ai/utils/litellm.py`, `get_litellm_provider_info`: add `case ModelProviderName.cloudflare: is_custom = True`, next to `siliconflow_cn`. This yields the `openai/@cf/<author>/<model>` model ID and requires a base URL. `litellm_adapter.py` already raises if a custom provider has no `api_base`.

`provider_tools.py`, `lite_llm_core_config_for_provider`: add a case that calls a new module-level helper. Keeping the logic in a helper keeps the `match` short and makes it testable on its own:

```python
CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_GATEWAY_HEADER = "cf-aig-gateway-id"

def cloudflare_base_url(account_id: str) -> str:
    return f"{CLOUDFLARE_API_BASE}/accounts/{account_id}/ai/v1"

def cloudflare_headers(gateway_id: str | None) -> Dict[str, str] | None:
    return {CLOUDFLARE_GATEWAY_HEADER: gateway_id} if gateway_id else None

def _cloudflare_core_config() -> LiteLlmCoreConfig:
    account_id = Config.shared().cloudflare_account_id
    if not account_id:
        raise ValueError(provider_warnings[ModelProviderName.cloudflare].message)
    return LiteLlmCoreConfig(
        base_url=cloudflare_base_url(account_id),
        default_headers=cloudflare_headers(Config.shared().cloudflare_ai_gateway_id),
        additional_body_options={"api_key": Config.shared().cloudflare_api_key},
    )
```

- `connect_cloudflare` reuses `cloudflare_base_url` and `cloudflare_headers`, so the connect check and inference build URLs and headers the same way.
- There's no `os.getenv(...BASE_URL)` override, unlike SiliconFlow and OpenRouter. The URL depends on the account, and nothing needs to override it.
- No `HTTP-Referer` / `X-Title` headers. Cloudflare doesn't use them.
- The header travels through the existing path: `adapter_registry.litellm_core_provider_config` → `LiteLlmConfig.default_headers` → `LiteLlmAdapter._headers` → `headers=` in `build_completion_kwargs`. No changes there.
- Embeddings, extractors and rerankers also call `lite_llm_core_config_for_provider`, but only for providers that have models of that type. Cloudflare has none, so those paths are untouched.

### 3. Connect and disconnect (`app/desktop/studio_server/provider_api.py`)

**Dispatch.** In `connect_api_key`, add `case ModelProviderName.cloudflare: return await connect_cloudflare(key_data)`. The whole dict is passed, like Fireworks.

**`connect_cloudflare(key_data: dict)`**, a new module-level async function:

Field keys are the UI labels, since the label is the payload key:

```python
CLOUDFLARE_TOKEN_FIELD = "API Token"
CLOUDFLARE_ACCOUNT_FIELD = "Account ID"
CLOUDFLARE_GATEWAY_FIELD = "AI Gateway ID - Optional"
CLOUDFLARE_CONNECTION_CHECK_MODEL = "@cf/kiln/connection-check"
```

Algorithm:

1. Read the fields. Strip whitespace from all three.
   - If the token or account ID is missing or empty, return 400 `Failed to connect to Cloudflare. API Token and Account ID are required.`.
   - If the gateway field is empty, treat it as `None`.
2. **Local format check.** If the account ID doesn't match `^[0-9a-fA-F]{32}$`, return 400 with the approved "Invalid Account ID." message. No network call.
3. **Token and account check.** `GET {CLOUDFLARE_API_BASE}/accounts/{account_id}/ai/models/search?search=kiln-connection-check` with a Bearer token and `timeout=30`.
   - The `search` value matches no model, so the response is about 120 bytes instead of about 100 KB. It's free and checks the same token, account and Workers AI permission as inference. (`per_page` is ignored by Cloudflare.)
   - 200 → continue.
   - 404 → the "Invalid Account ID." message.
   - 400, 401 or 403 → the approved token message: `...Invalid API Token, or the token doesn't have Workers AI access for this Account ID.` Live, a junk token gives 400 / 9106, a bad token 401, and a well-formed account the token can't use 403.
   - Anything else → `Failed to connect to Cloudflare. Error: [<status>] <text>`.
4. **Gateway check**, only if a gateway ID was given. `POST {cloudflare_base_url(account_id)}/chat/completions` with `headers=cloudflare_headers(gateway_id)` plus auth, body `{"model": CLOUDFLARE_CONNECTION_CHECK_MODEL, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}`, and `timeout=30`.
   - Parse `errors[].code` from the JSON body, if any.
   - Code 5007 (No such model) → the gateway is fine; continue.
   - Code 2001 → return 400 with the approved message: `Failed to connect to Cloudflare. AI Gateway '<id>' not found. Check the gateway ID, or remove it.`
   - A 200 (someone deployed a model with that ID) → treat it as success.
   - Anything else → the generic `Error: [<status>] <text>` message.
5. On success, set `cloudflare_api_key`, `cloudflare_account_id` and `cloudflare_ai_gateway_id` (`None` if not given). Return 200 `Connected to Cloudflare`. **Nothing is saved before every check passes.**
6. Wrap the body in `try/except Exception` and return 400 `Failed to connect to Cloudflare. Error: {e!s}`, as `connect_fireworks` does.

Error-status mapping for the returned `JSONResponse`: 401 for invalid-credential cases, 400 otherwise, matching Fireworks and SiliconFlow.

Parse the error code with a small helper, `_cloudflare_error_codes(response) -> set[int]`. It returns an empty set on non-JSON bodies. Use `requests`, like the neighboring connect functions, with an explicit `timeout`.

**Disconnect.** In `disconnect_api_key`, add a `cloudflare` case that sets all three config values to `None`.

**Reconnecting.** Connecting again with an empty gateway field clears a previously saved gateway ID (step 5 writes `None`). That's the documented way to remove a gateway without disconnecting.

### 4. Web UI

- `app/web_ui/static/images/cloudflare.svg`: from `assets/cloudflare.svg` in this spec folder.
  - Remove the XML declaration, the SVG Repo comment, `<title>`, `width` and `height`.
  - Set `fill="currentColor"`.
  - Crop the `viewBox` to the artwork's bounding box, per the maintain-models skill's icon rules. Compute it from the path, for example by rendering it with Playwright's `getBBox()`; don't guess.
- `src/lib/ui/provider_image.ts`: `cloudflare: "/images/cloudflare.svg"`.
- `src/lib/stores.ts`, `provider_name_map`: `cloudflare: "Cloudflare"`.
- `connect_providers.svelte`:
  - Add a provider entry after Featherless AI, with every string exactly as in [ui_design.md](./ui_design.md). That's `name`, `description`, `featured: false`, `api_key_steps` (5), `api_key_fields: ["API Token", "Account ID", "AI Gateway ID - Optional"]`, `optional_fields: ["AI Gateway ID - Optional"]` and `api_key_warning`.
  - Add a `status.cloudflare` entry.
  - In `check_existing_providers`: `if (data["cloudflare_api_key"] && data["cloudflare_account_id"]) status.cloudflare.connected = true`.
- `src/lib/api_schema.d.ts`: regenerate with `app/web_ui/src/lib/generate_schema.sh`. Don't hand-edit it.
- Don't touch the generated Copilot client (`api_client/kiln_ai_server_client/...`); the maintain-models skill documents it as a known gap.

### 5. Model list (PR 2 only)

In `libs/core/kiln_ai/adapters/ml_model_list.py`, add a `KilnModelProvider(name=ModelProviderName.cloudflare, model_id="@cf/...")` entry to each of the 10 models in the functional spec's initial list.

Per-model flags (`structured_output_mode`, `supports_function_calling`, `supports_vision`, `reasoning_capable`, `parser`, and so on) are set by running the maintain-models skill's per-model tests, not copied from Cloudflare's metadata.

Starting points, all to be confirmed by those tests:

- All 10 return reasoning in `reasoning` / `reasoning_content`, and LiteLLM already reads it.
- Kiln's default for an unknown provider is tool-call structured output, so entries should set `structured_output_mode` explicitly once tested.

Also add a Cloudflare model to `pytest_prerelease_whitelist.py` `PRERELEASE_CHAT_MODELS`. GLM 4.7 Flash is the suggestion: it runs on the free plan and is fast.

### 6. Skills and scripts (PR 2)

- `.agents/scripts/provider_utils.py`: add `"cloudflare": {"type": "cloudflare", "env": "CLOUDFLARE_API_KEY", "account_env": "CLOUDFLARE_ACCOUNT_ID"}` and a fetch function.
  - It calls `models/search?task=Text%20Generation&include_deprecated=true` when both env vars are set.
  - Otherwise it falls back to the public `https://ai-cloudflare-com.pages.dev/api/models`.
  - It returns model IDs with any `planned_deprecation_date`, so the deprecation check can flag them.
- `.agents/skills/kiln-check-deprecation/scripts/check_provider.py`: add the `cloudflare` branch. Update its quirks docstring, and the skill's supported-providers table and quirks list.
- `.agents/skills/claude-maintain-models/SKILL.md`: add the Cloudflare section from the functional spec (sources, cross-check, the "never LiteLLM" rule, the inclusion rule and how to tell OpenAI-format models from older ones, deprecations, lagging providers). Start from the draft in `research/.../recommended-maintenance-procedure.md`.
  - Add a **No Model Substitution** note: Cloudflare can silently alias a retired ID to another model, and responses don't reveal it. So remove entries **before** their `planned_deprecation_date`.
- `.agents/skills/kiln-prerelease-check/SKILL.md`: add `CLOUDFLARE_API_KEY` and `CLOUDFLARE_ACCOUNT_ID` to its env var list.

## Error Handling

- **Connect:** fully handled in `connect_cloudflare`, as above. Kiln never saves a configuration that failed a check.
- **Inference:** no Cloudflare-specific handling. Observed LiteLLM mappings:

| Cloudflare | LiteLLM exception | Retry | Batch-fatal |
|---|---|---|---|
| 429 / 3021 rate limit (direct and gateway) | `RateLimitError` | Yes | No |
| 401 / 10000 bad token or account | `AuthenticationError` | No | Yes |
| 403 / 5035 paid model on free plan | `APIError` | No | No |
| 410 / 5028 deprecated model | `APIError` | No | No |
| 400 / 5007 unknown model | `BadRequestError` | No | No |
| 400 / 2001 gateway deleted after connect | `BadRequestError` | No | No |

  The 403 and 410 cases aren't batch-fatal, so a batch fails case by case instead of aborting early. That's Kiln's existing conservative default for unrecognized errors, and changing it is out of scope.
- **Logging:** none added. Connect failures return their message to the UI, like other providers.

### Timeouts

Kiln sets no LiteLLM timeout (the default is about 600 s), so Cloudflare's own server-side timeout is what a slow model hits.

- Live: a long non-streaming Qwen 3.8 request failed after **121 s** with **HTTP 408, code 3046**.
- LiteLLM raises `litellm.Timeout`, so `is_retryable_error` is true and `is_batch_fatal_error` is false.
- A batch job retries it, and a request that timed out because the output is too long will usually time out again. Kiln's retry counts are small (2–3), so the worst case is a few extra two-minute attempts on one case.
- That's accepted. It's the same treatment as any provider's timeout, and a Cloudflare-specific exception isn't worth the special case. No change is planned.

## Testing Strategy

All tests use pytest, following the neighboring tests. No live calls in unit tests.

**Core (`libs/core`)**

- `test_config.py`: the three properties exist, and the env var and sensitivity flags are correct (`test_typesafe_api_key_property` pattern).
- `test_provider_tools.py`:
  - `provider_name_from_id` returns "Cloudflare" (add it to the parametrized test).
  - `provider_warnings` requires the key and account, but not the gateway.
  - `provider_enabled` is true with the key and account, and false when either is missing.
  - `cloudflare_base_url` builds the URL. `cloudflare_headers(None)` and `("")` return `None`; `("gw")` returns the header dict.
  - `lite_llm_core_config_for_provider(cloudflare)`: the full config without a gateway, the full config with a gateway, and a `ValueError` when the account ID is missing.
- `test_litellm_adapter.py`: add `(ModelProviderName.cloudflare, "openai")` to `test_litellm_model_id_standard_providers`. Check that `get_litellm_provider_info` returns `is_custom=True` and `openai/@cf/zai-org/glm-5.3`.
- `test_adapter_registry.py`: a `test_cloudflare_adapter_creation` modeled on the SiliconFlow test. It asserts `base_url`, `default_headers` (with and without a gateway) and `api_key`.
- **New wiring and rate-limit test** (`test_cloudflare_litellm.py` next to `test_litellm_adapter.py`). It uses `respx` to mock `https://api.cloudflare.com/client/v4/accounts/<acct>/ai/v1/chat/completions`, and builds a real `LiteLlmAdapter` for a Cloudflare model with config mocked. Three tests:
  1. With the gateway set, the outgoing request carries `cf-aig-gateway-id` and `Authorization: Bearer <key>`, and the body's `model` is `@cf/...` with no `openai/` prefix.
  2. A mocked 429 with the recorded 3021 body produces an exception where `unwrap_kiln_run_error(e)` is a `litellm.RateLimitError`, `is_retryable_error` is true, and `is_batch_fatal_error` is false. Run it with and without a gateway.
  3. A mocked 401 / 10000 becomes `AuthenticationError` and is batch-fatal.

  Use the recorded bodies from `live_test_findings.md` verbatim.

  LiteLLM sends through aiohttp by default, which `respx` can't intercept. The tests must `monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)`. Verified: with that set, `respx` captures the request, including the gateway header and the unprefixed `@cf/...` model, and a mocked 429 becomes `RateLimitError`.

**Server (`app/desktop`)** — `test_provider_api.py`, with `requests` mocked as in the Fireworks and SiliconFlow tests:

- Dispatch: `connect_api_key` routes `cloudflare` to `connect_cloudflare` with the full dict.
- Missing token, and missing account ID → 400, nothing saved.
- A malformed account ID → "Invalid Account ID.", with no HTTP call made.
- Search returns 404 → Invalid Account ID; 400, 401 or 403 → the token message; 500 → the generic message. Nothing saved in any of these.
- Search returns 200 with no gateway → saves the key and account, gateway `None`, and no chat call is made.
- Gateway given, chat returns 400 / 5007 → saves all three. The request carries the gateway header, the fake model and `max_tokens: 1`.
- Gateway given, chat returns 400 / 2001 → the gateway message, nothing saved.
- Gateway given, chat returns 200 → success. Chat returns a non-JSON 502 → the generic message.
- Whitespace-only gateway → treated as absent.
- Reconnect without a gateway clears the saved one.
- A request exception → 400 with the error text.
- Disconnect clears all three fields.
- Add `cloudflare` to the invalid-payload parametrize list and to `mock_config_all_providers`.

**Web (`app/web_ui`)** — `connect_providers.test.ts`: the Cloudflare card renders the three fields, with the gateway field optional, and connected status is derived from `cloudflare_api_key` and `cloudflare_account_id` (typesafe test pattern).

**Model entries (PR 2)** — the existing parametrized per-model tests run against every new `ml_model_list.py` entry. They need `CLOUDFLARE_API_KEY` and `CLOUDFLARE_ACCOUNT_ID` in the environment (the current dev container exposes `CF_AI_TOKEN` and `CF_ACCOUNT_ID`; map them when running).

## Release Split

- **PR 1:** sections 1–4 plus their tests.
- **PR 2**, after a client release that includes PR 1: sections 5–6.
