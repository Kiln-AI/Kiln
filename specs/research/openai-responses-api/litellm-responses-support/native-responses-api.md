# Native `litellm.responses()` / `litellm.aresponses()`

Scope: LiteLLM 1.102.0 `responses/main.py`, `responses/streaming_iterator.py`, `responses/utils.py`, `llms/openai/responses/transformation.py`, `utils.py` (`ProviderConfigManager`). Experiments: `/tmp/claude-0/-home-user-Kiln/dd147251-f363-5e17-95c4-80813a10f3ed/scratchpad/litellm_wire/native_and_azure.py` / `.out`, `fake_stream_check.py` / `.out`.

## Signature

`aresponses()` (`responses/main.py:540-725`) and `responses()` (`responses/main.py:1088-1393`) take OpenAI Responses parameters by name:

```python
async def aresponses(
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
    custom_llm_provider: str | None = None,
    **kwargs,
) -> ResponsesAPIResponse | BaseResponsesAPIStreamingIterator
```

Parameter types (`Reasoning`, `ResponseInputParam`, `ToolChoice`, `ToolParam`, `ResponseIncludable`, `ResponseText`) are re-exported from the `openai` SDK's `responses` types (`types/llms/openai.py:38-61`). `text_format` accepts a Pydantic class or dict and is converted to `text` (`responses/utils.py:1015+`). Other `**kwargs` include LiteLLM params (`api_key`, `api_base`, `drop_params`, `allowed_openai_params`, `litellm_metadata`, `mock_response`, `use_chat_completions_api`, ...). A `reasoning_effort` kwarg is mapped to `reasoning` when `reasoning` is not given (`responses/main.py:1256-1261`).

Parameters are filtered against `ResponsesAPIOptionalRequestParams` and checked against the provider config's supported list. Unsupported ones raise `UnsupportedParamsError` unless `drop_params` is set (`responses/utils.py:169-245`). For OpenAI, every Responses param is supported (`OpenAIResponsesAPIConfig.get_supported_openai_params`, `llms/openai/responses/transformation.py:184-201`). OpenAI-specific adjustments in `map_openai_params` (`llms/openai/responses/transformation.py:203-259`):

- `max_output_tokens` below 16 is raised to 16.
- `reasoning.effort` on a model whose map entry lacks `supports_reasoning` raises `UnsupportedParamsError` (or is dropped with `drop_params`).
- GPT-5-family `temperature != 1` raises unless the effort resolves to `none` and the model supports `none`, using the same rule as the chat config (`OpenAIGPT5Config.effort_resolves_to_none`).

`transform_responses_api_request` (`llms/openai/responses/transformation.py:261-306`) also strips Anthropic `cache_control` markers, decodes tool `parameters` given as JSON strings, sanitizes tool schemas for OpenAI's validator, and drops reasoning-item `status: null`. Request body sent by the experiment:

```json
{"model": "gpt-5.4", "input": [{"role": "user", "content": "hi"}], "include": ["reasoning.encrypted_content"],
 "reasoning": {"effort": "high", "summary": "auto"}, "store": false,
 "tools": [{"type": "function", "name": "get_weather", "parameters": {"type": "object", "properties": {}}}]}
```

Unlike the bridge, the native call sends tools exactly as given. No `"strict": null` is added.

## Return types

- Non-streamed: `ResponsesAPIResponse` (`types/llms/openai.py`), a Pydantic model shaped like the OpenAI SDK's `Response` with `output` items typed as the SDK's output item classes. It falls back to `model_construct` if validation fails (`llms/openai/responses/transformation.py:536-565`).
- Streamed: `ResponsesAPIStreamingIterator` (async) or `SyncResponsesAPIStreamingIterator` (`responses/streaming_iterator.py:831-993`). Each item is a typed event class (`ResponseCreatedEvent`, `OutputItemAddedEvent`, `OutputTextDeltaEvent`, `FunctionCallArgumentsDeltaEvent`, `ResponseCompletedEvent`, ...). Events without a dedicated class arrive as `GenericEvent`; in the experiment this included every `response.reasoning_summary_*` event and `response.content_part.done`. The terminal `response.completed` / `.incomplete` / `.failed` event is kept on `iterator.completed_response` (`responses/streaming_iterator.py:406-421`).

Observed event classes for a reasoning + message + function-call stream:

```text
ResponseCreatedEvent, ResponseInProgressEvent, OutputItemAddedEvent,
GenericEvent (response.reasoning_summary_part.added), GenericEvent (...reasoning_summary_text.delta) x2,
GenericEvent (...reasoning_summary_text.done), GenericEvent (...reasoning_summary_part.done), ...,
OutputItemDoneEvent, OutputItemAddedEvent, ContentPartAddedEvent, OutputTextDeltaEvent x2,
OutputTextDoneEvent, ContentPartDoneEvent, OutputItemDoneEvent, OutputItemAddedEvent,
FunctionCallArgumentsDeltaEvent x2, FunctionCallArgumentsDoneEvent, OutputItemDoneEvent,
ResponseCompletedEvent
```

## Response ids are rewritten

`ResponsesAPIRequestUtils._update_responses_api_response_id_with_model_id` (`responses/utils.py:319-370`) replaces `response.id` with `"resp_" + base64("litellm:custom_llm_provider:{provider};model_id:{model_id};response_id:{upstream_id}")`. Observed: upstream `resp_abc` came back as `resp_bGl0ZWxsbTpjdXN0b21fbGxtX3Byb3ZpZGVyOm9wZW5haTttb2RlbF9pZDpOb25lO3Jlc3BvbnNlX2lkOnJlc3BfYWJj`. LiteLLM decodes it again when the id is passed back as `previous_response_id` (observed on the wire: `resp_abc`). The purpose is router session affinity. A caller that stores ids, or calls OpenAI directly with them, must decode them first (`ResponsesAPIRequestUtils.decode_previous_response_id_to_original_previous_response_id`). The streamed `completed_response.response.id` is rewritten the same way. The chat bridge undoes this and returns the upstream id (`completion_extras/.../transformation.py:92-95,938`). Optional `encrypted_content_affinity_enabled` metadata also wraps `encrypted_content` and output item ids with the model id (`responses/utils.py:373-545`); it is off unless set in `litellm_metadata`.

## Usage and cost

- Non-streamed: `usage` is the Responses shape (`input_tokens`, `input_tokens_details.cached_tokens`, `output_tokens`, `output_tokens_details.reasoning_tokens`, `total_tokens`). `_hidden_params["response_cost"]` is set by the logging layer. Observed `0.0061`, and `litellm.completion_cost(completion_response=resp)` also returned `0.0061`.
- Streamed: on the terminal event, `_stamp_responses_usage_cost` (`responses/streaming_iterator.py:1320-1336`) computes the cost through the logging object and writes it onto `response.usage.cost`. Observed `completed usage: {..., 'cost': 0.0061}`.
- `ResponseAPILoggingUtils._transform_response_api_usage_to_chat_usage` turns either form into a chat `Usage` when a caller needs one (`responses/utils.py:1130-1234`).

## Provider coverage

`ProviderConfigManager.get_provider_responses_api_config()` (`utils.py:8744-8778`, `_get_python_responses_api_config` at `utils.py:8781-8853`) returns a native Responses config for: `openai`, `azure` (with an o-series variant), `xai`, `github_copilot` (model-dependent), `chatgpt`, `litellm_proxy`, `volcengine`, `manus`, `perplexity`, `databricks` (only model names containing `gpt`), `openrouter`, `hosted_vllm`, `fireworks_ai`, `bedrock_mantle` (map-driven), plus OpenAI-compatible providers registered in LiteLLM's JSON provider registry with Responses support. Every other provider is served by the reverse bridge: `litellm_completion_transformation_handler.response_api_handler()` converts the Responses request into `litellm.completion()` and converts the reply back (`responses/main.py:406-432,1304-1317`). The docs list "All LiteLLM supported providers" for `/responses` and explain the reverse bridge ([/responses docs](https://docs.litellm.ai/docs/response_api)). `use_chat_completions_api=True` or an `openai/chat_completions/<model>` prefix forces the reverse bridge for an `openai/` model on a chat-only server.

That reverse bridge is a separate converter with its own defects. Examples: reasoning items dropped for providers without a native config, issue [#36197](https://github.com/BerriAI/litellm/issues/36197); raw reasoning lost, issue [#40654](https://github.com/BerriAI/litellm/issues/40654). It only matters for Kiln if Kiln sends non-OpenAI providers through `litellm.responses()`.

## Streaming that is faked

`OpenAIResponsesAPIConfig.should_fake_stream()` (`llms/openai/responses/transformation.py:710-730`) returns true when `supports_native_streaming()` is false for the model. That is the case for map entries marked `supports_native_streaming: false` (`gpt-5-pro`, `o1-pro` in the bundled map) and for any model the map lookup cannot find (`utils.py:2514-2545` returns `False` on exception). A faked stream sends one non-streaming request and replays synthetic events afterwards.

Observed (`fake_stream_check.out`, `azure_stream_check.out`):

```text
native aresponses openai/gpt-5.4           stream sent upstream=True  events yielded=26
native aresponses openai/gpt-9-unknown     stream sent upstream=True  events yielded=26
azure/responses/my-gpt54-deployment    path=/openai/v1/responses?api-version=preview stream sent upstream=None  chunks=14
azure/responses/gpt-5.4                path=/openai/v1/responses?api-version=preview stream sent upstream=True  chunks=10
```

For OpenAI, an unknown model name still streamed natively in this test. For Azure, a deployment name that is not a model-map key was fake-streamed: no `stream` in the request, one blocking call, synthetic chunks after the full reply. Onyx patches `AzureOpenAIResponsesAPIConfig.should_fake_stream` for this reason ("unknown models still fake-stream via `supports_native_streaming` returning False", [onyx#13192](https://github.com/onyx-dot-app/onyx/pull/13192)).

## Native call versus the bridge, for a caller holding chat-shaped history

| Concern | Bridge (`acompletion` routed to `/responses`) | Native (`aresponses`) |
|---|---|---|
| Input shape | Chat messages; LiteLLM converts | Responses `input` items; caller converts |
| Output shape | `ModelResponse` / `ModelResponseStream` (chat) | `ResponsesAPIResponse` / typed events |
| Text + tool call in one reply | Two choices in 1.102.x (non-streamed) | Ordered `output` items, nothing lost |
| Reasoning items | `message.reasoning_items`; last-only if several; dropped by `stream_chunk_builder` | Full `output` list; `completed_response.response.output` when streamed |
| Streaming reasoning summary | `reasoning_content` deltas, wrong choice index for parts > 0, no separators | `response.reasoning_summary_text.delta` events with `summary_index` |
| Tool `strict` | `null` when absent | Whatever the caller sends |
| `n`, `logprobs`, `seed`, `stop`, `verbosity` | Silently dropped | Not Responses params; caller decides |
| Response id | Upstream `resp_...` | LiteLLM-encoded `resp_<base64>` |
| Usage / cost | Chat `Usage`, `_hidden_params["response_cost"]` | Responses usage; `response_cost` and streamed `usage.cost` |
| Routing | Implicit, changes with model name, tools, effort, base URL and the remote model map | Explicit: the caller chose `/responses` |
| Other providers | Unchanged (chat) | Reverse bridge, a different converter |
