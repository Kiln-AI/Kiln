---
status: draft
---

# Architecture: OpenCode Provider

Implements [functional_spec.md](./functional_spec.md). This is a small project, so it has a single architecture doc and no component docs.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Call path | Kiln's generic OpenAI-compatible path. The model ID becomes `openai/<id>` with a fixed `api_base`, like `siliconflow_cn`. | This was the user's choice. LiteLLM's `opencode_go/` provider covers only the Go plan, needs LiteLLM 1.110 or later (Kiln pins `>=1.105.7,<1.106`), and picks each model's native API, which is the opposite of Chat Completions-only. See [LiteLLM's OpenCode support](#litellms-opencode-support). |
| Cost | Always read `usage.cost` from the response. Ignore LiteLLM's `response_cost`. | LiteLLM fills in `response_cost` from its own price list for model names it knows (`gpt-5.4-nano`, `gpt-5.4-mini`), so the current precedence (`response_cost` first) would use the wrong source. |
| Session header | Not sent. Out of scope. | Session affinity is a cross-provider problem, handled separately for all providers. The caching data below is kept for that work. |
| Errors | No OpenCode-specific mapping. Add one generic rule for HTTP 402 (any provider) to `format_error_message` and `is_batch_fatal_error`. | The [error probe](#error-probe) shows OpenCode's messages are clear and LiteLLM keeps them. The one real gap is out-of-credits, which Kiln shows as "An unexpected error occurred." and doesn't treat as fatal. |
| Connect check | `GET https://opencode.ai/inference/v1/models` with the key. | It's free. The user confirmed that a bad key gets 401. |

## Live Findings (Nov 22, 2026)

These were recorded with a real Console key, through the environment's network proxy.

| Probe | Result |
|---|---|
| Chat Completions, `json_schema` response format | Works on `claude-haiku-5-5`, `gpt-5.4-nano`, `gemini-3.5-flash-lite` and `kimi-k3`. |
| Tool calls with `tool_choice: required` | Work on all four models. |
| `reasoning_effort: high` | Claude and Kimi return `reasoning_content`. GPT and Gemini report reasoning tokens. |
| Image (PNG data URL) | Works on all four models. |
| PDF (`file` part) | Works on Claude, GPT and Gemini. Kimi returns 400 (an upstream deserialize error). |
| GPT with `max_tokens` < 16 | 400 from upstream (`max_output_tokens` must be ≥ 16). |
| Streaming with `stream_options.include_usage` | The final chunk carries `usage.cost` and `usage.opencode`. Without `include_usage` there's no usage. Kiln's `StreamingCompletion` already forces it on. |
| LiteLLM 1.105.7, `openai/` path, non-streaming | `usage.cost` survives on `response.usage`. `_hidden_params["response_cost"]` is `None` for unknown names (`claude-*`, `glm-*`, `kimi-*`), but it's filled in from LiteLLM's price list for known OpenAI names. |
| LiteLLM 1.105.7, streaming | `stream_chunk_builder` carries `usage.cost` into both `usage.cost` and `response_cost`. |
| Free model (`big-pickle`) | 429 `{"type":"error","error":{"type":"FreeUsageLimitError","message":"Free usage limit reached. Free models work in OpenCode…"}}` |
| Retired model (`glm-5.2`) | 410 `{"type":"error","error":{"type":"ModelDeprecated","message":"Model glm-5.2 has been deprecated. Use glm-5.3 instead."},"metadata":{"model":"glm-5.2","replacement":"glm-5.3"}}` |
| Model disabled in the workspace (`claude-opus-5`) | 403 `{"error":{"type":"permission_error","message":"Model access is disabled. Change model access at https://opencode.ai/console/<org>/models."}}` |
| Unknown model | 400 `{"error":{"type":"server_error","message":"Upstream request failed: Model is unavailable."}}` |
| Out of credits | Not testable here. The billing docs say: "Paid requests fail with HTTP 402 once the balance reaches zero… `Upstream request failed: Insufficient account funds`." |
| Invalid key | 401, confirmed by the user from outside this environment. The proxy here overwrites `Authorization`. |
| `/inference/v1/models` with a key | 200, with 66 entries. It lists only the models the key's workspace allows, so the 403 above is for a model missing from this list. |
| User agents | `Python-urllib` is blocked by Cloudflare (error 1010). `OpenAI/Python` (what LiteLLM sends), `python-httpx` and `python-requests` all get 200. |

### Prompt caching and `x-opencode-session` (for the separate session-affinity work)

The test used an 11k-token system prompt. Each turn added the previous assistant reply plus a new user message, and calls were 3 s apart.

| Model | No header | With header |
|---|---|---|
| `claude-haiku-5-5` | No caching on any turn (about $0.00113 per turn) | Turn 0 writes 11,244 tokens ($0.00141, +25%). Turns 1 and 2 read 11,244+ tokens ($0.000118, about −90%). |
| `gpt-5.4-nano`, `kimi-k3` | Automatic prefix caching (8–9k tokens cached from the second call) | Same as without the header. |

A second test kept the system prompt fixed and sent a different single user message on each call, with the header. Every call wrote the cache and none read it. OpenCode puts the cache breakpoint at the end of the prompt, so the header helps only calls that extend an earlier prompt. On single-call Claude runs it adds a 25% cache-write charge for nothing.

### Error probe

These are real OpenCode errors run through LiteLLM 1.105.7 and Kiln's `format_error_message`, with streaming and non-streaming behaving the same:

| Case | LiteLLM exception and `str(e)` | Kiln message today | Retryable / batch-fatal |
|---|---|---|---|
| Free model, 429 | `RateLimitError`: "…Free usage limit reached. Free models work in OpenCode…" | "Rate limit exceeded. Wait a moment and try again." | yes / no |
| Retired, 410 | `APIError`: "…Model glm-5.2 has been deprecated. Use glm-5.3 instead." | "An unexpected error occurred." | no / no |
| Disabled for the workspace, 403 | `APIError`: "…Model access is disabled. Change model access at https://opencode.ai/console/…/models." | "An unexpected error occurred." | no / no |
| Unknown model, 400 | `BadRequestError`: "…Upstream request failed: Model is unavailable." | "An unexpected error occurred." | no / no |
| Out of credits, 402 | Not testable live. LiteLLM's mapping sends 402 to `APIError(status_code=402)`. | "An unexpected error occurred." | no / no |

OpenCode's text is good. Kiln's generic fallback hides it, which is a deliberate cross-provider policy against leaking provider internals. This project doesn't change that. The 403, 410 and 400 cases can only happen with custom model IDs or admin changes, because Kiln lists only default-enabled, current models. That leaves out-of-credits as the one case worth handling, and it isn't specific to OpenCode.

### LiteLLM's OpenCode support

- 1.110.2 (Nov 20, 2026) adds `opencode_go/`. It covers the Go base URL only, picks each model's native API from a 30-model Go price list, and reads `usage.opencode.list_cost`.
- It also detects an OpenCode `api_base` on other providers so that it can send `x-opencode-session`.
- Nothing in it targets the pay-as-you-go endpoint, and Kiln's pinned 1.105.7 has none of this.
- 1.105.7 does have a generic `provider_affinity_header` kwarg. This design uses a plain header instead (see [Session Header](#session-header)), so it depends on no LiteLLM version.

## Release Split

- **PR 1, provider support:** every section below except [Model Catalog](#model-catalog-pr-2).
- **PR 2, model catalog and skills:** [Model Catalog](#model-catalog-pr-2). It merges only after a client release that includes PR 1.

## Provider Plumbing (PR 1)

### `libs/core`

- **`datamodel/datamodel_enums.py`:** add `opencode = "opencode"` after `typesafe`.
- **`utils/config.py`:** add `"opencode_api_key": ConfigProperty(str, env_var="OPENCODE_API_KEY", sensitive=True)` next to `typesafe_api_key`.
- **`utils/litellm.py`:** add `case ModelProviderName.opencode: is_custom = True`, like `siliconflow_cn`. The model ID becomes `openai/<model_id>`.
- **`adapters/provider_tools.py`:**
  - Add the constant `OPENCODE_API_BASE = "https://opencode.ai/inference/openai/v1"`.
  - Add a `provider_warnings` entry: `required_config_keys=["opencode_api_key"]`, with the message "Attempted to use OpenCode without an API key set. \nGet a pay-as-you-go API key from https://opencode.ai/console (OpenCode Go subscriptions aren't supported)."
  - Add a `LiteLlmCoreConfig` field: `cost_from_response_usage: bool = False`.
  - Add a case to `lite_llm_core_config_for_provider`:
    ```python
    case ModelProviderName.opencode:
        return LiteLlmCoreConfig(
            base_url=OPENCODE_API_BASE,
            additional_body_options={"api_key": Config.shared().opencode_api_key},
            cost_from_response_usage=True,
        )
    ```
    It has no `default_headers`. OpenCode needs no attribution headers.
- **`adapters/model_adapters/litellm_config.py` and `adapter_registry.py`:** add the new field to `LiteLlmConfig` and copy it in `litellm_core_provider_config`.
- **`adapters/ml_provider_list.py`:** add a `KilnProviderInfo` after TypeSafe, with:
  - `id=ModelProviderName.opencode`
  - `friendly_name="OpenCode"`
  - `models_dev_id="opencode"`
  - `notes`, using the allowed labels:
    - "Routing: An AI gateway; each model runs on its lab's own API (OpenAI, Anthropic, Google, xAI) or a vetted host, and Kiln calls all of them through OpenCode's Chat Completions translation."
    - "Data retention: OpenCode's hosts don't retain data by default, but the OpenAI, Anthropic and xAI APIs keep requests 30 days and Google up to 55 days."
    - "Gotchas: Pay-as-you-go credits only; OpenCode Go subscriptions and OpenCode's free models aren't supported."
  - `tags=[]`
  - Then update the expected dict in `test_ml_provider_list.py::test_models_dev_ids`.

### Cost from `usage.cost`

Changes in `LiteLlmAdapter.usage_from_response` (`litellm_adapter.py:975`):

```python
if self.config.cost_from_response_usage:
    reported = litellm_usage.get("cost") if litellm_usage else None
    cost = reported if isinstance(reported, (int, float)) and math.isfinite(reported) and reported >= 0 else None
else:
    ...existing response_cost-then-usage.cost logic, unchanged...
```

- Store `int` costs as `float`. The existing `isinstance(cost, float)` guard would drop an `int`, such as a `0` from a fully cached call.
- This one function covers both paths. The non-streaming tool loop calls it per call, and `AdapterStream` calls it on the response `stream_chunk_builder` builds, which carries `usage.cost` (verified).
- No `extra_body` opt-in is needed. OpenCode always sends `usage.cost`, unlike OpenRouter's `usage.include`.

### Generic 402 rule (`adapters/errors.py`, `adapters/retry_classification.py`)

- **`format_error_message`:** add a branch after the 5xx bucket and before `JSONSchemaValidationError`: `isinstance(exc, litellm.APIError) and getattr(exc, "status_code", None) == 402`. It returns "The model provider declined the request because the account is out of credits. Add credits with the provider and try again."
- **`is_batch_fatal_error`:** also true for an `APIError` with `status_code == 402`, after `unwrap_kiln_run_error`. Every remaining row of a batch would fail the same way, so the run stops early.
- **`is_retryable_error`:** no change. `APIError` isn't in its retryable set.
- **Not OpenCode-specific.** Any provider that returns 402 benefits. It matches on the status code, so it holds if a later LiteLLM maps 402 to an `APIError` subclass.

### Connect and disconnect

**`app/desktop/studio_server/provider_api.py`:**

- Add `async def connect_opencode(key: str) -> JSONResponse`, modelled on `connect_typesafe` (async `httpx`):
  - Sends `GET https://opencode.ai/inference/v1/models` with `Authorization: Bearer {key}`, a 10 s timeout and `follow_redirects=True`.
  - **200:** sets `Config.shared().opencode_api_key = key` and returns 200 `"Connected to OpenCode"`.
  - **401 or 403:** returns 401 `"Invalid OpenCode API key. Use a pay-as-you-go API key from OpenCode Console; OpenCode Go subscriptions aren't supported."`
  - **Any other status:** returns 400 `"Failed to connect to OpenCode. Error: [{status}]"`.
  - **`httpx.RequestError`:** returns 400 `"Couldn't reach OpenCode. Check your network connection and try again."`. A network failure never says the key is invalid.
- Add `case ModelProviderName.opencode: return await connect_opencode(parse_api_key(key_data))` in `connect_api_key`.
- Add `case ModelProviderName.opencode: Config.shared().opencode_api_key = None` in `disconnect_api_key`.

### Web UI

- **`src/lib/stores.ts`:** `opencode: "OpenCode"` in `provider_name_map`.
- **`src/lib/ui/provider_image.ts`:** `opencode: "/images/opencode.svg"`, plus `static/images/opencode.svg`.
  - The icon is a monochrome bare glyph using `currentColor`, with a cropped viewBox.
  - Copy it from [`assets/opencode.svg`](./assets/opencode.svg). That file is the user-supplied OpenCode mark converted to `currentColor`: the frame is solid, and the inner block has `fill-opacity="0.25"`, matching the brand's two-tone mark.
- **`connect_providers.svelte`:** a card with `name: "OpenCode"`, `id: "opencode"`, `featured: false` and `api_key_fields: ["API Key"]`. It uses the approved copy from the functional spec's [Connect Screen Copy](./functional_spec.md#connect-screen-copy): the description, the `api_key_warning` (the Go notice) and the three `api_key_steps`. Also add the status entry and the `opencode_api_key` connected check.
- Regenerate `api_schema.d.ts` with `generate_schema.sh`.

## Model Catalog (PR 2)

Follow `claude-maintain-models`, adding only provider entries to existing `KilnModel`s.

- **Source list:** `GET /inference/v1/models` with a key from a workspace whose model settings are untouched, filtered to `type: chat` with a non-zero price. This gives the models a new workspace enables by default.
  - Our workspace's list on Nov 22 had 34 such models (`claude-haiku-5-5`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-fable-5-2`, `gpt-5.4-mini`, `gemini-3.8-flash`, `kimi-k3`, `glm-5.3` and more).
  - The user confirms our workspace is still on default model settings before this list is used.
  - Remove anything on OpenCode's deprecated table.
  - Keep only models where Kiln already has a `KilnModel`, matching on `canonical_id` cross-checked with models.dev `opencode`.
  - Models outside the default set aren't listed. Users who turn them on add them as custom models.
- **Starting flags** for each entry, kept only if the paid tests pass:
  - `structured_output_mode=json_schema` (verified on four model families).
  - `supports_function_calling=True`.
  - `reasoning_capable` and `available_thinking_levels` copied from the model's native-provider entry. Thinking levels are sent as `reasoning_effort`, which OpenCode accepted on all four families.
  - Vision and MIME types copied from the native entry, with PDF removed wherever a test fails (Kimi's PDF already fails).
  - For OpenCode IDs that LiteLLM recognises as OpenAI models (`gpt-*`), LiteLLM applies that model's parameter rules. This is the same behaviour as on the `openai` provider, so it's fine. Use `litellm_allowed_openai_params` only if a test shows a needed parameter is dropped.
- **Tests and tooling lists:**
  - Add `opencode` to the provider list in `test_thinking_level_paid.py`.
  - Add a smoke test `test_opencode` in `test_prompt_adaptors.py`, like `test_cloudflare`.
  - Add one `PRERELEASE_CHAT_MODELS` entry.
  - Add `OPENCODE_API_KEY` to the prerelease skill's env list.
- **Skill updates** (`claude-maintain-models/SKILL.md` and `kiln-check-deprecation`):
  - Add an OpenCode Provider Quirks section covering the default-workspace models list as the source, the inclusion rule (exclude `type` other than `chat`, zero price and the `-free` suffix), that the list is filtered by workspace model settings (so the source workspace must keep default settings), and that thinking levels go through `reasoning_effort`.
  - Add OpenCode to the lagging-provider check.
  - Add the models endpoint to `.agents/scripts/provider_utils.py`.
  - Deprecation checks use OpenCode's deprecated table, and treat a 410 `ModelDeprecated` as proof. Add `opencode` to `extract_models.py` / `check_provider.py`.

## Testing Strategy

The unit tests use pytest. The wire tests follow `test_cloudflare_litellm.py`: they use respx and set `monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)`, so that LiteLLM's real request and exception mapping run against recorded OpenCode bodies.

**`test_opencode_litellm.py`** (new), the wire tests:

- **Request:** the request goes to `https://opencode.ai/inference/openai/v1/chat/completions` with `Authorization: Bearer <key>` and the model ID unchanged.
- **Cost:**
  - The cost is read from `usage.cost` on non-streaming and streaming runs.
  - A run with a known OpenAI model name still uses `usage.cost` when LiteLLM's `response_cost` differs (patch the price map, or use a `gpt-*` ID whose LiteLLM price is different).
  - When `usage.cost` is missing, the run has no cost.
  - An `int` cost of 0 is recorded as 0.0.
- **Errors:** a recorded 402 body gives an `APIError` with `status_code == 402`, the new message, and `is_batch_fatal_error` True. A 401 stays an `AuthenticationError`, and a plain 429 stays a retryable `RateLimitError`. These pin LiteLLM's mapping, so an upgrade that changes it shows up.

**Other new or extended tests:**

- `errors.py` and retry-classification tests: the 402 branch, including inside a `KilnRunError`. Other `APIError` statuses still get the generic message and aren't batch-fatal.
- Existing parametrized tests extended with `opencode`: `test_provider_tools.py` (friendly name, core config), `utils/test_litellm.py`, `test_litellm_adapter.py` (model ID prefix `openai`), `test_adapter_registry.py`, `utils/test_config.py` and `test_ml_provider_list.py`.
- `test_provider_api.py`: connect success, 401, 403, another status, a request exception, the dispatch through `connect_api_key`, and disconnect. Add `opencode` to the invalid-payload and all-providers fixtures.
- `connect_providers.test.ts`: OpenCode shows as connected when `opencode_api_key` is set.
- **Live (paid, PR 2):** the standard per-model suites with `OPENCODE_API_KEY=proxy-injected` in this environment. The proxy adds the real key.

## Open Items

1. **Default model settings:** the user confirms our OpenCode workspace's model settings are untouched, before PR 2 uses its models list as the source of default-enabled models.
