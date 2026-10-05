# Integration options: getting `LiteLlmAdapter` onto the Responses API

The constraint: keep `BaseAdapter` unchanged, stay on LiteLLM, and contain the change in `LiteLlmAdapter` (and the model list). Evidence for each claim is in [adapter-touchpoints.md](./adapter-touchpoints.md) (code) and [bridge-probe-results.md](./bridge-probe-results.md) (probe runs).

## Where we start

- Kiln **already** sends some OpenAI traffic to `/v1/responses` without knowing it. LiteLLM 1.102.0 bridges `gpt-5.4-pro` and `gpt-5.2-pro` every time (model-map `mode: responses`). It also bridges every gpt-5.4+ / gpt-6 call that carries a function tool with reasoning on. That includes Kiln's `function_calling` structured-output mode, and the `default` mode on OpenAI, which uses a strict `task_response` tool (`litellm_adapter.py:488-500`).
- Kiln still sets `supports_function_calling=False` on 9 gpt-5.4+ OpenAI entries, waiting for "Kiln routes these models to /v1/responses" (`ml_model_list.py:824…1397`). The flag was added when Kiln was locked to litellm 1.81.16, which had no such routing. The routing appeared in 1.82.2.
- What automatic bridging does **not** cover: requests with **no function tool** whose parameters only Responses accepts. Kiln's comment says `reasoning_effort: "max"` on gpt-6.1-sol is one (`ml_model_list.py:549-553`). Others are pro models missing from LiteLLM's map (e.g. `gpt-6-sol-pro`) and anything needing `reasoning.summary`.

## How to express the opt-in (no `BaseAdapter` change)

Add one declarative field to `KilnModelProvider` (`ml_model_list.py:368-482`), next to the existing provider-specific toggles (`openrouter_reasoning_object`, `anthropic_summarized_thinking`, `gemini_reasoning_enabled`):

```python
# Route this model through OpenAI's Responses API (via LiteLLM's
# completion->responses bridge) instead of /v1/chat/completions.
openai_responses_api: bool = False
```

Add a `model_validator` restricting it to `name in (openai, azure_openai)`, like `validate_openrouter_reasoning_object` (`ml_model_list.py:461-470`). Inside `LiteLlmAdapter`, only `build_extra_body` (`:561`), `litellm_model_id` (`:675`) and the choice-reading helpers would read it. `BaseAdapter`, the trace format, `AdapterStream`'s public API and the stream-event contract stay as they are.

Not recommended: a new `ModelAdapterId.litellm_responses` value (`ml_model_list.py:359-365`, dispatched in `adapter_registry.py:180-186`). That would make a new adapter class, which goes beyond "contained inside `LiteLlmAdapter`". It would also duplicate both tool loops.

Not usable: `litellm.route_all_chat_openai_to_responses`. It is process-global, and Kiln maps every custom / OpenAI-compatible / Ollama provider to LiteLLM's `openai` provider (`utils/litellm.py:91-93`). Most of those servers have no `/responses` route, so this would break them.

## Options

### Option 0: Turn function calling back on, rely on LiteLLM's automatic bridge
- **Change:** remove `supports_function_calling=False` (and its comment) from the gpt-5.4+ OpenAI entries. No adapter code change.
- **Covers:** reasoning plus tools for gpt-5.4+ / gpt-6 on OpenAI direct (the documented 400 in Kiln's comment).
- **Doesn't cover:** `max` effort without tools, unmapped pro models, reasoning summaries (no reasoning text comes back).
- **Known gaps it exposes:** the non-streaming preamble bug (text and tool call in one response, so the tool is dropped; `litellm_adapter.py:457`), and responses stored by default. Both already affect `gpt-5.4-pro` / `gpt-5.2-pro` today.
- **Effort:** under ½ day plus paid tool tests per model.

### Option A: Per-model flag that forces LiteLLM's bridge (recommended)
- **Change, inside `LiteLlmAdapter` only:**
  1. `litellm_model_id()`: when `provider.openai_responses_api`, return `openai/responses/<model_id>` (or `azure/responses/<deployment>`). This covers every GPT-5 call, with or without tools, and unmapped pro models. Probe scenario 5 shows cost still worked for a mapped model. *Alternative lever:* put `reasoning_summary: "auto"` in `build_extra_body`. That also forces the bridge for GPT-5-family names (scenario 8) and asks for summaries in one step, but it relies on LiteLLM's name matching, so the prefix is more explicit.
  2. `build_extra_body()`: send `reasoning_effort` as `{"effort": level, "summary": "auto"}` (or add `reasoning_summary: "auto"`) so `intermediate_outputs["reasoning"]` is filled. Decide on `store`: either send `store: False` + `include: ["reasoning.encrypted_content"]` (stateless, matches today's Chat Completions retention), or accept OpenAI's default.
  3. `acompletion_checking_response()` (`:443-457`): merge every returned choice's `content` and `tool_calls` into one message, instead of reading only `choices[0]`. This fixes the preamble bug. The fix helps already-bridged pro models too.
  4. Logprobs: reject `top_logprobs` early with a clear error for flagged models, or map it to `include: ["message.output_text.logprobs"]` + `top_logprobs` through `additional_body_options`. Low priority: no GPT-5.x/6 entry has `supports_logprobs=True`.
  5. Optional: in streaming, carry `reasoning_items` from the final `response.completed` chunk onto the assembled message, so tool loops keep encrypted reasoning (`litellm_streaming.py:70`). This needs a small helper; `stream_chunk_builder` doesn't do it.
  6. Model list: set the flag on gpt-5.4+ / gpt-6 OpenAI entries, re-enable function calling, re-add `max` to GPT-6.1 Sol's levels, and optionally add pro models on OpenAI direct.
- **Unchanged:** message building, tool loop (both copies), structured-output modes, usage/cost parsing, trace saving, multi-turn, AI SDK streaming. All of these get chat-shaped objects back from the bridge.
- **Effort:** about 1–2 days of code and unit tests, plus a paid-test pass.
- **Risk:** Kiln depends on the quality of LiteLLM's bridge, which is large and changes often (1,630 lines in `transformation.py`). The pin `<1.103` limits surprise. A LiteLLM upgrade needs a paid re-test of flagged models.

### Option B: Call `litellm.aresponses()` directly from a new path in `LiteLlmAdapter`
- **Change:** a second request builder and response parser, chosen by the same flag:
  - Request: system→`instructions`; messages (including saved multi-turn traces) → `input` items; `tool_calls`→`function_call`; `role: tool`→`function_call_output`; flat tool schema; `tool_choice` flattening; `response_format`→`text.format`; `reasoning`; `store`/`include`; logprobs `include`.
  - Response: `output` items (`reasoning`, `message`, `function_call`) → a chat-shaped assistant message for the trace (`ChatCompletionAssistantMessageParamWrapper`, `utils/open_ai_types.py:46`), including `reasoning_content`; keep reasoning items in memory for the tool loop; map `incomplete_details` / refusals onto `raise_for_empty_model_response`; usage `input_tokens`→`prompt_tokens`, etc.
  - Streaming: Responses SSE events → **`ModelResponseStream`** chunks. This is required because `BaseAdapter.invoke_openai_stream` publicly yields `ModelResponseStream` (`base_adapter.py:381-400, 891-905`) and `AiSdkStreamConverter` consumes them (`stream_events.py:209`). Then reassemble the final message.
  - Both tool loops (`litellm_adapter.py:147-276` and `adapter_stream.py:212-313`) call `build_completion_kwargs` + `acompletion` / `StreamingCompletion` directly, so both need a branch, or a new abstraction under them.
- **What you gain over A:** full control (`previous_response_id`, built-in tools, exact item ids, no surprises from LiteLLM's heuristics).
- **What it costs:** in effect it re-implements LiteLLM's bridge (`transformation.py` + `OpenAiResponsesToChatCompletionStreamIterator`) inside Kiln. It doubles the request/response test surface.
- **Effort:** about 1.5–3 weeks including tests (inference, from the size of the bridge and of the existing test files).

### Option C: Global route-all flag
Rejected. See "Not usable" above.

## Comparison

| | Option 0: un-flag tools | **Option A: flag + forced bridge** | Option B: direct `aresponses()` |
|---|---|---|---|
| `BaseAdapter` untouched | ✅ | ✅ | ✅ (but must emit `ModelResponseStream`) |
| Code touched | model list only | `LiteLlmAdapter` (~4 methods), `KilnModelProvider` (+1 field, +1 validator), model list | `LiteLlmAdapter` (new builder/parser), `AdapterStream` loop, `StreamingCompletion` or a new stream wrapper, model list |
| Reasoning + tools (gpt-5.4+) | ✅ | ✅ | ✅ |
| Effort levels only Responses accepts (e.g. `max`) without tools | ❌ | ✅ | ✅ |
| Pro models not in LiteLLM's map | ❌ | ✅ (prefix) | ✅ |
| Reasoning summary into `intermediate_outputs` | ❌ | ✅ | ✅ |
| Preamble (text+tool in one response) | ❌ non-stream | ✅ with choice-merge fix | ✅ |
| Encrypted reasoning across tool calls | non-stream only | non-stream; stream with small helper | ✅ |
| Logprobs | ❌ | needs mapping | ✅ |
| Stateless / `store` control | default stored | ✅ via `store: false` + `include` | ✅ |
| Depends on LiteLLM bridge quality | yes | yes | no (depends only on `litellm.aresponses`) |
| Rough effort | ≤½ day | 1–2 days | 1.5–3 weeks |

**Recommendation (inference):** Option A. It is smaller than B by roughly an order of magnitude. The bridge already returns the chat-shaped objects that every Kiln contract downstream expects. The probes found exactly one adapter bug that matters (`choices[0]`), and it is a few lines to fix and already affects pro models today. Option 0 is a reasonable first step if only tools are the goal, but it leaves `max` effort and reasoning summaries unsolved and ships the preamble bug to more models.

## Test impact

Unit tests that mock `litellm.acompletion` (`test_litellm_adapter.py` 19 references, `test_litellm_adapter_tools.py` 12, `test_litellm_adapter_streaming.py` 2, `test_structured_output.py` 2, `test_litellm_adapter_errors.py` 2) **keep working under Options 0/A**, because the bridge sits below `acompletion`. Under Option B, every test that drives a flagged model needs a parallel `aresponses` mock.

New or changed tests for Option A:
- `adapters/test_ml_model_list.py` validation for the new field (only openai/azure).
- `test_litellm_adapter.py`: `litellm_model_id()` adds the `responses/` prefix when flagged and is unchanged otherwise; `build_extra_body` sends summary (and `store` / `include` if chosen) only when flagged; existing `test_build_extra_body_thinking_level_*` tests (`:530-705`) stay as they are.
- `acompletion_checking_response` with a multi-choice `ModelResponse` (text choice + tool-call choice), both orders.
- Streaming: `reasoning_items` carried across a tool round (if step 5 is done).
- One mock-HTTP integration test like the probe, which catches LiteLLM bridge regressions on upgrade without paid calls. Recommended, because the bridge changes often.
- Paid: `test_thinking_level_paid.py` already enumerates every OpenAI thinking level (`:68-131`). Its assertion at `:184` expects reasoning text for every non-`none` level. Inference: on Chat Completions, OpenAI returns no reasoning text for GPT-5.x/6, so those cases can't pass today. With summaries requested through the Responses path, they should. Add `max` to GPT-6.1 Sol and paid tool-call tests (`test_litellm_adapter_tools.py` paid cases) for the flagged models.
