# `litellm.responses()` / `aresponses()` — surface, return types, provider coverage

Primary source: the installed package `litellm==1.102.0` in `/home/user/Kiln/.venv/lib/python3.13/site-packages/litellm` (Kiln pins `litellm>=1.102.0,<1.103`). File paths below are relative to that `litellm/` directory. Docs: [LiteLLM `/responses` page](https://docs.litellm.ai/docs/response_api) (fetched 2026-10-05).

## Signature (1.102.0, `responses/main.py`)

`aresponses` (line 541) and `responses` (line 1088) share one signature. Verbatim from `responses()`:

```python
def responses(
    input: str | ResponseInputParam,
    model: str,
    include: list[ResponseIncludable] | None = None,
    instructions: str | None = None,
    max_output_tokens: int | None = None,
    prompt: PromptObject | None = None,
    metadata: dict[str, object] | None = None,
    parallel_tool_calls: bool | None = None,
    previous_response_id: str | None = None,
    reasoning: Reasoning | None = None,
    store: bool | None = None,
    background: bool | None = None,
    stream: bool | None = None,
    temperature: float | None = None,
    text: Optional["ResponseText"] = None,
    text_format: type["BaseModel"] | dict | None = None,
    tool_choice: ToolChoice | None = None,
    tools: Iterable[ToolParam] | None = None,
    top_p: float | None = None,
    truncation: Literal["auto", "disabled"] | None = None,
    user: str | None = None,
    service_tier: str | None = None,
    safety_identifier: str | None = None,
    extra_headers: dict[str, object] | None = None,
    extra_query: dict[str, object] | None = None,
    extra_body: dict[str, object] | None = None,
    timeout: float | httpx.Timeout | None = None,
    # LiteLLM specific params,
    allowed_openai_params: list[str] | None = None,
    custom_llm_provider: str | None = None,
    **kwargs,
):
```

`aresponses` is the same minus `allowed_openai_params` in the explicit list. It is annotated `-> ResponsesAPIResponse | BaseResponsesAPIStreamingIterator`.

Notes:
- **`text_format`** takes a Pydantic model class or a dict and is turned into `text={"format": ...}` by `ResponsesAPIRequestUtils.convert_text_format_to_text_param`. This is a LiteLLM convenience. It is not in the OpenAI wire API.
- `**kwargs` carries the usual LiteLLM params: `api_key`, `api_base`, `drop_params`, `metadata`/`litellm_metadata`, `use_chat_completions_api`, `mock_response`, and so on.
- The full set of optional request keys LiteLLM knows about is `ResponsesAPIOptionalRequestParams` in `types/llms/openai.py:1237`: `include, instructions, max_output_tokens, metadata, parallel_tool_calls, previous_response_id, reasoning, store, background, stream, temperature, text, tool_choice, tools, top_p, truncation, user, service_tier, safety_identifier, prompt, max_tool_calls, prompt_cache_key, prompt_cache_retention, prompt_cache_options, stream_options, top_logprobs, partial_images, context_management`. **There is no `verbosity` key and no `logprobs` key.** This matters for the chat→responses bridge (see [completion-to-responses-bridge.md](./completion-to-responses-bridge.md)).
- If you pass `reasoning_effort=` as a kwarg to `responses()` and no `reasoning`, LiteLLM maps it to `reasoning` (`responses/main.py` ~L1255).
- `REASONING_EFFORT = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]` (`types/llms/openai.py:1889`).

### Return types (verified by probe)

- Non-streaming: `litellm.types.llms.openai.ResponsesAPIResponse`. It is a Pydantic `BaseLiteLLMOpenAIResponseObject` that mirrors OpenAI's `Response`. It has `.output`, `.output_text`, `.usage` (`ResponseAPIUsage` with `input_tokens`, `output_tokens`, `input_tokens_details.cached_tokens`, `output_tokens_details.reasoning_tokens`), and `._hidden_params["response_cost"]`. See [probe-evidence.md](./probe-evidence.md), probe 3.
- Streaming: a `BaseResponsesAPIStreamingIterator` (sync or async) that yields typed Responses events (`response.created`, `response.output_text.delta`, `response.completed`, ...). The event-class map is `OpenAIResponsesAPIConfig.get_event_model_class` in `llms/openai/responses/transformation.py`.
- **The response `id` is rewritten.** The probe got back `resp_bGl0ZWxsbTpjdXN0b21fbGxtX3Byb3ZpZGVyOm9wZW5haTttb2RlbF9pZDpOb25lO3Jlc3BvbnNlX2lkOnJlc3BfMTIz` for an upstream id of `resp_123`. That is base64 of `litellm:custom_llm_provider:openai;model_id:None;response_id:resp_123`, done by `_update_responses_api_response_id_with_model_id`. LiteLLM decodes it again when the id comes back as `previous_response_id`. Anyone who logs or compares raw provider ids should know this.
- Cost: `litellm.completion_cost(completion_response=<ResponsesAPIResponse>)` works, and `_hidden_params["response_cost"]` is filled in. Both gave the same number in probe 3. The docs state "Cost Tracking ✅ Works with all supported models".

## Native providers vs. the chat-completions bridge

Dispatch rule (`responses/main.py`):

```python
def _bridges_to_chat_completions(responses_api_provider_config, use_chat_completions_api) -> bool:
    """Whether the request reaches its provider as a chat completion, not a Responses call."""
    return responses_api_provider_config is None or use_chat_completions_api is True
```

So a provider is "native" exactly when `ProviderConfigManager.get_provider_responses_api_config()` (`utils.py:8744`) returns a config. In 1.102.0 the Python-class configs are (`utils.py:8789-8853`):

| Provider | Native Responses config | Notes |
|---|---|---|
| `openai` | `OpenAIResponsesAPIConfig` | Always. A custom `api_base` is still sent to `{api_base}/responses`. Use `use_chat_completions_api=True` or the `openai/chat_completions/<model>` prefix to force chat. |
| `azure` | `AzureOpenAIResponsesAPIConfig` / `AzureOpenAIOSeriesResponsesAPIConfig` | O-series is chosen when `"o_series"` is in the name or the model `supports_reasoning` and the name has no `"gpt"`. The probe hit `{api_base}/openai/responses?api-version=...`. |
| `openrouter` | `OpenRouterResponsesAPIConfig` (subclass of the OpenAI one) | Uses `https://openrouter.ai/api/v1/responses`. OpenRouter's own docs say that API "is **stateless**" and "Requests that set `store: true` or a non-null `previous_response_id` are rejected with a `400` error" ([OpenRouter Responses overview](https://openrouter.ai/docs/api/reference/responses/overview)). |
| `xai` | `XAIResponsesAPIConfig` | |
| `github_copilot` | only for models where `github_copilot_supports_responses_api(model)` | |
| `chatgpt` | `ChatGPTResponsesAPIConfig` | |
| `litellm_proxy` | `LiteLLMProxyResponsesAPIConfig` | |
| `volcengine`, `manus`, `perplexity` | yes | |
| `databricks` | only if `"gpt"` is in the model name | |
| `hosted_vllm`, `fireworks_ai` | yes | Fireworks native Responses arrived in 1.102.0 ([release notes](https://docs.litellm.ai/release_notes/v1.102.0/v1-102-0)). |
| `bedrock_mantle` | only models the cost map marks as Responses-capable | |
| JSON-defined OpenAI-compatible providers | only if `providers.json` sets `supports_responses_api` | |
| any deployment whose `model_info.supported_endpoints` contains `/v1/responses` | generic `OpenAILikeResponsesConfig` | |

Every other provider has no config, so `responses()` **bridges to `litellm.completion()`**. That covers `anthropic`, `gemini`, `vertex_ai`, `bedrock` (Converse), `groq`, `together_ai`, `fireworks` chat models, and the rest. The docs describe this: "LiteLLM allows you to call non-Responses API models via a bridge to LiteLLM's /chat/completions endpoint. This is useful for calling Anthropic, Gemini and even non-Responses API OpenAI models." ([docs](https://docs.litellm.ai/docs/response_api)). The responses→chat transformation is in `responses/litellm_completion_transformation/` (about 2.8k lines in `transformation.py`).

Note on the docs: the summary table says "Supported LLM providers: All LiteLLM supported providers". That counts both native and bridged providers. The docs do not list which ones are native. The table above comes from the source.

## Forcing a route from the `responses()` side

From the docs, quoted:

> "Use either of these to force the /responses → /chat/completions bridge: `use_chat_completions_api: true` — makes it explicit that LiteLLM will call the provider's chat-completions API. `openai/chat_completions/<model_name>` — same pattern as `responses/` on chat completions: the model id encodes the routing choice."

The code is `_normalize_openai_chat_completions_responses_model` and `_pop_use_chat_completions_api_kw` in `responses/main.py`.

## Known open issues on this surface (from the LiteLLM tracker, Oct 2026)

- [#35878](https://github.com/BerriAI/litellm/issues/35878) (open). With `use_chat_completions_api`, `allowed_openai_params` is not forwarded and namespace/tool_search tools are dropped.
- [#27276](https://github.com/BerriAI/litellm/issues/27276), [#27655](https://github.com/BerriAI/litellm/issues/27655) (open). The Responses→Chat bridge forwards unsupported built-in tool types.
- [#38065](https://github.com/BerriAI/litellm/issues/38065) (open). Streaming `/v1/responses` loses usage for some providers.

These affect people who call `responses()` on non-native providers. Kiln would only hit them if it called `litellm.responses()` for non-OpenAI providers.
