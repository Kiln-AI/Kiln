# Existing tests, and how a routing flag would be tested

Scope: unit tests for the adapter and streaming, the paid tests (`--runpaid`), test helpers and seams, and what testing a new routing flag needs. Commit `579014ab`, read 2026-10-30. Labels: **Read**, **Observed**, **Inference**.

## 1. How paid tests are switched on

Read ([conftest.py:84-175](../../../../conftest.py#L84)):

- `@pytest.mark.paid` tests are skipped unless `--runpaid` ([L157-161](../../../../conftest.py#L157)).
- `--runprerelease` runs only `@pytest.mark.prerelease` tests and implies paid for them.
- `--ollama`, `--runslow` gate their own marks. `--runsinglewithoutchecks` runs a single manually-picked test even if it is marked.
- Keys come from `.env` / environment (`load_dotenv` at session start). `skip_if_missing_provider_keys(provider)` skips when the provider's config keys are missing ([test_paid_utils.py](../../../../libs/core/kiln_ai/adapters/model_adapters/test_paid_utils.py)).
- Every test runs with `KILN_SKIP_REMOTE_MODEL_LIST=true` and a temp settings dir; the root conftest also flushes LiteLLM's client cache per test.

## 2. Unit tests that pin the adapter's chat shape

Read; counts are `grep -c` over test files.

| File | Lines | What it pins |
|---|---|---|
| [test_litellm_adapter.py](../../../../libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter.py) | 3807 | `build_completion_kwargs` (56 references), `build_extra_body` (48), `response_format_options`/`tool_call_params`/`json_schema_response_format`, `litellm_model_id` per provider ([L371-480](../../../../libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter.py#L371)), `usage_from_response` (5), `litellm_message_to_trace_message` (12), strict-false tools, prior-trace continuation, `return_on_tool_call` resume, latency/usage tracking, empty-response errors. Patches `acompletion_checking_response` 15 times. |
| [test_litellm_adapter_tools.py](../../../../libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py) | 1893 | Tool loop with mocked `ModelResponse`s, patching `acompletion_checking_response` (15) and in three places `litellm.acompletion` too. Paid: `test_tools_gpt_4_1_mini` (prerelease), `..._simplified`, and `test_tools_all_built_in_models` over every model that has `supports_function_calling=True` ([L231-251](../../../../libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py#L231)). |
| [test_adapter_stream.py](../../../../libs/core/kiln_ai/adapters/model_adapters/test_adapter_stream.py) | 981 | `AdapterStream` with a `FakeStreamingCompletion` ([L102](../../../../libs/core/kiln_ai/adapters/model_adapters/test_adapter_stream.py#L102)); helpers `_make_streaming_chunk`, `_make_model_response`, `_make_tool_call`, `_make_raw_tool_call` ([L29-80](../../../../libs/core/kiln_ai/adapters/model_adapters/test_adapter_stream.py#L29)), reused by the tools tests; `TestValidateResponse` ([L929](../../../../libs/core/kiln_ai/adapters/model_adapters/test_adapter_stream.py#L929)). |
| [test_litellm_streaming.py](../../../../libs/core/kiln_ai/adapters/litellm_utils/test_litellm_streaming.py) | 206 | `StreamingCompletion`: `include_usage` forcing, patching `litellm.acompletion` and `stream_chunk_builder`. |
| [test_stream_events.py](../../../../libs/core/kiln_ai/adapters/model_adapters/test_stream_events.py) | 436 | `AiSdkStreamConverter` from hand-built chunks. |
| [test_litellm_adapter_streaming.py](../../../../libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_streaming.py) | 1241 | Mostly paid: OpenAI-protocol and AI SDK streams, prior trace, `return_on_tool_call`. Model lists at [L43-62](../../../../libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_streaming.py#L43) have **no OpenAI model**. |
| [test_base_adapter.py](../../../../libs/core/kiln_ai/adapters/model_adapters/test_base_adapter.py) | 2156 | Public methods, stream wrappers, run saving. |
| [test_cloudflare_litellm.py](../../../../libs/core/kiln_ai/adapters/model_adapters/test_cloudflare_litellm.py) | 176 | **Wire-level** tests through real LiteLLM with `respx` (see §4). |
| [test_ml_model_list.py](../../../../libs/core/kiln_ai/adapters/test_ml_model_list.py) | — | Model-list invariants: validators, unique providers, deprecated not suggested, prerelease models exist, Cloudflare/Fireworks level checks. Place for a "flag only on provider X" invariant. |
| [utils/test_litellm.py](../../../../libs/core/kiln_ai/utils/test_litellm.py) | — | `get_litellm_provider_info`. |
| [test_remote_config.py](../../../../libs/core/kiln_ai/adapters/test_remote_config.py) | — | Round trip, extra keys ignored, invalid providers dropped, and the opt-in v0.19 compatibility test (`KILN_TEST_COMPATIBILITY=1`) that CI runs before publishing. |

Other files that patch `acompletion_checking_response`: `test_prompt_adaptors.py`, `test_structured_output.py`, `test_litellm_adapter_errors.py`, `eval/test_eval_runner_worlds.py`, `app/desktop/studio_server/test_repair_api.py`.

**Consequence (Inference):** almost every adapter unit test mocks at `acompletion_checking_response` and returns a `(ModelResponse, Choices)` pair. If a native path keeps that method's return type, these tests keep working. If the reply type changes, the seam and many fixtures change with it. None of these tests exercises LiteLLM's request translation; only `test_cloudflare_litellm.py` goes down to HTTP.

### Hazard: bare `Mock()` providers

Read: `test_litellm_adapter.py` assigns `mock_provider = Mock()` (or `MagicMock()`) **38 times**; `test_adapter_stream.py` once. A `Mock` returns a truthy `Mock` for any attribute not set explicitly. Existing tests set the flags they need by hand (e.g. `mock_provider.temp_top_p_exclusive = False`, [L1501-1503](../../../../libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter.py#L1501)). **Inference:** a new boolean read as `if provider.new_flag:` will be truthy in every such test that does not set it, so those tests would take the new routing branch. Options: set the flag on each mock, use `Mock(spec=KilnModelProvider)` (still truthy), or build real `KilnModelProvider` objects.

## 3. Paid tests that touch OpenAI direct today

Read.

| Test | OpenAI-direct coverage |
|---|---|
| `test_tools_gpt_4_1_mini` (prerelease) | GPT-4.1 mini only. |
| `test_tools_all_built_in_models` | All models with `supports_function_calling=True`; skips the ten affected providers today. |
| `test_thinking_level_reasoning_content` ([test_thinking_level_paid.py:113-191](../../../../libs/core/kiln_ai/adapters/model_adapters/test_thinking_level_paid.py#L113)) | Every OpenAI-direct model × every level; asserts reasoning content is **present** for non-`none` levels (no OpenAI exception in the test). Inference: on Chat Completions OpenAI returns no reasoning text, so these cases may fail today; I could not run them (no key). The prerelease variant `PRERELEASE_THINKING_MODELS` has no OpenAI entry ([pytest_prerelease_whitelist.py:83-88](../../../../libs/core/kiln_ai/adapters/pytest_prerelease_whitelist.py#L83)). |
| Structured output (prerelease) | `gpt_5_4_mini`/`openai` for json_schema and function_calling, nested and flat ([test_structured_output.py:280-308](../../../../libs/core/kiln_ai/adapters/model_adapters/test_structured_output.py#L280)); `test_all_built_in_models_structured_output` fan-out. |
| Prompt caching (prerelease) | `gpt_5_4_mini`/`openai` ([test_prompt_caching.py:47-51](../../../../libs/core/kiln_ai/adapters/model_adapters/test_prompt_caching.py#L47)); relies on `cached_tokens` from `prompt_tokens_details`. |
| Streaming, return-on-tool-call | None (Claude and MiniMax only). |
| Doc extraction (prerelease) | `gpt_4o`/`openai`. |

The closed PR #1757 branch added `test_openai_responses_routing_paid.py` (622 lines) — a lead for what a paid routing test looked like, not reviewed here.

## 4. Testing a routing flag without spending money

Precedent (Read): [test_cloudflare_litellm.py](../../../../libs/core/kiln_ai/adapters/model_adapters/test_cloudflare_litellm.py) builds a real adapter with `adapter_for_task`, patches config for keys, sets `litellm.disable_aiohttp_transport = True` ("LiteLLM sends through aiohttp by default, which respx can't intercept", [L60-63](../../../../libs/core/kiln_ai/adapters/model_adapters/test_cloudflare_litellm.py#L60)), mocks the provider URL with `respx`, then asserts on `route.calls.last.request` (headers, JSON body) and on error classification. `respx>=0.22.0` is already a dev dependency ([pyproject.toml:22](../../../../pyproject.toml#L22)).

Observed: the same approach works for OpenAI direct. With `OPENAI_API_KEY` set to a fake value, `LITELLM_LOCAL_MODEL_COST_MAP=True`, and `respx` routes on both `https://api.openai.com/v1/responses` and `https://api.openai.com/v1/chat/completions`, I ran the real adapter offline and could see:

- which endpoint each model hit (`gpt-5.4-pro` → `/v1/responses`, `gpt-5.4` → `/v1/chat/completions`);
- the request body (`input`, `instructions`, `reasoning`, `tools` with `strict`, `tool_choice`, `temperature`; `store` absent);
- the second tool-loop request (reasoning item replayed, `function_call` + `function_call_output`);
- a continuation from `prior_trace` (reasoning item missing);
- the text-plus-tool-call reply losing the tool call;
- usage and cost mapped into `MessageUsage`.

A test set built this way could cover, per routed provider, without a key:

1. Routing: with the flag, the request goes to `/v1/responses`; without it, to `/v1/chat/completions`. Same for streaming (`stream: true` and an SSE body).
2. Request mapping: tools + `reasoning.effort` together; `strict` on tools and on `text.format`; thinking level `max`; `store`/`include` if set; no `temperature`/`top_p` when required.
3. Reply mapping: text, tool call, text + tool call in one reply, reasoning summary → `reasoning_content` and `intermediate_outputs`, refusal, empty reply → existing error messages.
4. Tool loop across two calls, and across a `prior_trace` continuation and a `return_on_tool_call` resume.
5. Usage and cost from a Responses `usage` block, including `cached_tokens`.
6. Errors: 429/401/5xx bodies from `/v1/responses` still raise `litellm.RateLimitError` / `AuthenticationError` / server errors so `retry_classification` still works (the Cloudflare tests show the pattern).
7. AI SDK events from a recorded Responses SSE stream.

Unit level: `litellm_model_id()` and `build_completion_kwargs()` for flagged and unflagged providers (existing pattern: patch `model_provider`, `litellm_model_id`, `build_extra_body`, `response_format_options`), a model-list invariant (flag only on `openai` providers, or on the agreed list), and a remote-config test that an old-shaped provider dict and a new-shaped one both load.

Paid level: add OpenAI-direct entries for the routed models to `STREAMING_MODELS`, `RETURN_ON_TOOL_CALL_MODELS` and the prerelease lists, since today none of those exercise OpenAI direct.
