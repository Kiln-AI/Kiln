# Where `LiteLlmAdapter` depends on the Chat Completions shape

Every place in Kiln's LiteLLM adapter stack that assumes a Chat Completions request or response, what a Responses API path must translate there, and what LiteLLM 1.102.0's completion→Responses bridge already translates. Line numbers are against this repo at commit `c215b3e4` (2026-10-05). "Bridge" means `litellm/completion_extras/litellm_responses_transformation/transformation.py` in the installed `.venv` (litellm 1.102.0, the version `libs/core/pyproject.toml:48` pins to `>=1.102.0,<1.103`).

Labels: **Source** = what the code says. **Probe** = what I saw when I ran the real adapter against a local fake OpenAI server (see [bridge-probe-results.md](./bridge-probe-results.md)). **Inference** = my reading, not checked.

## 1. The call itself

| Touchpoint | Code | Chat-shape assumption | Responses equivalent | Bridge handles it? |
|---|---|---|---|---|
| Non-streaming call | `litellm_adapter.py:443-457` `acompletion_checking_response` | Calls `litellm.acompletion`, requires `ModelResponse` with `Choices`, and **uses only `choices[0]`** | `litellm.aresponses()` returns `ResponsesAPIResponse` with an `output` list of items | Yes, it returns a `ModelResponse`. **But** it can return **more than one choice**: one per `ResponseOutputMessage` content plus one extra choice holding all tool calls (`transformation.py:642-783`). Kiln reads only `choices[0]`. See "Preamble bug" below. |
| Streaming call | `litellm_utils/litellm_streaming.py:30-71` `StreamingCompletion` | `litellm.acompletion(stream=True)` yields `ModelResponseStream`. Forces `stream_options.include_usage`. Rebuilds the final message with `litellm.stream_chunk_builder` | Responses SSE events (`response.output_text.delta`, `response.reasoning_summary_text.delta`, `response.function_call_arguments.delta`, `response.completed`, ...) | Yes. `OpenAiResponsesToChatCompletionStreamIterator` turns SSE events into `ModelResponseStream` chunks (`transformation.py:1300-1630`). `stream_options` is normalized for Responses (`transformation.py:506-509`). Probe: streaming worked for text, reasoning summary, tool calls and usage. |
| Response validation | `adapter_stream.py:376-388` `_validate_response` | Same `choices[0]` assumption as above | — | Streaming is safe: `stream_chunk_builder` folds every chunk's `choices[0]` delta into one message (`litellm/main.py:8752+`), so text and tool calls end up in the same message. Probe confirmed. |

### Preamble bug (non-streaming only)

**Probe:** when a fake Responses reply contained `[reasoning, message("Let me add those."), function_call(add)]`, the non-streaming adapter returned `"Let me add those."` as the **final task output** and never ran the tool. The bridge put the text in `choices[0]` and the tool call in `choices[1]`; `acompletion_checking_response` (`litellm_adapter.py:457`) only looks at `choices[0]`. The same reply over streaming worked correctly (tool ran, final answer returned), because the stream builder merges.

**Inference:** this already applies today to `gpt-5.4-pro` and `gpt-5.2-pro` on OpenAI direct, because LiteLLM routes those to Responses no matter what (their cost-map entry is `mode: "responses"`). Whether real GPT-5.x/6 models emit a text message and a function call in the same response is an API-behaviour question for subtopic 1. The fix on Kiln's side is small: merge all choices' `content` and `tool_calls` into one message, or pick the choice with tool calls when there is one.

## 2. Request building (`build_completion_kwargs`, `litellm_adapter.py:725-810`)

| Field | Code | Responses equivalent | Bridge |
|---|---|---|---|
| `messages` (system + user + assistant + tool) | `litellm_adapter.py:738, 805-808`; built by `_run` `litellm_adapter.py:291-324` and the chat formatter | `instructions` + `input` items (`message`, `function_call`, `function_call_output`, `reasoning`) | Yes. Leading system messages become `instructions`; assistant `tool_calls` become `function_call` items; `role: tool` becomes `function_call_output` (`transformation.py:358-485`). Probe confirmed. |
| `temperature`, `top_p` | `litellm_adapter.py:741-742` | Same names | Passed through when not dropped. Probe: `top_p=1.0` was dropped (`drop_params`), `temperature` sent. |
| `drop_params: True` | `litellm_adapter.py:747` | n/a (LiteLLM param) | Works. |
| `reasoning_effort` (from `build_extra_body`) | `litellm_adapter.py:561-608`, set at `:596` | `reasoning: {effort, summary}` | Yes. `_map_reasoning_effort` (`transformation.py:1157-1174`) accepts any of `none, minimal, low, medium, high, xhigh, max` (`litellm/types/llms/openai.py:1889`). A dict is passed through as-is, so `{"effort": "high", "summary": "auto"}` works. **It does not ask for a summary by default**, so real OpenAI will return no reasoning text unless Kiln asks (see §4). |
| `tools`, `tool_choice: "auto"` | `litellm_adapter.py:760-764`, `862-881` | Flat function tools `{type, name, parameters, strict, description}` | Yes (`transformation.py:1095-1126`). Probe: Kiln tools are sent with `"strict": null` because Kiln's tool definitions don't set `strict`. **Inference / for subtopic 1:** check how OpenAI treats `strict: null` on Responses, since Responses documents a different default for `strict` than Chat Completions does. |
| `allowed_openai_params` | `litellm_adapter.py:690-723, 798-803` | n/a (LiteLLM param) | The bridge adds `reasoning_effort` to it itself (`litellm/main.py:5437-5442`). |
| `response_format` json_schema | `litellm_adapter.py:507-529` | `text.format = {type: json_schema, name, schema, strict}` | Yes (`transformation.py:1207-1253`). Probe: became `text.format` with `strict: false`, because Kiln never sets `strict` here. Chat Completions also treats a missing `strict` as false, so behaviour matches. |
| `response_format` json_object | `litellm_adapter.py:472, 487` | `text.format = {type: json_object}` | Yes. |
| function-calling structured output (`task_response` tool, forced `tool_choice`) | `litellm_adapter.py:531-559` | Flat tool plus `tool_choice: {type: function, name}` | Yes. `_normalize_tool_choice_for_responses_api` flattens it (`transformation.py:294-311`). Probe: worked, and `strict: true` was carried. |
| `logprobs`, `top_logprobs` | `litellm_adapter.py:794-796` | `include: ["message.output_text.logprobs"]` + `top_logprobs` | **No.** Probe: neither was sent, and the run failed with Kiln's own "Logprobs were required, but no logprobs were returned" (`litellm_adapter.py:423-424`). Low impact: every GPT-5.x/6 OpenAI entry in Kiln's list has `supports_logprobs=False`. |
| `cache_control_injection_points` | `litellm_adapter.py:752-758` | OpenAI caches prompts on its own; `prompt_cache_key` is optional | Harmless. Probe: no `cache_control` keys leaked into the Responses body. Cached tokens were still reported. |
| `api_base`, `headers` | `litellm_adapter.py:739-740` | Same | Yes. Headers become `extra_headers` (`transformation.py:636-637`). |
| `additional_body_options` spread | `litellm_adapter.py:749` | — | Keys that are Responses params (`store`, `include`, `prompt_cache_key`, `truncation`, ...) are passed through. Probe: `store: false` and `include: ["reasoning.encrypted_content"]` arrived intact. |
| OpenRouter / Anthropic / Gemini / SiliconFlow extra_body branches | `litellm_adapter.py:580-671` | n/a | Not relevant. The automatic GPT-5 bridge check only runs for the LiteLLM providers `openai` and `azure` (`litellm/main.py:1126`). The `responses/` prefix and cost-map `mode: responses` checks apply to any provider, but Kiln has no non-OpenAI models that use them. |
| Cerebras assistant-field stripping | `litellm_adapter.py:72-95, 806-807` | n/a | Not relevant. |
| Model id | `litellm_adapter.py:675-688` → `utils/litellm.py:108-112` builds `"{litellm_provider}/{model_id}"` | `openai/responses/<model>` forces the bridge | See §5. |

## 3. Response handling

| Touchpoint | Code | Bridge result |
|---|---|---|
| Content and tool calls | `litellm_adapter.py:195-200` (`response_choice.message.content`, `.tool_calls`), `adapter_stream.py:241-244` | Chat-shaped `Message`. Probe: correct apart from the preamble case above. |
| Tool call id | `litellm_adapter.py:933-948` uses `tool_call.id` for the `tool_call_id` it sends back | The bridge uses the Responses `call_id`, or the item `id` if `call_id` looks like `call_<digits>` (`litellm/responses/litellm_completion_transformation/transformation.py:2220-2229`). The ids round-trip consistently. (My fake server used `call_1`, so the bridge picked `fc_1`. Real OpenAI call ids aren't plain digits.) |
| Custom (non-function) tool calls | `litellm_utils/tool_calls.py:9-28` rejects them | The bridge can emit them, but Kiln only registers function tools, so this doesn't come up. |
| Empty / refusal / incomplete | `adapter_stream.py:46-87` `raise_for_empty_model_response` checks `finish_reason` and `message.refusal` | The bridge maps `incomplete_details.reason` to `finish_reason` `length` or `content_filter` (`transformation.py:200-204, 910-923`). So a content filter still produces Kiln's "declined" error. **Inference:** Responses `refusal` content parts are not mapped to `message.refusal`. Unverified. |
| Assembled stream message | `adapter_stream.py:234-246` | Works. However, `stream_chunk_builder` does **not** rebuild `reasoning_items`. Probe: in streaming mode the reasoning item was **not** sent back on the second tool-loop call. Non-streaming did send it back. |

## 4. Reasoning capture

| Touchpoint | Code | Notes |
|---|---|---|
| `intermediate_outputs["reasoning"]` | `litellm_adapter.py:428-441` reads `choices[0].message.reasoning_content` | The bridge joins the reasoning summary text into `reasoning_content` (`transformation.py:682-688`). Probe: captured. **But** real OpenAI only returns summary text when the request includes `reasoning.summary`, and by default the bridge sends `reasoning: {effort}` only (`transformation.py:1157-1174`). Kiln must ask for it, either with `reasoning_effort={"effort": L, "summary": "auto"}` or with the top-level kwarg `reasoning_summary="auto"` (see §5). |
| "Reasoning required" check | `base_adapter.py:303-325`, `494-511` | Only fires when `provider.reasoning_capable`. All GPT-5.x/6 OpenAI entries have `reasoning_capable=False`, so nothing breaks if no summary comes back. |
| Streaming reasoning events | `stream_events.py:209-295` reads `delta.reasoning_content` | The bridge emits `Delta(reasoning_content=...)` for `response.reasoning_summary_text.delta` (`transformation.py:1541-1550`). Probe: the AI SDK stream produced `reasoning-start`, `reasoning-delta` and `reasoning-end` events. Quirk: those chunks use `summary_index` as the choice `index`. Kiln's converter and `stream_chunk_builder` both ignore the index, so this is harmless today. |
| Encrypted reasoning across tool calls (same run) | Kiln keeps the LiteLLM `Message` objects in `messages_internal` during a run (`litellm_adapter.py:202-205, 297`) | Non-streaming: the bridge stores `reasoning_items` (id, summary, `encrypted_content`) on the `Message` and sends them back on the next call (`transformation.py:110-134, 439`). Probe: the `encrypted_content` round-tripped. Streaming: lost (see §3). |
| Reasoning across saved traces / multi-turn | `litellm_adapter.py:965-1017` `litellm_message_to_trace_message` keeps only `content`, `reasoning_content`, `tool_calls`, `latency_ms`, `usage` | `reasoning_items` (and so `encrypted_content`) are dropped from the saved trace. A `prior_trace` continuation therefore resends no reasoning items. That is stateless and valid. The model just loses its earlier hidden reasoning. Keeping them would need a new trace field, which is a datamodel change. |

## 5. Usage and cost

| Touchpoint | Code | Bridge result |
|---|---|---|
| Token counts | `litellm_adapter.py:812-849` reads `usage.prompt_tokens`, `completion_tokens`, `total_tokens`, `prompt_tokens_details.cached_tokens` | `ResponseAPILoggingUtils._transform_response_api_usage_to_chat_usage` maps `input_tokens` / `output_tokens` / `input_tokens_details` onto the chat names (`litellm/responses/utils.py:1130-1180`). Probe: `input_tokens=100, output_tokens=50, cached_tokens=40` came through. |
| Cost | `litellm_adapter.py:816` `_hidden_params["response_cost"]` | Probe: `cost=0.000624` was filled in, both for automatic bridging and with the `openai/responses/` prefix. The bridge keeps the hidden params (`transformation.py:942-956`). Cost needs the model in LiteLLM's cost map. `gpt-6.1-sol` is there; `gpt-6-sol-pro` is not, so it would cost $0 (`litellm.get_model_info` probe). |
| Streaming usage | `litellm_streaming.py:39-43`, `stream_events.py:290-293` | The `response.completed` event carries the usage (`transformation.py:1552-1590`). Probe: streaming usage and cost matched non-streaming. |

## 6. Public contracts that must not change (no `BaseAdapter` changes)

- `BaseAdapter.invoke_openai_stream` yields **`ModelResponseStream`** chunks (`base_adapter.py:381-400, 857-905`). `AiSdkStreamResult` feeds those chunks into `AiSdkStreamConverter` (`base_adapter.py:907-983`, `stream_events.py:209`). A Responses path has to produce chat-shaped chunks to keep this contract. The bridge already does. A direct `litellm.aresponses()` path would have to write that converter itself.
- `_run` must mutate `trace_ref` in place and return chat-shaped trace messages (`base_adapter.py:554-577`, `litellm_adapter.py:278-384`). Traces are `ChatCompletionMessageParam` lists (`utils/open_ai_types.py:46+`) used by evals, multi-turn (`chat/chat_formatter.py:278` `MultiturnFormatter`) and fine-tune export. A Responses path must keep writing chat-shaped traces. The bridge gives it chat-shaped `Message` objects for free.
- `AdapterStream` (`adapter_stream.py:96-364`) holds a second copy of the tool loop for streaming. Any Responses path has to change both loops, unless the change stays below `acompletion` / `StreamingCompletion`, as the bridge does.

## 7. Other `litellm.acompletion` callers (out of the adapter, for completeness)

`extractors/litellm_extractor.py:236, 401` and `app/desktop/studio_server/provider_api.py:1337, 1788` (connection tests) also call `litellm.acompletion`. The bridge applies to them too when the model and params match. A change inside `LiteLlmAdapter` won't reach them.
