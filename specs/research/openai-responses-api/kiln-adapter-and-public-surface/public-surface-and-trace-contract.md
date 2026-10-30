# Public surface and the trace contract

Scope: what a migration must keep stable: `BaseAdapter`'s public methods and types, the trace format stored in `TaskRun.trace` and accepted as `prior_trace`, and everything that reads traces. Line numbers from commit `579014ab`, read 2026-10-30. Labels: **Read**, **Observed**, **Inference**.

## 1. `BaseAdapter` public methods ([base_adapter.py](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py))

Read.

| Method | Signature (abridged) | Returns | Lines |
|---|---|---|---|
| `invoke` | `(input: InputType, input_source: DataSource \| None = None, prior_trace: list[ChatCompletionMessageParam] \| None = None, parent_task_run: TaskRun \| None = None)` | `TaskRun` | [L210-220](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py#L210) |
| `invoke_returning_run_output` | same args | `Tuple[TaskRun, RunOutput]` | [L369-379](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py#L369) |
| `invoke_openai_stream` | same args | `OpenAIStreamResult`: async-iterable of `litellm.types.utils.ModelResponseStream`, then `.task_run` | [L381-400](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py#L381), class [L857-904](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py#L857) |
| `invoke_ai_sdk_stream` | same args | `AiSdkStreamResult`: async-iterable of `AiSdkStreamEvent`, then `.task_run` | [L402-418](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py#L402), class [L907-983](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py#L907) |

Notes:

- `invoke_openai_stream`'s docstring: "Stream raw OpenAI-protocol chunks ... Tool-call rounds happen internally and are not surfaced". The yielded type is LiteLLM's Chat Completions chunk class, so the public type ties Kiln to LiteLLM's chat shape regardless of the wire endpoint.
- Errors after the model call starts are re-raised as `KilnRunError(message, partial_trace, original)`; the partial trace comes from `_messages_to_trace(trace_ref)` ([L349-367](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py#L349)). `LiteLlmAdapter` overrides `_messages_to_trace` to convert live `Message` objects ([litellm_adapter.py:1231-1238](../../../../libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py#L1231)). Retry logic and error text classify by LiteLLM exception classes (`litellm.RateLimitError`, `AuthenticationError`, `Timeout`, `APIConnectionError`, `InternalServerError`, `JSONSchemaValidationError`, ...) in [retry_classification.py:39-60](../../../../libs/core/kiln_ai/adapters/retry_classification.py#L39) and [errors.py:97-120](../../../../libs/core/kiln_ai/adapters/errors.py#L97). A new call path must raise the same classes for retries and messages to keep working.
- `AdapterConfig` ([L78-135](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py#L78)): `allow_saving`, `top_logprobs`, `default_tags`, `task_run_config_id`, `prompt_builder`, `skills`, `return_on_tool_call`, `unmanaged_tools`, `automatic_prompt_caching`. The ones that change the request: `top_logprobs`, `return_on_tool_call`, `unmanaged_tools`, `automatic_prompt_caching`.
- `RunOutput` ([run_output.py:12-22](../../../../libs/core/kiln_ai/adapters/run_output.py#L12)): `output`, `intermediate_outputs`, `output_logprobs: litellm ChoiceLogprobs | None`, `trace`, and `is_toolcall_pending` (true when the trace ends with an assistant message holding non-`task_response` tool calls, [open_ai_types.py:270-288](../../../../libs/core/kiln_ai/utils/open_ai_types.py#L270)).
- The `litellm_adapter` module is exported from `kiln_ai.adapters.model_adapters` ([__init__.py](../../../../libs/core/kiln_ai/adapters/model_adapters/__init__.py)). No subclass of `LiteLlmAdapter` exists in this repo; `AdapterStream` calls its methods (`build_completion_kwargs`, `usage_from_response`, `process_tool_calls`, `_extract_and_validate_logprobs`, `_extract_reasoning_to_intermediate_outputs`, `all_messages_to_trace`, `base_adapter_config`).

## 2. Trace types ([utils/open_ai_types.py](../../../../libs/core/kiln_ai/utils/open_ai_types.py))

Read.

- `ChatCompletionMessageParam` = union of OpenAI SDK `developer`, `system`, `user`, `function` message TypedDicts and two Kiln wrappers ([L134-141](../../../../libs/core/kiln_ai/utils/open_ai_types.py#L134)).
- `ChatCompletionAssistantMessageParamWrapper` ([L47-108](../../../../libs/core/kiln_ai/utils/open_ai_types.py#L47)): `role`, `audio`, `content`, `reasoning_content` (documented as "A LiteLLM property for reasoning data"), `function_call`, `name`, `refusal`, `tool_calls: List[ChatCompletionMessageToolCallParam]`, plus Kiln-only `latency_ms`, `usage`.
- `ChatCompletionToolMessageParamWrapper` ([L111-131](../../../../libs/core/kiln_ai/utils/open_ai_types.py#L111)): `content`, `role`, `tool_call_id`, plus Kiln-only `kiln_task_tool_data`, `is_error`, `error_message`.
- `KILN_ONLY_MESSAGE_FIELDS = {latency_ms, is_error, error_message, kiln_task_tool_data, usage}` are stripped before sending ([L144-173](../../../../libs/core/kiln_ai/utils/open_ai_types.py#L144)). Everything else in a trace dict is sent to the provider as-is.
- `TaskRun.trace: list[ChatCompletionMessageParam] | None`, "The trace of the task run in OpenAI format" ([task_run.py:122-125](../../../../libs/core/kiln_ai/datamodel/task_run.py#L122)).

**Observed:** pydantic validation of this union drops keys a TypedDict does not declare. `{"role":"assistant","content":"hi","reasoning_content":"r","provider_specific_fields":{...},"kiln_new_field":1}` validates to `{'role': 'assistant', 'content': 'hi', 'reasoning_content': 'r'}`. So nothing Responses-specific (reasoning item ids, encrypted reasoning, response ids) can survive in a saved trace unless the wrapper type declares it. Adding a declared optional field is additive for old traces; old app versions reading a newer trace would silently drop the field (and drop it again on re-save).

The same union appears in the web API schema ([api_schema.d.ts:5190](../../../../app/web_ui/src/lib/api_schema.d.ts#L5190), used by `trace` and `judge_trace` fields), so a new declared field means regenerating it (`app/web_ui/src/lib/generate_schema.sh`; CI runs `check_schema.sh`).

## 3. Who reads or replays traces

Read. Each of these relies on the chat shape (`role`, `content`, `tool_calls[].id/function`, `tool_call_id`, `reasoning_content`).

| Reader | What it does with the trace | File |
|---|---|---|
| `MultiturnFormatter` | Seeds the next run with the whole prior trace, appends a user message or `role: tool` results (resume after `return_on_tool_call`) | [chat_formatter.py:278-353](../../../../libs/core/kiln_ai/adapters/chat/chat_formatter.py#L278) |
| `/api/projects/{p}/tasks/{t}/run` with `parent_task_run_id` | Loads the parent `TaskRun.trace` from disk as `prior_trace` | [libs/server/kiln_server/run_api.py:787-815](../../../../libs/server/kiln_server/run_api.py#L787) |
| Synthetic user (multi-turn evals) | Each turn calls `invoke(..., prior_trace=...)`, with `automatic_prompt_caching=True` | [synthetic_user/runner.py:591-626](../../../../libs/core/kiln_ai/synthetic_user/runner.py#L591), [driver.py:135](../../../../libs/core/kiln_ai/synthetic_user/driver.py#L135), [eval_drive.py:54-85](../../../../libs/core/kiln_ai/synthetic_user/eval_drive.py#L54) |
| Fine-tune dataset export | Pulls tool calls and tool results out of the trace | [chat/chat_utils.py:10-61](../../../../libs/core/kiln_ai/adapters/chat/chat_utils.py#L10), [fine_tune/dataset_formatter.py:89](../../../../libs/core/kiln_ai/adapters/fine_tune/dataset_formatter.py#L89) |
| Eval trace formatter (judges) | Reads `reasoning_content` and tool calls to build judge input | [eval/eval_utils/eval_trace_formatter.py:187-197](../../../../libs/core/kiln_ai/adapters/eval/eval_utils/eval_trace_formatter.py#L187) |
| Dataset import | Accepts `reasoning_content` on imported assistant messages | [utils/dataset_import.py:509-585](../../../../libs/core/kiln_ai/utils/dataset_import.py#L509) |
| Web trace viewer | Renders `reasoning_content` and tool calls | `app/web_ui/src/lib/ui/trace/` (tests in `chat_trace.test.ts`) |
| `is_toolcall_pending` | Decides whether a run is waiting on client tools | [open_ai_types.py:270-288](../../../../libs/core/kiln_ai/utils/open_ai_types.py#L270) |

Two facts that matter for reasoning-item round trips (from [adapter-request-response-path.md](./adapter-request-response-path.md) §5, observed offline):

1. Inside one run, LiteLLM `Message` objects stay in the message list, so the bridge replays reasoning items (with `encrypted_content`) on the next tool-loop call.
2. Across runs, only the saved trace is replayed; it has no reasoning items. Multi-turn chat, `return_on_tool_call` resume, synthetic-user turns, and server continuation all cross a run boundary.

**Inference:** the run config is chosen per request, so a conversation can switch provider or model between turns (`run_api.py` takes `run_config_properties` per call). A trace started on Claude via OpenRouter can be continued on GPT-5.4 direct, and the other way round. Anything Responses-specific persisted in the trace must be ignored or stripped safely by other providers.

## 4. Behavior a user can see today vs. after a migration

Read, plus inference where marked:

- **Reasoning text.** OpenAI-direct runs never set `intermediate_outputs["reasoning"]` today (no reasoning returned on Chat Completions, no summary requested). If summaries are requested, reasoning appears in the run view and in eval inputs. `reasoning_capable` stays `False` on these providers, so `BaseAdapter`'s "Reasoning is required" check ([base_adapter.py:308-324](../../../../libs/core/kiln_ai/adapters/model_adapters/base_adapter.py#L308)) would not start failing when a summary is missing.
- **Tools on GPT-5.4+ direct.** Hidden today in the model dropdown when the run config has tools ([available_models_dropdown.svelte:235-236](../../../../app/web_ui/src/lib/ui/run_config_component/available_models_dropdown.svelte#L235)); fine-tune model lists and the models page also read the flag. Saved run configs or API callers that send tools anyway are not blocked by the adapter (Inference from the absence of any runtime check).
- **Thinking level `max`.** Hidden on GPT-6.1 Sol and GPT-6.1 Terra direct because Chat Completions rejects it (comments at [ml_model_list.py:584-587](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L584) and [L1033-1034](../../../../libs/core/kiln_ai/adapters/ml_model_list.py#L1033)). Adding it back is a model-list change once routing exists.
- **Usage.** `MessageUsage` has input, output, total, cached tokens and cost. No reasoning-token count. Kiln does not need new usage fields to keep the contract.
