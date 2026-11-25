# Every LiteLLM caller in `libs/` and `app/`, and whether a migration touches it

Method: `grep` over `libs/` and `app/` (non-test files) for `litellm.acompletion`, `aembedding`, `arerank`, `aresponses`, `stream_chunk_builder`, `import litellm`, `from litellm`, plus callers of `adapter_for_task`, `LiteLlmAdapter`, `StreamingCompletion` and the streaming methods. Commit `579014ab`, read 2026-10-30.

"Affected" assumes the migration is a per-provider routing decision inside `LiteLlmAdapter` (the adapter path). Where a global LiteLLM switch (for example `litellm.route_all_chat_openai_to_responses`, named in the research plan) would change the answer, the last column says so.

## 1. Direct LiteLLM model calls

| Caller | Call | What it sends | Affected by a per-provider adapter flag? | Affected by a global LiteLLM switch? |
|---|---|---|---|---|
| `LiteLlmAdapter.acompletion_checking_response` ([litellm_adapter.py:580-594](../../../../libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py#L580)) | `litellm.acompletion` | Full agent request | **Yes, the main target** | Yes |
| `StreamingCompletion` ([litellm_streaming.py:59-71](../../../../libs/core/kiln_ai/adapters/litellm_utils/litellm_streaming.py#L59)) | `litellm.acompletion(stream=True)` + `litellm.stream_chunk_builder` | Same kwargs as above, built by the adapter | **Yes** (gets the routed kwargs) | Yes |
| `LitellmExtractor._extract_single_pdf_page`, `_extract` ([litellm_extractor.py:236](../../../../libs/core/kiln_ai/adapters/extractors/litellm_extractor.py#L236), [L401](../../../../libs/core/kiln_ai/adapters/extractors/litellm_extractor.py#L401)) | `litellm.acompletion` | One user message with a text prompt and a file/image/audio part; no tools, no `reasoning_effort`, no `temperature`; reads `choices[0].message.content` | No. It builds its own kwargs ([L344-375](../../../../libs/core/kiln_ai/adapters/extractors/litellm_extractor.py#L344)) and only uses `get_litellm_provider_info` for the model id. It never sends tools with reasoning, so it does not hit the bug. Exception: if routing were put inside `get_litellm_provider_info` it would change here too. | Yes: file parts (`file`, `image_url`, `input_audio`) would go through the conversion layer. The GPT-5.4+ OpenAI-direct providers have `supports_doc_extraction=True`. |
| `LitellmEmbeddingAdapter` ([litellm_embedding_adapter.py:168](../../../../libs/core/kiln_ai/adapters/embedding/litellm_embedding_adapter.py#L168)) | `litellm.aembedding` | `/v1/embeddings` | No | No (embeddings are not chat) |
| `LitellmRerankerAdapter` ([litellm_reranker_adapter.py:53](../../../../libs/core/kiln_ai/adapters/rerankers/litellm_reranker_adapter.py#L53)) | `litellm.arerank` | Rerank endpoint (non-OpenAI providers) | No | No |
| `connect_vertex` ([provider_api.py:1335-1355](../../../../app/desktop/studio_server/provider_api.py#L1335)) | `litellm.acompletion` | Probe call to `vertex_ai/gemini-3.5-flash` | No | No (not OpenAI) |
| `connect_bedrock` ([provider_api.py:1771-1800](../../../../app/desktop/studio_server/provider_api.py#L1771)) | `litellm.acompletion` | Probe call to a fake Bedrock model to test credentials | No | No |

OpenAI and Azure key checks do not call LiteLLM: `connect_openai` does `GET https://api.openai.com/v1/models` ([provider_api.py:1243-1249](../../../../app/desktop/studio_server/provider_api.py#L1243)); `connect_azure_openai` does `GET {endpoint}/openai/files?api-version=2024-08-01-preview` ([L1495-1503](../../../../app/desktop/studio_server/provider_api.py#L1495)). OpenAI-compatible provider discovery uses `openai.OpenAI(...).models.list()` ([L2377-2385](../../../../app/desktop/studio_server/provider_api.py#L2377)). None are affected.

## 2. Indirect callers (all go through `adapter_for_task` → `LiteLlmAdapter`)

These inherit whatever the adapter does. None build their own LiteLLM request.

| Feature | Entry point | Uses | Notes |
|---|---|---|---|
| Run a task (UI and REST) | [libs/server/kiln_server/run_api.py:778-815](../../../../libs/server/kiln_server/run_api.py#L778) | `invoke`, `prior_trace` from `parent_task_run_id` | Multi-turn continuation crosses run boundaries (reasoning items lost, see trace doc). |
| Eval judges (LLM-as-judge, G-Eval) | [eval/g_eval.py:263-327](../../../../libs/core/kiln_ai/adapters/eval/g_eval.py#L263), [eval/v2_eval_llm_judge.py:219-275](../../../../libs/core/kiln_ai/adapters/eval/v2_eval_llm_judge.py#L219) | `invoke_returning_run_output`, `top_logprobs=10` for G-Eval | G-Eval needs `ChoiceLogprobs`; v2 judge refuses G-Eval when `supports_logprobs` is false. No affected provider supports logprobs, so G-Eval cannot pick them. Plain LLM-judge can. |
| Eval task runs | [eval/base_eval.py:723-744](../../../../libs/core/kiln_ai/adapters/eval/base_eval.py#L723) | `invoke` | |
| Synthetic data gen | [app/desktop/studio_server/data_gen_api.py:407-686](../../../../app/desktop/studio_server/data_gen_api.py#L407) | `invoke` | Structured output (json_schema for affected providers). |
| Eval builder | [app/desktop/studio_server/eval_builder_api.py:1135-1151](../../../../app/desktop/studio_server/eval_builder_api.py#L1135), [L1534-1544](../../../../app/desktop/studio_server/eval_builder_api.py#L1534) | `invoke` (including a "Say OK" connectivity check) | |
| Repair | [app/desktop/studio_server/repair_api.py:151-157](../../../../app/desktop/studio_server/repair_api.py#L151) | `invoke` | |
| Synthetic user (multi-turn evals) | [synthetic_user/runner.py:591-626](../../../../libs/core/kiln_ai/synthetic_user/runner.py#L591), [driver.py:84-136](../../../../libs/core/kiln_ai/synthetic_user/driver.py#L84), [eval_drive.py:54-85](../../../../libs/core/kiln_ai/synthetic_user/eval_drive.py#L54) | `invoke` with `prior_trace` every turn; `automatic_prompt_caching=True` | Heaviest user of cross-run replay. |
| LLM built-in tools | [tools/built_in_tools/llm_tools.py:109-123](../../../../libs/core/kiln_ai/tools/built_in_tools/llm_tools.py#L109) | `invoke_returning_run_output` | |
| Kiln task as a tool | [tools/kiln_task_tool.py:94-104](../../../../libs/core/kiln_ai/tools/kiln_task_tool.py#L94) | `invoke` (nested run) | |
| Data-gen tasks, chunkers etc. | via the same adapter | | |

## 3. Things that read LiteLLM objects or settings without calling a model

| Code | Dependency | Affected? |
|---|---|---|
| `CustomLiteLLMLogger` ([utils/logging.py:32-131](../../../../libs/core/kiln_ai/utils/logging.py#L32)), installed by `setup_litellm_logging` in [desktop_server.py:139](../../../../app/desktop/desktop_server.py#L139) | `log_pre_api_call` rebuilds a curl command with `call_type="completion"` ([L46-56](../../../../libs/core/kiln_ai/utils/logging.py#L46)); `async_log_success_event` reads `response_obj.choices[0].message` ([L102-131](../../../../libs/core/kiln_ai/utils/logging.py#L102)) and logs "Model Response (multiple choices)" when there is more than one | Bridge: no change. Native `aresponses`: the success hook gets a response with no `.choices`; the `try/except` turns it into "Could not print". Log-only, but `model_calls.log` would lose response content. |
| `retry_classification.py`, `errors.py` | `isinstance` checks on LiteLLM exception classes | Must still hold on any new call path. |
| `run_output.py`, `eval/g_eval.py`, `eval_utils/scoring_utils.py` | Types `ChoiceLogprobs`, `ChatCompletionTokenLogprob` | Only if routed models gain logprobs. |
| `chat/chat_formatter.py` | `LiteLLMMessage` in the internal message alias | Internal type only. |
| `stream_events.py`, `base_adapter.py` | `ModelResponseStream` (public stream type) | Keep, or convert into it. |
| `app/desktop/studio_server/chat/*` | Parses AI SDK events from Kiln's hosted server using `stream_events` types | Not a LiteLLM caller. Affected only if the AI SDK event shapes change. |
| `eval/_heavy_main_bench.py` | `import litellm` for a startup-time benchmark | No. |

## 4. Fine-tuning

No fine-tune code calls LiteLLM chat (`adapters/fine_tune/` has Fireworks, Together, Vertex providers; OpenAI fine-tuning is "no longer supported for new fine-tunes", [provider_tools.py:369-371](../../../../libs/core/kiln_ai/adapters/provider_tools.py#L369)). Running an existing OpenAI fine-tune goes through `kiln_fine_tune` → `core_provider` → `openai`, with `KilnModelProvider` defaults ([provider_tools.py:340-376](../../../../libs/core/kiln_ai/adapters/provider_tools.py#L340)), so it is affected only if routing is keyed on provider name rather than on a model-list flag. Fine-tune dataset export reads traces (see [public-surface-and-trace-contract.md](./public-surface-and-trace-contract.md) §3). The fine-tune model picker reads `supports_function_calling` to decide whether tools can be in the training data ([finetune_api.py:420-440](../../../../app/desktop/studio_server/finetune_api.py#L420)); none of the affected providers has a `provider_finetune_id`.

## 5. Azure OpenAI

Kiln's Azure provider entries are only GPT-4.1/4o and o1/o3/o4-mini (all `supports_function_calling=True`, no GPT-5.x). Requests go to `azure/<deployment>` with `api_version="2025-02-01-preview"` ([provider_tools.py:796-802](../../../../libs/core/kiln_ai/adapters/provider_tools.py#L796)). Not affected today. If newer models are added on Azure and routed to Responses, the API version and endpoint shape would need checking (OpenAI/LiteLLM subtopics).
