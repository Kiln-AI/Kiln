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
| Session header | Send `x-opencode-session` only on runs that may make more than one model call. The ID is a hash of how the conversation starts. | Live tests: the header turns on Claude prompt caching, cutting later calls' cost by about 90%. It also adds a 25% cache-write charge to every call, so single-call runs would pay more for nothing. See [Session Header](#session-header). |
| Error mapping | A provider error hook on the adapter. For OpenCode it turns the account-level errors (402, 403 model disabled, 410, the free-model 429) into one new exception type, `ProviderActionRequiredError`. | These errors have no special handling in Kiln today. LiteLLM turns 402, 403 and 410 into a bare `APIError`, which shows the generic "unexpected error" message and is neither retried nor batch-fatal. |
| Connect check | `GET https://opencode.ai/inference/v1/models` with the key. | It's free. OpenCode documents 401 for revoked or expired keys. One check is still open, see [Open Items](#open-items). |

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
| Invalid key | Not testable here, because the proxy overwrites `Authorization`. The API docs say: "Revoked and expired keys stop working immediately and return HTTP 401." |
| `/inference/v1/models` with a key | 200, with 66 entries. It lists only the models the key's workspace allows, so the 403 above is for a model missing from this list. |
| User agents | `Python-urllib` is blocked by Cloudflare (error 1010). `OpenAI/Python` (what LiteLLM sends), `python-httpx` and `python-requests` all get 200. |

### Prompt caching and `x-opencode-session`

The test used an 11k-token system prompt. Each turn added the previous assistant reply plus a new user message, and calls were 3 s apart.

| Model | No header | With header |
|---|---|---|
| `claude-haiku-5-5` | No caching on any turn (about $0.00113 per turn) | Turn 0 writes 11,244 tokens ($0.00141, +25%). Turns 1 and 2 read 11,244+ tokens ($0.000118, about −90%). |
| `gpt-5.4-nano`, `kimi-k3` | Automatic prefix caching (8–9k tokens cached from the second call) | Same as without the header. |

A second test kept the system prompt fixed and sent a different single user message on each call, with the header. Every call wrote the cache and none read it. OpenCode puts the cache breakpoint at the end of the prompt, so separate runs that share only a system prompt never reuse the cache. That rules out option C (one ID per task).

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
  - Add `LiteLlmCoreConfig` fields: `cost_from_response_usage: bool = False` and `session_affinity_header: str | None = None`.
  - Add a case to `lite_llm_core_config_for_provider`:
    ```python
    case ModelProviderName.opencode:
        return LiteLlmCoreConfig(
            base_url=OPENCODE_API_BASE,
            additional_body_options={"api_key": Config.shared().opencode_api_key},
            cost_from_response_usage=True,
            session_affinity_header=OPENCODE_SESSION_HEADER,  # "x-opencode-session"
        )
    ```
    It has no `default_headers`. OpenCode needs no attribution headers.
- **`adapters/model_adapters/litellm_config.py` and `adapter_registry.py`:** add the two new fields to `LiteLlmConfig` and copy them in `litellm_core_provider_config`.
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

### Session header

New module `adapters/model_adapters/session_affinity.py`:

```python
def conversation_session_id(model_id: str, messages: Sequence[Mapping[str, Any]]) -> str:
    """Stable ID for a conversation: sha256 over model_id, the first system message's content and the
    first user message's content (JSON-encoded), as "kiln_" + the first 32 hex chars."""

def run_may_make_multiple_calls(chat_formatter: ChatFormatter, has_tools: bool) -> bool:
    """True for MultiturnFormatter (continuing a conversation), TwoMessageCotFormatter,
    TwoMessageCotLegacyFormatter, or any run with tools available."""
```

Changes in `LiteLlmAdapter`:

- **`async def _session_id_for_run(self, chat_formatter, initial_messages) -> str | None`:**
  - Returns `None` when `self.config.session_affinity_header` is `None`, or when `run_may_make_multiple_calls(chat_formatter, bool(await self.available_tools()))` is false.
  - Otherwise returns `conversation_session_id(provider.model_id, initial_messages)`.
- **`build_completion_kwargs` gains `session_id: str | None = None`.** When both the header name and `session_id` are set, it sends `"headers": {**(self._headers or {}), header: session_id}`. Otherwise headers stay as they are today.
- **Non-streaming:** `_run` computes the session ID once, after `initial_messages`. It passes the ID down through `_run_model_turn` to every `build_completion_kwargs` call.
- **Streaming:** `AdapterStream` computes the session ID once, at the start of `__aiter__` (it has the adapter, the formatter and the initial messages), and passes it to its `build_completion_kwargs` calls.
- **Why a hash and no stored ID:**
  - A continuation run (`prior_trace`) starts with the same system and user messages as the run it continues, so every turn of a conversation gets the same ID without storing any state. Each new turn then reads the previous turn's cache.
  - Separate eval rows have different inputs, so they get different IDs and don't share one backend.
  - Re-running an identical input gets the same ID, which is harmless and can hit the cache.
  - The ID is only a hash, sent to the provider that already receives the content.
  - It's computed per run, never stored on the adapter. Synthetic-user drives reuse one adapter across turns, and each turn's `prior_trace` still hashes to the same ID.
- **Why runs that make only one call get no header:** a single-call run gets no cache read, and on Claude the header adds a 25% cache-write charge. Most eval and data-gen runs make one call.
- **Kept generic on purpose.** It's a field on `LiteLlmCoreConfig`, not OpenCode code. That leaves room for the separate cross-provider session work the user plans, such as OpenAI's `prompt_cache_key`.

### Error mapping

**`adapters/errors.py`:**

- Add:
  ```python
  class ProviderActionRequiredError(Exception):
      """The provider refused the request for an account reason the user must fix (billing, model access,
      a retired model). Never retried; aborts a batch. Its message is user-facing."""
  ```
- `format_error_message` returns `str(exc)` for it. Add this branch before the `RuntimeError` branch.

**`adapters/retry_classification.py`:**

- `is_batch_fatal_error` adds `ProviderActionRequiredError` to its fatal tuple.
- `is_retryable_error` leaves it out.

**Hook in `BaseAdapter`:**

- Add `def translate_provider_error(self, e: Exception) -> Exception`. The default returns `e`.
- Both `except Exception as e` sites call it before building `KilnRunError`: the non-streaming one at `base_adapter.py:352` and the streaming one at `:543`. They then pass the translated exception as `original`, and as `__cause__` via `raise ... from translated`.
- The translated exception chains the LiteLLM one as its own `__cause__`, so logs keep the raw body.
- `LiteLlmAdapter` overrides the hook. It calls `translate_opencode_error(e, provider.model_id)` when the provider is `opencode`, and returns `e` for every other provider.

**New module `adapters/model_adapters/opencode_errors.py`:**

- `translate_opencode_error(e: Exception, model_id: str) -> Exception`:
  - Reads `getattr(e, "status_code", None)`.
  - Finds the first `{…}` JSON object in `str(e)` and parses it, ignoring parse failures. LiteLLM prefixes the body with text such as `OpenAIException - `.
  - Reads the OpenCode error `type` and `message` from `body["error"]`.
  - Matches only on status plus body content, never on LiteLLM's exception class, which differs across LiteLLM versions (`APIError(403)` today, possibly `PermissionDeniedError` later).

| Match | Result |
|---|---|
| 402 | `ProviderActionRequiredError("Your OpenCode workspace is out of pay-as-you-go credits. Add credits in OpenCode Console (https://opencode.ai/console). Kiln's OpenCode provider uses pay-as-you-go credits; OpenCode Go subscriptions aren't supported.")` |
| 403 and type `permission_error` and the message contains "Model access is disabled" | `ProviderActionRequiredError("The model '{model_id}' is turned off for your OpenCode workspace. Turn it on in OpenCode Console under Models.")`. If OpenCode's message has a console URL, append it. |
| 403, anything else | `ProviderActionRequiredError("OpenCode refused the request: {OpenCode message}. Check your API key's permissions and your workspace budget in OpenCode Console.")` |
| 410 and type `ModelDeprecated` | `ProviderActionRequiredError("OpenCode has retired '{model_id}'. Use '{replacement}' instead.")`. If there's no `metadata.replacement`, drop the second sentence. |
| 429 and type `FreeUsageLimitError` | `ProviderActionRequiredError("'{model_id}' is one of OpenCode's free models, which only work inside the OpenCode app. Kiln's OpenCode provider uses paid pay-as-you-go models; OpenCode Go subscriptions aren't supported.")` |
| Anything else (401, a plain 429, 400, 5xx, network) | Returned unchanged. LiteLLM's mapping and Kiln's existing handling apply: 401 is an `AuthenticationError` and batch-fatal, 429 is a `RateLimitError` and retryable. |

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
  - **The logo is not in hand yet.** Commit a placeholder glyph with a `TODO` comment. The real SVG must come from the user before merge.
- **`connect_providers.svelte`:** a card with `name: "OpenCode"`, `id: "opencode"`, `featured: false` and `api_key_fields: ["API Key"]`. It uses the approved copy from the functional spec's [Connect Screen Copy](./functional_spec.md#connect-screen-copy): the description, the `api_key_warning` (the Go notice) and the three `api_key_steps`. Also add the status entry and the `opencode_api_key` connected check.
- Regenerate `api_schema.d.ts` with `generate_schema.sh`.

## Model Catalog (PR 2)

Follow `claude-maintain-models`, adding only provider entries to existing `KilnModel`s.

- **Source list:**
  - The pricing and endpoints tables on https://opencode.ai/docs/console/models: rows with a non-zero price that aren't on its deprecated table.
  - Cross-checked against models.dev `opencode` (match on `canonical_id`, for example `anthropic/claude-sonnet-5-5`).
  - Keep only models where Kiln already has a `KilnModel`.
  - The workspace `/inference/v1/models` list isn't the full catalog, because it's filtered by the workspace's model settings.
- **Test workspace:** before the paid tests, the user turns on every candidate model in our OpenCode workspace (Console → Models). The 403 above shows what a model that's turned off returns.
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
  - Add an OpenCode Provider Quirks section covering the sources above, the inclusion rule (exclude `type` other than `chat`, zero price and the `-free` suffix), workspace model access, and that thinking levels go through `reasoning_effort`.
  - Add OpenCode to the lagging-provider check.
  - Add the models endpoint to `.agents/scripts/provider_utils.py`.
  - Deprecation checks use OpenCode's deprecated table, and treat a 410 `ModelDeprecated` as proof. Add `opencode` to `extract_models.py` / `check_provider.py`.

## Testing Strategy

The unit tests use pytest. The wire tests follow `test_cloudflare_litellm.py`: they use respx and set `monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)`, so that LiteLLM's real request and exception mapping run against recorded OpenCode bodies.

**`test_opencode_litellm.py`** (new), the wire tests:

- **Request:**
  - The request goes to `https://opencode.ai/inference/openai/v1/chat/completions` with `Authorization: Bearer <key>` and the model ID unchanged.
  - No `x-opencode-session` header on a single-turn run with no tools.
  - On a two-message chain-of-thought run, on a run with tools, and on a `prior_trace` continuation, the header is present, and it's the same on every call in the run.
  - A continuation run gets the same ID as the run it continues.
- **Cost:**
  - The cost is read from `usage.cost` on non-streaming and streaming runs.
  - A run with a known OpenAI model name still uses `usage.cost` when LiteLLM's `response_cost` differs (patch the price map, or use a `gpt-*` ID whose LiteLLM price is different).
  - When `usage.cost` is missing, the run has no cost.
  - An `int` cost of 0 is recorded as 0.0.
- **Errors**, one test per row of the mapping table, using the recorded bodies:
  - The exact `ProviderActionRequiredError` message.
  - `is_batch_fatal_error` is True and `is_retryable_error` is False.
  - 401 stays an `AuthenticationError`, and a plain 429 stays a retryable `RateLimitError`.
  - Each test records the LiteLLM exception type that came in, so a LiteLLM upgrade that changes the mapping shows up.

**Other new or extended tests:**

- `test_session_affinity.py`: `conversation_session_id` is stable, changes with the model or the first user message, and ignores later messages. `run_may_make_multiple_calls` returns the right answer for every formatter class, with and without tools.
- `test_opencode_errors.py`: JSON extraction from LiteLLM-style messages, bodies that can't be parsed, a missing replacement, and passthrough for other statuses.
- `errors.py` and retry-classification tests: `ProviderActionRequiredError` formatting and classification.
- The `BaseAdapter` hook: a translated error is what `KilnRunError.original` holds, on both the streaming and non-streaming sites.
- Existing parametrized tests extended with `opencode`: `test_provider_tools.py` (friendly name, core config), `utils/test_litellm.py`, `test_litellm_adapter.py` (model ID prefix `openai`), `test_adapter_registry.py`, `utils/test_config.py` and `test_ml_provider_list.py`.
- `test_provider_api.py`: connect success, 401, 403, another status, a request exception, the dispatch through `connect_api_key`, and disconnect. Add `opencode` to the invalid-payload and all-providers fixtures.
- `connect_providers.test.ts`: OpenCode shows as connected when `opencode_api_key` is set.
- **Live (paid, PR 2):** the standard per-model suites with `OPENCODE_API_KEY=proxy-injected` in this environment. The proxy adds the real key.

## Open Items

1. **Does `/inference/v1/models` reject bad keys?** The docs say every request authenticates and that revoked keys get 401, but the docs' own curl example for that endpoint has no key. This can't be tested here, because the proxy injects the key. The user runs this once from a normal machine:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://opencode.ai/inference/v1/models -H "Authorization: Bearer oc_sk_invalid"
   ```
   - If it prints 401, the design stands.
   - If it prints 200, `connect_opencode` switches to the Featherless pattern: `POST /inference/openai/v1/chat/completions` with model `kiln-connection-test` and `max_tokens: 16`. Here 401 means an invalid key, and the 400 "Model is unavailable" means a valid one. That call is free, because the model doesn't exist.
2. **Budget-exceeded status is undocumented.** It falls under the 402 or the generic-403 row, both of which show OpenCode's own message. No more design is needed.
3. **OpenCode SVG logo** is needed from the user before PR 1 merges.
